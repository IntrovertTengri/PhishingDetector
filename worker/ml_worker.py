import pika
import redis
import psycopg2
import json
import os
import time
from transformers import pipeline

# Infrastructure Configuration
REDIS_HOST = os.getenv("REDIS_HOST", "redis")
RABBITMQ_HOST = os.getenv("RABBITMQ_HOST", "rabbitmq")
DATABASE_URL = os.getenv("DATABASE_URL")

# Load AI Model (DistilBERT Phishing V2)
print("Loading NLP transformer model...")
classifier = pipeline(
    "text-classification",
    model="cybersectony/phishing-email-detection-distilbert_v2.4.1",
    truncation=True,
    max_length=512
)
print("Model loaded successfully.")

def save_to_postgres(sender, receiver, subject, email_hash, verdict, confidence):
    """Persistence layer: saves analysis results to the relational database."""
    if not DATABASE_URL:
        return

    try:
        with psycopg2.connect(DATABASE_URL) as conn:
            with conn.cursor() as cur:
                # Use ON CONFLICT to maintain idempotency in case of queue retries
                cur.execute("""
                            INSERT INTO phishing_logs
                                (sender, receiver, subject, content_hash, verdict, confidence)
                            VALUES (%s, %s, %s, %s, %s, %s)
                                ON CONFLICT (content_hash) DO NOTHING;
                            """, (sender, receiver, subject, email_hash, verdict, confidence))
    except Exception as e:
        print(f"Database insertion error: {e}")

def callback(ch, method, properties, body):
    """Primary processing logic triggered by message arrival."""
    try:
        message = json.loads(body)
        email_hash = message.get('hash')
        text_to_analyze = message.get('text_to_analyze')

        sender = message.get('sender', 'Unknown')
        receiver = message.get('receiver', 'Unknown')
        subject = message.get('subject', 'No Subject')

        print(f"Processing analysis request: {email_hash[:8]}")

        # Run Inference
        result = classifier(text_to_analyze)[0]
        label = result['label']
        confidence = result['score']

        # Map model-specific labels to system-standard verdicts
        is_phishing = any(x in label.lower() for x in ['label_1', '1', 'phishing', 'spam'])
        verdict = "PHISHING" if is_phishing else "SAFE"

        # Update Redis Cache (TTL: 7 days)
        # Allows poller nodes to skip redundant ML processing
        redis_client = redis.Redis(host=REDIS_HOST, port=6379, db=0, decode_responses=True)
        if verdict == "PHISHING":
            redis_client.setex(name=email_hash, time=604800, value="PHISHING")

        save_to_postgres(sender, receiver, subject, email_hash, verdict, confidence)

    except Exception as e:
        print(f"Worker processing error: {e}")

    finally:
        # Acknowledge message regardless of outcome to prevent queue clogging
        ch.basic_ack(delivery_tag=method.delivery_tag)

def connect_to_rabbitmq():
    """Establish connection to broker with retry logic for infrastructure stability."""
    while True:
        try:
            connection = pika.BlockingConnection(pika.ConnectionParameters(host=RABBITMQ_HOST))
            return connection
        except pika.exceptions.AMQPConnectionError:
            print("RabbitMQ not ready. Retrying in 5 seconds...")
            time.sleep(5)

if __name__ == "__main__":
    connection = connect_to_rabbitmq()
    channel = connection.channel()

    channel.queue_declare(queue='email_analysis_queue', durable=True)
    channel.basic_qos(prefetch_count=1)
    channel.basic_consume(queue='email_analysis_queue', on_message_callback=callback)

    print("Worker online. Monitoring analysis queue...")
    channel.start_consuming()