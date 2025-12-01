# Multi-stage ML training environment
FROM python:3.11-slim as base

# Install system dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /workspace

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy project structure
COPY src/ /workspace/src/
COPY configs/ /workspace/configs/
COPY data/ /workspace/data/
COPY train.py /workspace/train.py

# Set Python path
ENV PYTHONPATH=/workspace

# Default command (can be overridden)
CMD ["python", "train.py"]
