
FROM python:3.10-slim

# Loglarni darhol chiqarish (buferlamaslik)
ENV PYTHONUNBUFFERED=1

# FFmpeg o'rnatish
RUN apt-get update && apt-get install -y ffmpeg && rm -rf /var/lib/apt/lists/*

# Ishchi papka
WORKDIR /app

# Requirements nusxalash va o'rnatish
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Loyihani nusxalash
COPY . .

# Botni ishga tushirish
CMD ["python", "bot.py"]
