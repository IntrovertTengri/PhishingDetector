import imaplib
import email
import redis
from email.header import decode_header
import pika
import json
import os
import time
import hashlib

# Infrastructure Config
RABBITMQ_HOST = os.getenv("RABBITMQ_HOST", "rabbitmq")
REDIS_HOST = os.getenv("REDIS_HOST", "redis")

# Fast-path Cache Connection
redis_client = redis.Redis(host=REDIS_HOST, port=6379, db=0, decode_responses=True)

def get_email_body(msg):
    """Recursively extracts the plain text body from raw email data."""
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == "text/plain":
                try:
                    return part.get_payload(decode=True).decode(errors="replace")
                except:
                    pass
    else:
        try:
            return msg.get_payload(decode=True).decode(errors="replace")
        except:
            return str(msg.get_payload())
    return ""

def check_inbox(target_email, target_password, analysis_channel):
    """Connects to IMAP, retrieves unread messages, and dispatches to ML queue."""
    mail = None
    try:
        mail = imaplib.IMAP4_SSL("imap.gmail.com")
        mail.login(target_email, target_password)
        mail.select("INBOX")

        # Search for UNSEEN (unread) emails
        status, messages = mail.search(None, '(UNSEEN)')
        if status != 'OK' or not messages[0]:
            print(f"[Node] No new emails in {target_email}.")
            return

        email_ids = messages[0].split()
        for e_id in email_ids:
            res, msg_data = mail.fetch(e_id, "(RFC822)")
            for response_part in msg_data:
                if isinstance(response_part, tuple):
                    msg = email.message_from_bytes(response_part[1])

                    # Decode Subject safely
                    subject_header = decode_header(msg.get("Subject", "No Subject"))[0]
                    subject = subject_header[0]
                    if isinstance(subject, bytes):
                        subject = subject.decode(subject_header[1] or "utf-8", errors="replace")

                    sender = str(msg.get("From", "Unknown Sender"))
                    body = get_email_body(msg)

                    # Generate unique fingerprint for the email
                    email_text = f"Subject: {subject}\n\n{body}"
                    email_hash = hashlib.sha256(email_text.encode('utf-8')).hexdigest()

                    # FAST-PATH: If Redis already has this hash, we skip analysis
                    if redis_client.get(email_hash):
                        print(f"[Node] Skipping duplicate email (Hash: {email_hash[:8]}...)")
                        continue

                    print(f"[Node] Found NEW email in {target_email} from {sender}")

                    message_data = {
                        "hash": email_hash,
                        "text_to_analyze": email_text,
                        "sender": sender,
                        "receiver": target_email,
                        "subject": subject
                    }

                    # Dispatch to ML queue
                    analysis_channel.basic_publish(
                        exchange='',
                        routing_key='email_analysis_queue',
                        body=json.dumps(message_data),
                        properties=pika.BasicProperties(delivery_mode=2)
                    )
    except Exception as e:
        print(f"[Node] Critical error during session for {target_email}: {e}")
    finally:
        # Guarantee the connection is closed even if the loop fails
        if mail:
            try:
                mail.close()
                mail.logout()
            except:
                pass

def callback(ch, method, properties, body):
    """Processor for incoming inbox-check tasks from the Manager."""
    task = json.loads(body)
    target_email = task.get("email")
    target_password = task.get("password")

    print(f"\n[Node] Received task: Check {target_email}")
    check_inbox(target_email, target_password, ch)

    # Acknowledge the task is finished
    ch.basic_ack(delivery_tag=method.delivery_tag)

def start_consuming():
    """Establishes RabbitMQ connection and begins listening for tasks."""
    try:
        connection = pika.BlockingConnection(pika.ConnectionParameters(host=RABBITMQ_HOST))
        channel = connection.channel()

        channel.queue_declare(queue='inbox_tasks_queue', durable=True)
        channel.queue_declare(queue='email_analysis_queue', durable=True)

        # HORIZONTAL SCALING: Take only one task at a time to distribute load
        channel.basic_qos(prefetch_count=1)
        channel.basic_consume(queue='inbox_tasks_queue', on_message_callback=callback)

        print("====== Poller Node Online. Waiting for tasks... ======")
        channel.start_consuming()
    except Exception as e:
        print(f"[Node] RabbitMQ connection drop: {e}. Retrying in 5s...")
        time.sleep(5)

if __name__ == "__main__":
    # Increased wait time to ensure RabbitMQ is fully healthy
    time.sleep(20)
    while True:
        start_consuming()