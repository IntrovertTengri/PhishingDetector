CREATE TABLE IF NOT EXISTS monitored_inboxes (
    id SERIAL PRIMARY KEY,
    display_name VARCHAR(100),
    email_address VARCHAR(255) UNIQUE NOT NULL,
    app_password TEXT NOT NULL,
    is_active BOOLEAN DEFAULT TRUE
    );

CREATE TABLE IF NOT EXISTS phishing_logs (
    id SERIAL PRIMARY KEY,
    sender VARCHAR(255),
    receiver VARCHAR(255),
    subject TEXT,
    content_hash VARCHAR(64) UNIQUE,
    verdict VARCHAR(20),
    confidence FLOAT,
    received_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
                              );

CREATE INDEX idx_phishing_logs_hash ON phishing_logs(content_hash);