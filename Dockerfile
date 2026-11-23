# NeonClipping Cloud Container
FROM nvidia/cuda:12.2.0-runtime-ubuntu22.04

# Avoid prompts
ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1
ENV NEONCLIPPING_LAN=1
ENV NEONCLIPPING_PORT=8770

# System dependencies: Python 3.12, FFmpeg, Git, fonts
RUN apt-get update && apt-get install -y --no-install-recommends \
    software-properties-common curl git \
    && add-apt-repository ppa:deadsnakes/ppa -y \
    && apt-get update && apt-get install -y --no-install-recommends \
    python3.12 python3.12-venv python3.12-dev python3-pip \
    ffmpeg fonts-dejavu fonts-liberation \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy requirements and install
COPY requirements.txt .
RUN python3.12 -m venv .venv \
    && .venv/bin/pip install --upgrade pip \
    && .venv/bin/pip install -r requirements.txt \
    && .venv/bin/pip install boto3

# Copy application source
COPY . .

EXPOSE 8770

CMD [".venv/bin/python", "app.py"]
