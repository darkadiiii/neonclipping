# NeonClipping Cloud Container (Fast & Lightweight)
FROM python:3.12-slim

ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1
ENV NEONCLIPPING_CLOUD=1
ENV NEONCLIPPING_LAN=1
ENV NEONCLIPPING_PORT=8770

RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg fonts-dejavu git \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt \
    && pip install --no-cache-dir boto3

COPY . .

EXPOSE 8770

CMD ["python", "app.py"]
