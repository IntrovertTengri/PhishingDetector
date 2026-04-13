import pika
import redis
import psycopg2
import json
import os
import time
from transformers import pipeline

# Give RabbitMQ and Postgres a few seconds to boot up
print("Waiting for infrastructure to start...")
time.sleep(15)

REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
RABBITMQ_HOST = os.getenv("RABBITMQ_HOST", "localhost")
DATABASE_URL = os.getenv("DATABASE_URL")

# Connect to Redis
redis_client = redis.Redis(host=REDIS_HOST, port=6379, db=0, decode_responses=True)

# 1. LOAD THE PUBLIC AI MODEL
print("Loading cybersectony/phishing-email-detection-distilbert_v2.4.1 model...")
classifier = pipeline(
    "text-classification",
    model="cybersectony/phishing-email-detection-distilbert_v2.4.1",
    truncation=True,
    max_length=512
)
print("Model loaded successfully!")

# Helper function to save to our new database safely
def save_to_postgres(sender, receiver, subject, email_hash, verdict, confidence):
    if not DATABASE_URL:
        print("    -> No DATABASE_URL found. Skipping DB save.")
        return

    try:
        # Secure context manager for database connections
        with psycopg2.connect(DATABASE_URL) as conn:
            with conn.cursor() as cur:
                # We added 'receiver' to the columns and the %s placeholders
                cur.execute("""
                            INSERT INTO phishing_logs (sender, receiver, subject, content_hash, verdict, confidence)
                            VALUES (%s, %s, %s, %s, %s, %s)
                                ON CONFLICT (content_hash) DO NOTHING
                            """, (sender, receiver, subject, email_hash, verdict, confidence))
            # The 'with' block automatically commits the transaction!
        print("    -> Saved result to PostgreSQL.")
    except Exception as e:
        print(f"    -> DB Error: {e}")

def callback(ch, method, properties, body):
    message = json.loads(body)
    email_hash = message.get('hash')
    text_to_analyze = message.get('text_to_analyze')

    # Safely get sender/receiver/subject
    sender = message.get('sender', 'Unknown Sender')
    receiver = message.get('receiver', 'Unknown Receiver') # WE ADDED THIS!
    subject = message.get('subject', 'No Subject')

    print(f"\n[x] Analyzing email from: {sender} | Hash: {email_hash[:8]}...")

    try:
        # 2. RUN THE AI CLASSIFICATION
        result = classifier(text_to_analyze)[0]
        label = result['label']
        confidence = result['score']

        # Normalize the label to a standard 'PHISHING' or 'SAFE'
        if label in ['LABEL_1', '1'] or 'phishing' in label.lower() or 'spam' in label.lower():
            verdict = "PHISHING"
        else:
            verdict = "SAFE"

        print(f"    -> AI Verdict: {verdict} (Confidence: {confidence:.2f})")

        # 3. IF MALICIOUS, UPDATE REDIS WITH A TTL
        if verdict == "PHISHING":
            print("    -> Action: Phishing detected! Saving to Redis Fast-Path Cache.")
            redis_client.setex(name=email_hash, time=604800, value="PHISHING")
        else:
            print("    -> Action: Email is safe.")

        # 4. SAVE EVERYTHING TO POSTGRES FOR THE UI DASHBOARD
        # We are now passing the receiver into the function!
        save_to_postgres(sender, receiver, subject, email_hash, verdict, confidence)

    except Exception as e:
        print(f"    -> Error during ML processing: {e}")

    # 5. ACKNOWLEDGE THE MESSAGE
    ch.basic_ack(delivery_tag=method.delivery_tag)
    print("[x] Analysis complete. Waiting for next email...")

# Connect to RabbitMQ
connection = pika.BlockingConnection(pika.ConnectionParameters(host=RABBITMQ_HOST))
channel = connection.channel()
channel.queue_declare(queue='email_analysis_queue', durable=True)

channel.basic_qos(prefetch_count=1)
channel.basic_consume(queue='email_analysis_queue', on_message_callback=callback)

print(' [*] ML Worker is online. Waiting for messages. To exit press CTRL+C')
channel.start_consuming()