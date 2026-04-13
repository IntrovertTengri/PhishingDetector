from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import psycopg2
import pika
import json
import os
import hashlib

app = FastAPI(title="Phishing Shield Admin API")

DATABASE_URL = os.getenv("DATABASE_URL")
RABBITMQ_HOST = os.getenv("RABBITMQ_HOST", "rabbitmq")

class MonitoredInbox(BaseModel):
    display_name: str
    email_address: str
    app_password: str

class ManualScan(BaseModel):
    sender: str
    subject: str
    body_text: str

@app.post("/inboxes/")
def add_inbox(inbox: MonitoredInbox):
    """Add a new Gmail account for the Poller to monitor."""
    try:
        conn = psycopg2.connect(DATABASE_URL)
        cur = conn.cursor()
        cur.execute("""
                    INSERT INTO monitored_inboxes (display_name, email_address, app_password)
                    VALUES (%s, %s, %s)
                    """, (inbox.display_name, inbox.email_address, inbox.app_password))
        conn.commit()
        cur.close()
        conn.close()
        return {"status": "success", "message": f"Now monitoring {inbox.email_address}"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/scan/")
def manual_scan(email: ManualScan):
    """Manually push an email text to the RabbitMQ queue for ML processing."""
    email_text = f"Subject: {email.subject}\n\n{email.body_text}"
    email_hash = hashlib.sha256(email_text.encode('utf-8')).hexdigest()

    message_data = {
        "hash": email_hash,
        "text_to_analyze": email_text,
        "sender": email.sender,
        "subject": email.subject
    }

    try:
        connection = pika.BlockingConnection(pika.ConnectionParameters(host=RABBITMQ_HOST))
        channel = connection.channel()
        channel.queue_declare(queue='email_analysis_queue', durable=True)
        channel.basic_publish(
            exchange='',
            routing_key='email_analysis_queue',
            body=json.dumps(message_data),
            properties=pika.BasicProperties(delivery_mode=2)
        )
        connection.close()
        return {"status": "queued", "hash": email_hash}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"RabbitMQ Error: {e}")

@app.post("/trigger-poll/")
async def trigger_manual_poll():
    """Manual override: Instantly drops inbox check tasks into the queue."""
    try:
        inboxes = []
        # 1. Fetch the roster from the DB securely
        with psycopg2.connect(DATABASE_URL) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT email_address, app_password FROM monitored_inboxes WHERE is_active = TRUE;")
                for row in cur.fetchall():
                    inboxes.append({"email": row[0], "password": row[1]})

        if not inboxes:
            return {"status": "No active inboxes found to monitor."}

        # 2. Connect to RabbitMQ and drop the tasks
        connection = pika.BlockingConnection(pika.ConnectionParameters(host=RABBITMQ_HOST))
        channel = connection.channel()
        channel.queue_declare(queue='inbox_tasks_queue', durable=True)

        for target in inboxes:
            channel.basic_publish(
                exchange='',
                routing_key='inbox_tasks_queue',
                body=json.dumps(target),
                properties=pika.BasicProperties(delivery_mode=2)
            )

        connection.close()
        return {"status": f"Successfully dispatched {len(inboxes)} tasks to the poller nodes!"}

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database or Queue Error: {e}")