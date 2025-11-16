FROM python:3.11-alpine

# Set working directory
WORKDIR /usr/app/src

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application files
COPY main.py .
COPY SyncAlpaca.py .
COPY alpaca_client.py .
COPY ghostfolio_client.py .
COPY mapping.yaml .

# Copy shell scripts
COPY entrypoint.sh /usr/app/
COPY run.sh /root/

# Make scripts executable
RUN chmod +x /usr/app/entrypoint.sh /root/run.sh

# Set entrypoint
ENTRYPOINT ["/usr/app/entrypoint.sh"]
