import streamlit as st
import pandas as pd
import psycopg2
import os
import time
import requests

API_URL = "http://api:8000/scan/"

def get_db_connection():
    return psycopg2.connect(os.getenv("DATABASE_URL"))

def get_data():
    try:
        with get_db_connection() as conn:
            query = """
                    SELECT sender, receiver, subject, verdict, confidence, received_at
                    FROM phishing_logs
                    ORDER BY received_at DESC LIMIT 50 \
                    """
            df = pd.read_sql(query, conn)
        return df
    except Exception as e:
        st.error(f"CRITICAL DATABASE ERROR: {e}")
        return pd.DataFrame()

def check_result(email_hash):
    try:
        with get_db_connection() as conn:
            # 100% IMMUNE: Using 'params' to sanitize the hash input
            query = "SELECT verdict, confidence FROM phishing_logs WHERE content_hash = %s"
            df = pd.read_sql(query, conn, params=(email_hash,))
        return df
    except Exception:
        return pd.DataFrame()

# --- FUNCTIONS FOR INBOX MANAGEMENT ---
def get_monitored_inboxes():
    try:
        with get_db_connection() as conn:
            query = "SELECT id, display_name, email_address, is_active FROM monitored_inboxes"
            df = pd.read_sql(query, conn)
        return df
    except Exception:
        return pd.DataFrame()

def add_monitored_inbox(name, email, app_pwd):
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                # Parameterized query to prevent SQL injection on employee inputs
                cur.execute(
                    "INSERT INTO monitored_inboxes (display_name, email_address, app_password) VALUES (%s, %s, %s)",
                    (name, email, app_pwd)
                )
            # The 'with' block for conn automatically commits the transaction!
        return True
    except Exception as e:
        st.error(f"Database error: {e}")
        return False

st.set_page_config(page_title="Corporate Phishing Shield", layout="wide")
st.title("Enterprise Threat Gateway")

tab1, tab2, tab3 = st.tabs(["IT Dashboard", "Employee Scanner", "Manage Inboxes"])

# ==========================================
# TAB 1: THE IT DASHBOARD
# ==========================================
with tab1:
    col_a, col_b = st.columns([0.8, 0.2])
    with col_b:
        if st.button("Refresh Dashboard"):
            st.rerun()

    df = get_data()
    if not df.empty:
        col1, col2 = st.columns(2)
        phishing_count = len(df[df['verdict'] == 'PHISHING'])
        col1.metric("Total Emails Scanned", len(df))
        col2.metric("Threats Detected", phishing_count, delta_color="inverse")

        st.subheader("Live Analysis Feed")
        def color_verdict(row):
            return ['background-color: #ffcccc' if row.verdict == 'PHISHING' else '' for _ in row]

        st.dataframe(df.style.apply(color_verdict, axis=1), use_container_width=True, hide_index=True)
    else:
        st.info("System Online. Waiting for incoming traffic...")

# ==========================================
# TAB 2: THE EMPLOYEE SCANNER
# ==========================================
with tab2:
    st.subheader("Suspicious Email Scanner")
    with st.form("manual_scan_form"):
        sender = st.text_input("Sender Address", placeholder="e.g., HR@mycompany.com")
        subject = st.text_input("Email Subject")
        body = st.text_area("Email Body", height=150)

        if st.form_submit_button("Scan for Threats", type="primary"):
            if sender and subject and body:
                try:
                    res = requests.post(API_URL, json={"sender": sender, "subject": subject, "body_text": body})
                    if res.status_code == 200:
                        email_hash = res.json().get("hash")
                        with st.spinner("AI is analyzing the text..."):
                            for _ in range(20):
                                time.sleep(0.5)
                                result_df = check_result(email_hash)
                                if not result_df.empty:
                                    verdict = result_df.iloc[0]['verdict']
                                    confidence = result_df.iloc[0]['confidence']
                                    st.markdown("---")
                                    if verdict == 'PHISHING':
                                        st.error(f"**WARNING: PHISHING DETECTED!** (Confidence: {confidence:.2f})")
                                    else:
                                        st.success(f"**SAFE.** (Confidence: {confidence:.2f})")
                                    break
                except Exception as e:
                    st.error(f"API Error: {e}")
            else:
                st.warning("Please fill in all fields.")

# ==========================================
# TAB 3: MANAGE INBOXES
# ==========================================
with tab3:
    col_x, col_y = st.columns([0.7, 0.3])
    with col_x:
        st.subheader("Monitored Email Accounts")
        st.markdown("Add new employee inboxes for the background Poller to monitor.")
    with col_y:
        # THE NEW MANUAL OVERRIDE BUTTON
        if st.button("Force Check Inboxes Now", use_container_width=True):
            try:
                res = requests.post("http://api:8000/trigger-poll/")
                if res.status_code == 200:
                    st.success(res.json().get("status"))
                else:
                    st.error("Failed to trigger the API.")
            except Exception as e:
                st.error(f"API Error: {e}")

    with st.form("add_inbox_form"):
        col1, col2 = st.columns(2)
        name = col1.text_input("Employee Name", placeholder="e.g., Alice Smith")
        email = col2.text_input("Gmail Address", placeholder="e.g., alice.security.test@gmail.com")
        app_pwd = st.text_input("Google App Password", type="password", help="The 16-character app password")

        if st.form_submit_button("Add to Roster", type="primary"):
            if name and email and app_pwd:
                if add_monitored_inbox(name, email, app_pwd):
                    st.success(f"Added {email}! The Poller will check it on its next loop.")
                    time.sleep(1)
                    st.rerun()
            else:
                st.warning("All fields are required.")

    st.markdown("---")
    st.markdown("**Currently Monitored Roster:**")
    inboxes_df = get_monitored_inboxes()
    if not inboxes_df.empty:
        st.dataframe(inboxes_df, use_container_width=True, hide_index=True)
    else:
        st.info("No inboxes are currently in the database.")