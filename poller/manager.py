import pika
import json
import os
import time
import psycopg2

RABBITMQ_HOST = os.getenv("RABBITMQ_HOST", "rabbitmq")
DATABASE_URL = os.getenv("DATABASE_URL")
GMAIL_USER = os.getenv("GMAIL_USER")
GMAIL_PASSWORD = os.getenv("GMAIL_PASSWORD")

def get_monitored_inboxes():
    """Fetches the roster from PostgreSQL securely."""
    inboxes = []
    if not DATABASE_URL: return inboxes
    try:
        with psycopg2.connect(DATABASE_URL) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT email_address, app_password FROM monitored_inboxes WHERE is_active = TRUE;")
                for row in cur.fetchall():
                    inboxes.append({"email": row[0], "password": row[1]})
    except Exception as e:
        print(f"[Manager DB Error] {e}")
    return inboxes

def dispatch_tasks():
    targets = get_monitored_inboxes()
    if not targets and GMAIL_USER and GMAIL_PASSWORD:
        targets = [{"email": GMAIL_USER, "password": GMAIL_PASSWORD}]

    if not targets:
        print("[Manager] No active inboxes found. Skipping cycle.")
        return

    try:
        connection = pika.BlockingConnection(pika.ConnectionParameters(host=RABBITMQ_HOST))
        channel = connection.channel()
        # Create the new queue for distributing the inbox tasks
        channel.queue_declare(queue='inbox_tasks_queue', durable=True)

        for target in targets:
            channel.basic_publish(
                exchange='',
                routing_key='inbox_tasks_queue',
                body=json.dumps(target),
                properties=pika.BasicProperties(delivery_mode=2)
            )
            print(f"[Manager] Dispatched task to check inbox: {target['email']}")

        connection.close()
    except Exception as e:
        print(f"[Manager] RabbitMQ Connection Error: {e}")

if __name__ == "__main__":
    print("Waiting 15 seconds for infrastructure...")
    time.sleep(15)
    print("====== Poller Manager Online ======")

    while True:
        dispatch_tasks()
        print("[Manager] Cycle complete. Sleeping for 5 minutes...")
        time.sleep(300) # Wait 5 minutes before handing out tasks again