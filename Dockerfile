FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# FFmpeg o'rnatish
RUN apt-get update && \
    apt-get install -y ffmpeg gcc && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Requirements avval (cache uchun)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Loyihani nusxalash
COPY . .

CMD ["python", "bot.py"]
