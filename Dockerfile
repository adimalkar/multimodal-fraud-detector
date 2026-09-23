# Multi-Agent Forensics Engine - Hugging Face Spaces & Production Container
# Free Tier Specs: 16 GB RAM + 2 vCPU on Hugging Face Docker Spaces

FROM python:3.10-slim

# Install system dependencies for OpenCV, PDF extraction (poppler), video (ffmpeg), and health checks
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 \
    libglib2.0-0 \
    poppler-utils \
    ffmpeg \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Hugging Face Spaces runs as user with UID 1000
RUN useradd -m -u 1000 user
USER user
ENV HOME=/home/user \
    PATH=/home/user/.local/bin:$PATH \
    PYTHONUNBUFFERED=1

WORKDIR $HOME/app

# Install Python requirements
COPY --chown=user requirements.txt requirements.txt
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy application files
COPY --chown=user . .

# Initialize database schema if not present
RUN python database/init_db.py || true

# Default Hugging Face Space port is 7860, Render uses $PORT
ENV PORT=7860
EXPOSE 7860

CMD ["sh", "-c", "uvicorn backend.app:app --host 0.0.0.0 --port ${PORT:-7860}"]
