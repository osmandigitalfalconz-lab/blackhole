FROM python:3.12-slim

# ffmpeg is needed to merge video+audio and to extract MP3
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .

# PORT is set by the host (Render/Koyeb) or defaults to 7860 (Hugging Face Spaces).
EXPOSE 7860
CMD ["sh", "-c", "gunicorn --bind 0.0.0.0:${PORT:-7860} --workers 2 --threads 4 --timeout 600 server:app"]
