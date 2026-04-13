FROM python:3.10-slim

WORKDIR /app

# This replaces the "-u" flag. It forces Python to instantly print logs to the terminal!
ENV PYTHONUNBUFFERED=1

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# We set the node as the default, but your docker-compose.yml will override this for the manager!
CMD ["python", "node.py"]