import imaplib
import email
import redis
from email.header import decode_header
import pika
import json
import os
import time
import hashlib

RABBITMQ_HOST = os.getenv("RABBITMQ_HOST", "rabbitmq")
REDIS_HOST = os.getenv("REDIS_HOST", "redis")

redis_client = redis.Redis(host=REDIS_HOST, port=6379, db=0, decode_responses=True)

def get_email_body(msg):
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == "text/plain":
                try: return part.get_payload(decode=True).decode()
                except: pass
    else:
        try: return msg.get_payload(decode=True).decode()
        except: return str(msg.get_payload())
    return ""

def check_inbox(target_email, target_password, analysis_channel):
    """Logs into the assigned inbox and pushes emails to the ML queue."""
    mail = None
    try:
        mail = imaplib.IMAP4_SSL("imap.gmail.com")
        mail.login(target_email, target_password)
        status, _ = mail.select("INBOX")
        if status != 'OK': return

        status, messages = mail.search(None, '(UNSEEN)')
        if status != 'OK': return

        email_ids = messages[0].split()
        if not email_ids:
            print(f"[Node] No new emails in {target_email}.")
            mail.logout()
            return

        for e_id in email_ids:
            res, msg_data = mail.fetch(e_id, "(RFC822)")
            for response_part in msg_data:
                if isinstance(response_part, tuple):
                    msg = email.message_from_bytes(response_part[1])

                    subject_header = decode_header(msg.get("Subject", "No Subject"))[0]
                    subject = subject_header[0]
                    if isinstance(subject, bytes):
                        subject = subject.decode(subject_header[1] or "utf-8", errors="replace")

                    sender = str(msg.get("From", "Unknown Sender"))
                    body = get_email_body(msg)

                    email_text = f"Subject: {subject}\n\n{body}"
                    email_hash = hashlib.sha256(email_text.encode('utf-8')).hexdigest()

                    if redis_client.get(email_hash): continue

                    print(f"[Node] Found NEW email in {target_email} from {sender}")

                    message_data = {
                        "hash": email_hash,
                        "text_to_analyze": email_text,
                        "sender": sender,
                        "receiver": target_email,
                        "subject": subject
                    }

                    # Push to the ML Worker
                    analysis_channel.basic_publish(
                        exchange='',
                        routing_key='email_analysis_queue',
                        body=json.dumps(message_data),
                        properties=pika.BasicProperties(delivery_mode=2)
                    )
        mail.logout()
    except Exception as e:
        print(f"[Node] Error checking {target_email}: {e}")
        try:
            if mail:
                mail.logout()
        except:
            pass

def callback(ch, method, properties, body):
    """Triggered every time the Manager hands out a task."""
    task = json.loads(body)
    target_email = task.get("email")
    target_password = task.get("password")

    print(f"\n[Node] Received task: Check {target_email}")
    check_inbox(target_email, target_password, ch)

    # Tell RabbitMQ the task is done so it removes it from the queue
    ch.basic_ack(delivery_tag=method.delivery_tag)

def start_consuming():
    try:
        connection = pika.BlockingConnection(pika.ConnectionParameters(host=RABBITMQ_HOST))
        channel = connection.channel()

        # Ensure both queues exist
        channel.queue_declare(queue='inbox_tasks_queue', durable=True)
        channel.queue_declare(queue='email_analysis_queue', durable=True)

        channel.basic_qos(prefetch_count=1) # Only take 1 task at a time
        channel.basic_consume(queue='inbox_tasks_queue', on_message_callback=callback)

        print("====== Poller Node Online. Waiting for tasks... ======")
        channel.start_consuming()
    except Exception as e:
        print(f"[Node] Connection error: {e}. Retrying in 5s...")
        time.sleep(5)

if __name__ == "__main__":
    time.sleep(20) # Wait for RabbitMQ to boot
    while True:
        start_consuming()