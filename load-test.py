import requests
import time

# The URL of your Admin API
API_URL = "http://localhost:8000/scan/"

# A mix of safe and malicious emails to test the AI's accuracy
TEST_EMAILS = [
    {"sender": "hr@yourcompany.com", "subject": "Policy Update", "body_text": "Please review the attached updated vacation policy for 2026."},
    {"sender": "security@paypal-alert.com", "subject": "URGENT: Account Locked", "body_text": "Your account is restricted. Click here to verify immediately: http://paypal-update-secure-login.com"},
    {"sender": "colleague@yourcompany.com", "subject": "Lunch today?", "body_text": "Hey, are we still on for lunch at 12:30?"},
    {"sender": "support@netflix-billing.com", "subject": "Payment Failed", "body_text": "Your subscription will be canceled. Update your credit card details here: http://netflix-billing-error.com/login"},
    {"sender": "it-dept@yourcompany.com", "subject": "Server Maintenance", "body_text": "The main database will be down for 15 minutes tonight at 2 AM for routine updates."},
    {"sender": "admin@bank-of-america-security.com", "subject": "Suspicious Login Attempt", "body_text": "We detected a login from Russia. If this wasn't you, secure your account: http://bofa-secure-reset.com"},
]

print(f"🚀 Firing {len(TEST_EMAILS)} test emails at the gateway...")

# Fire them off rapidly!
for i, email_data in enumerate(TEST_EMAILS):
    try:
        response = requests.post(API_URL, json=email_data)
        if response.status_code == 200:
            print(f"[SUCCESS] Sent email {i+1}: {email_data['subject']}")
        else:
            print(f"[ERROR] API rejected email {i+1}: {response.text}")
    except Exception as e:
        print(f"[FATAL] Could not connect to API: {e}")

    # Tiny pause so we don't overwhelm your local network port
    time.sleep(0.2)

print("✅ All test emails dispatched to RabbitMQ!")
print("👀 Watch your Docker logs and Streamlit Dashboard to see the workers process them!")