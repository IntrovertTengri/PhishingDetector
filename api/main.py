from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import psycopg2
import pika
import json
import os
import hashlib

app = FastAPI(
    title="Phishing Shield Admin API",
    description="Backend management API for corporate inbox monitoring and manual threat analysis."
)

# Infrastructure Configuration
DATABASE_URL = os.getenv("DATABASE_URL")
RABBITMQ_HOST = os.getenv("RABBITMQ_HOST", "rabbitmq")

# Data Models
class MonitoredInbox(BaseModel):
    display_name: str
    email_address: str
    app_password: str

class ManualScan(BaseModel):
    sender: str
    subject: str
    body_text: str

# API ENDPOINTS

@app.post("/inboxes/", status_code=201)
def add_inbox(inbox: MonitoredInbox):
    """Registers a new Gmail account for automated background monitoring."""
    try:
        with psycopg2.connect(DATABASE_URL) as conn:
            with conn.cursor() as cur:
                cur.execute("""
                            INSERT INTO monitored_inboxes (display_name, email_address, app_password)
                            VALUES (%s, %s, %s)
                            """, (inbox.display_name, inbox.email_address, inbox.app_password))
        return {"status": "success", "message": f"Now monitoring {inbox.email_address}"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Database Write Error: {e}")

@app.post("/scan/")
def manual_scan(email: ManualScan):
    """Dispatches a manual email template to the ML Worker for asynchronous analysis."""
    email_text = f"Subject: {email.subject}\n\n{email.body_text}"
    email_hash = hashlib.sha256(email_text.encode('utf-8')).hexdigest()

    message_data = {
        "hash": email_hash,
        "text_to_analyze": email_text,
        "sender": email.sender,
        "receiver": "Manual Admin Scan",
        "subject": email.subject
    }

    try:
        # Standard RabbitMQ Publisher logic
        with pika.BlockingConnection(pika.ConnectionParameters(host=RABBITMQ_HOST)) as connection:
            channel = connection.channel()
            channel.queue_declare(queue='email_analysis_queue', durable=True)
            channel.basic_publish(
                exchange='',
                routing_key='email_analysis_queue',
                body=json.dumps(message_data),
                properties=pika.BasicProperties(delivery_mode=2)
            )
        return {"status": "queued", "hash": email_hash}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Broker Dispatch Error: {e}")

@app.post("/trigger-poll/")
async def trigger_manual_poll():
    """Manual Override: Bypasses the 5-minute manager interval to trigger an immediate inbox check."""
    try:
        inboxes = []
        with psycopg2.connect(DATABASE_URL) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT email_address, app_password FROM monitored_inboxes WHERE is_active = TRUE;")
                for row in cur.fetchall():
                    inboxes.append({"email": row[0], "password": row[1]})

        if not inboxes:
            return {"status": "No active inboxes found to monitor."}

        with pika.BlockingConnection(pika.ConnectionParameters(host=RABBITMQ_HOST)) as connection:
            channel = connection.channel()
            channel.queue_declare(queue='inbox_tasks_queue', durable=True)
            for target in inboxes:
                channel.basic_publish(
                    exchange='',
                    routing_key='inbox_tasks_queue',
                    body=json.dumps(target),
                    properties=pika.BasicProperties(delivery_mode=2)
                )

        return {"status": f"Dispatched {len(inboxes)} polling tasks to nodes successfully."}

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"System Integration Error: {e}")