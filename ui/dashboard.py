import streamlit as st
import pandas as pd
import psycopg2
import os
import time
import requests

# Pointing to the FastAPI container
API_BASE_URL = "http://api:8000"

def get_db_connection():
    return psycopg2.connect(os.getenv("DATABASE_URL"))

def get_data():
    """Fetches the latest analysis results for the dashboard."""
    try:
        with get_db_connection() as conn:
            query = """
                    SELECT sender, receiver, subject, verdict, confidence, received_at
                    FROM phishing_logs
                    ORDER BY received_at DESC LIMIT 50 \
                    """
            return pd.read_sql(query, conn)
    except Exception as e:
        st.error(f"Data Sync Error: {e}")
        return pd.DataFrame()

def check_result(email_hash):
    """Checks if the ML Worker has finished processing a specific hash."""
    try:
        with get_db_connection() as conn:
            query = "SELECT verdict, confidence FROM phishing_logs WHERE content_hash = %s"
            return pd.read_sql(query, conn, params=(email_hash,))
    except Exception:
        return pd.DataFrame()

def get_monitored_inboxes():
    """Fetches the current roster of monitored employees."""
    try:
        with get_db_connection() as conn:
            query = "SELECT display_name, email_address, is_active FROM monitored_inboxes"
            return pd.read_sql(query, conn)
    except Exception:
        return pd.DataFrame()

# --- Page Configuration ---
st.set_page_config(page_title="Phishing Shield", layout="wide")
st.title("Phishing Detection Gateway")

tab1, tab2, tab3 = st.tabs(["Dashboard", "Scanner", "Settings"])

# ==========================================
# TAB 1: DASHBOARD
# ==========================================
with tab1:
    col_a, col_b = st.columns([0.8, 0.2])
    with col_b:
        if st.button("Refresh Results", use_container_width=True):
            st.rerun()

    df = get_data()
    if not df.empty:
        col1, col2 = st.columns(2)
        phishing_count = len(df[df['verdict'] == 'PHISHING'])
        col1.metric("Total Processed", len(df))
        col2.metric("Threats Flagged", phishing_count, delta_color="inverse")

        st.subheader("Live Feed")

        def highlight_threats(row):
            if row.verdict == 'PHISHING':
                return ['background-color: #950000; color: white; font-weight: bold;' for _ in row]
            return ['' for _ in row]

        st.dataframe(
            df.style.apply(highlight_threats, axis=1),
            use_container_width=True,
            hide_index=True
        )
    else:
        st.info("No logs found. Waiting for incoming traffic.")

# ==========================================
# TAB 2: MANUAL SCANNER
# ==========================================
with tab2:
    st.subheader("Manual Analysis")
    st.write("Submit suspicious email content for AI evaluation.")

    with st.form("manual_scan_form"):
        sender = st.text_input("From", placeholder="sender@example.com")
        subject = st.text_input("Subject")
        body = st.text_area("Content", height=200)

        if st.form_submit_button("Analyze", type="primary"):
            if all([sender, subject, body]):
                try:
                    res = requests.post(f"{API_BASE_URL}/scan/", json={
                        "sender": sender,
                        "subject": subject,
                        "body_text": body
                    })

                    if res.status_code == 200:
                        email_hash = res.json().get("hash")
                        with st.spinner("Processing..."):
                            found = False
                            for _ in range(15):
                                time.sleep(1)
                                result_df = check_result(email_hash)
                                if not result_df.empty:
                                    verdict = result_df.iloc[0]['verdict']
                                    confidence = result_df.iloc[0]['confidence']

                                    st.write("---")
                                    if verdict == 'PHISHING':
                                        st.error(f"Result: PHISHING (Confidence: {confidence:.2%})")
                                    else:
                                        st.success(f"Result: SAFE (Confidence: {confidence:.2%})")
                                    found = True
                                    break
                            if not found:
                                st.warning("Analysis pending. Check the Dashboard in a few minutes.")
                except Exception as e:
                    st.error(f"Network error: {e}")
            else:
                st.warning("All fields are required.")

# ==========================================
# TAB 3: SETTINGS / MANAGEMENT
# ==========================================
with tab3:
    col_title, col_btn = st.columns([0.7, 0.3])
    with col_title:
        st.subheader("Inbox Roster")
    with col_btn:
        if st.button("Trigger Immediate Check", use_container_width=True):
            try:
                res = requests.post(f"{API_BASE_URL}/trigger-poll/")
                if res.status_code == 200:
                    st.success("Tasks dispatched.")
            except Exception as e:
                st.error(f"API Error: {e}")

    with st.expander("Register New Account", expanded=True):
        with st.form("add_inbox_form", clear_on_submit=True):
            c1, c2 = st.columns(2)
            new_name = c1.text_input("Name")
            new_email = c2.text_input("Email")
            new_pwd = st.text_input("App Password", type="password")

            if st.form_submit_button("Save Account"):
                if all([new_name, new_email, new_pwd]):
                    try:
                        api_res = requests.post(f"{API_BASE_URL}/inboxes/", json={
                            "display_name": new_name,
                            "email_address": new_email,
                            "app_password": new_pwd
                        })
                        if api_res.status_code == 201:
                            st.success(f"Registered {new_email}")
                            time.sleep(1)
                            st.rerun()
                        else:
                            st.error("Failed to register account.")
                    except Exception as e:
                        st.error(f"Connectivity error: {e}")

    st.write("---")
    roster = get_monitored_inboxes()
    if not roster.empty:
        st.table(roster)
    else:
        st.info("No accounts are currently monitored.")