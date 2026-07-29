FROM python:3.12-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    curl \
    git \
    && rm -rf /var/lib/apt/lists/*

# Upgrade pip first
RUN pip install --no-cache-dir --upgrade pip

# Install heavy ML packages first (separate layer for better caching & retry handling)
COPY requirements.txt .
RUN pip install --no-cache-dir \
    --default-timeout=300 \
    --retries 5 \
    "numpy<2.0.0" \
    "scipy==1.12.0"

# Install remaining Python dependencies
RUN pip install --no-cache-dir \
    --default-timeout=300 \
    --retries 5 \
    -r requirements.txt

# Copy source code
COPY . .

# Create non-root user
RUN useradd -m -u 1000 appuser && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
