# ACP CW3: Distributed Phishing Detection Gateway

This project is a Proof of Concept (PoC) for a highly scalable, event-driven phishing detection gateway. It utilizes a microservices architecture to monitor corporate inboxes (via IMAP) and analyzes email semantics using a fine-tuned DistilBERT NLP model.

## Prerequisites
To run this project, the marker will need the following installed on their host machine:
* **Docker**
* **Docker Compose**
* *Note: The ML Worker downloads the DistilBERT model on its first run. An active internet connection is required.*

## Step 1: Environment Setup
Before building the project, you must define the environment variables. 

1. In the root directory of the project, locate the `.env.example` file (or create a new file named `.env`).
2. Add the necessary configurations:

## Step 2: Build and Run the Services
This project is fully containerized. To build the images and start the distributed network, run the following command in your terminal from the root directory:

```bash
docker-compose up --build -d
```

This command will orchestrate the following containers:
* `postgres-db`: Relational database for audit logs and employee rosters.
* `redis`: High-speed cache for the "Fast-Path" deduplication.
* `rabbitmq`: Message broker for asynchronous task distribution.
* `api`: FastAPI backend (Port 8000).
* `ui`: Streamlit frontend (Port 8501).
* `poller-manager`: The Master scheduler for automated inbox checking.
* `poller-node`: The worker fleet that fetches IMAP data.
* `worker`: The DistilBERT inference engine.

## Step 3: Verifying the Deployment
Because the infrastructure (RabbitMQ, Postgres) takes a few seconds to initialize, the Python workers have a built-in wait time. 

You can check the health of the services by viewing the logs:

```bash
docker-compose logs -f
```

Wait until you see the following messages:
* `[Node] ====== Poller Node Online. Waiting for tasks... ======`
* `[ML-Worker] Model loaded successfully. Worker online. Monitoring analysis queue...`

## Step 4: How to Test the System

Once the system is online, you can test it in two ways:

**1. Manual Scan (The UI Dashboard)**
* Open your browser and navigate to `http://localhost:8501`.
* Go to the "Manual Scan" tab.
* Paste any text or known phishing email content into the form and submit.
* The API will dispatch the task to RabbitMQ, the ML Worker will analyze it, and the results will immediately populate in the Database / Logs tab.

**2. Automated Inbox Monitoring**
* In the UI Dashboard, navigate to the "Manage Inboxes" section.
* Add a valid Gmail address and an **App Password** (see the Appendix below for instructions). Standard Google passwords will not work due to security policies.
* Once added, the `poller-manager` will automatically pick up this inbox during its next 20-second loop. 
* Send a test email to that Gmail account. Within 20 seconds, the `poller-node` will retrieve it, hash it via Redis, and send it to the `ml-worker` for evaluation. The final verdict will appear in the UI logs.

## Shutting Down
To stop the services and remove the network, run:

```bash
docker-compose down
```

*(Note: To completely wipe the PostgreSQL database and Redis cache, run `docker-compose down -v` to remove the persistent volumes).*

## Appendix: How to Create a Gmail App Password
Google's security policies prevent third-party automated scripts from logging in with your regular Google account password. Instead, you must generate and use a 16-digit "App Password."

**Step-by-Step Instructions:**
1. **Open Security Settings:** Log in to your Google Account and navigate to the **Security** tab in the left menu.
2. **Verify 2-Step Verification:** Under "How you sign in to Google," ensure **2-Step Verification** is turned on.
3. **Access App Passwords:** Click on **2-Step Verification** and scroll to the bottom to find **App passwords**. You may need to sign in again. *(Alternatively, you can search "App passwords" directly in the Google Account search bar).*
4. **Create App Password:**
   * Enter a custom name for the app (e.g., "Phishing Scanner PoC").
   * Click **Create**.
5. **Save the Password:** Copy the 16-digit code presented in the yellow box. **Once you close the window, you will not be able to see this password again.** Paste this code into the UI Dashboard or `.env` file instead of your regular password.
