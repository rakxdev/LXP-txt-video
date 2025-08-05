FROM python:3.11-slim

# Install required system packages (ffmpeg and aria2 are needed by yt-dlp)
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
      ffmpeg aria2 gcc libffi-dev && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of your bot’s code
COPY . .

# Run the Telegram bot directly
CMD ["python3", "main.py"]
