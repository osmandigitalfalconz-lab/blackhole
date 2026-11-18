FROM python:3.12-slim

# ffmpeg is needed to merge video+audio and to extract MP3
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .

ENV PORT=5000
EXPOSE 5000
# Use $PORT (Render sets it) instead of a fixed port.
CMD ["sh", "-c", "gunicorn --bind 0.0.0.0:$PORT --workers 2 --threads 4 --timeout 600 server:app"]
