import pika
import json
import os
import time
import psycopg2

RABBITMQ_HOST = os.getenv("RABBITMQ_HOST", "rabbitmq")
DATABASE_URL = os.getenv("DATABASE_URL")

def get_monitored_inboxes():
    """Fetches the active roster from PostgreSQL."""
    inboxes = []
    try:
        with psycopg2.connect(DATABASE_URL) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT email_address, app_password FROM monitored_inboxes WHERE is_active = TRUE;")
                for row in cur.fetchall():
                    inboxes.append({"email": row[0], "password": row[1]})
    except Exception as e:
        print(f"[Manager DB Error] {e}")
    return inboxes

def perform_maintenance():
    """Implements a 7-day data retention policy."""
    try:
        with psycopg2.connect(DATABASE_URL) as conn:
            with conn.cursor() as cur:
                # Clean up logs older than 7 days to prevent DB bloat
                cur.execute("DELETE FROM phishing_logs WHERE received_at < NOW() - INTERVAL '7 days';")
        print("[Manager] Maintenance: Stale logs purged successfully.")
    except Exception as e:
        print(f"[Manager Maintenance Error] {e}")

def dispatch_tasks():
    targets = get_monitored_inboxes()

    if not targets:
        print("[Manager] No active inboxes in database. Waiting for UI registration...")
        return

    try:
        with pika.BlockingConnection(pika.ConnectionParameters(host=RABBITMQ_HOST)) as connection:
            channel = connection.channel()
            channel.queue_declare(queue='inbox_tasks_queue', durable=True)

            for target in targets:
                channel.basic_publish(
                    exchange='',
                    routing_key='inbox_tasks_queue',
                    body=json.dumps(target),
                    properties=pika.BasicProperties(delivery_mode=2)
                )
            print(f"[Manager] Dispatched {len(targets)} inbox monitoring tasks.")
    except Exception as e:
        print(f"[Manager] RabbitMQ Connection Error: {e}")

if __name__ == "__main__":
    print("Waiting 15 seconds for infrastructure...")
    time.sleep(15)
    print("====== Poller Manager Online (Multi-Tenant Mode) ======")

    while True:
        # 1. Clear out old data
        perform_maintenance()

        # 2. Assign new work
        dispatch_tasks()

        print("[Manager] Cycle complete. Sleeping for 5 minutes...")
        time.sleep(300)