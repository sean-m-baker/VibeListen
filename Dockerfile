# VibeListen — Multi-stage Docker image
#
# Build:
#   docker build -t vibelisten .
#   docker build --build-arg TTS_PROFILE=edge -t vibelisten:edge .
#
# Run:
#   docker run -p 8000:8000 -v ./data:/app/data --env-file .env vibelisten
#
# Multi-platform: base image python:3.11-slim supports linux/amd64 and linux/arm64.
# Pocket TTS (PyTorch) may need platform-specific wheels on ARM — build with
# TTS_PROFILE=edge or TTS_PROFILE=piper on ARM if Pocket fails.

# ---------------------------------------------------------------------------
# Stage 1 — Builder: install Python dependencies
# ---------------------------------------------------------------------------
FROM python:3.11-slim AS builder

ARG TTS_PROFILE=all

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install core dependencies first (cache-efficient layer)
COPY requirements.txt .
RUN pip install --user --no-cache-dir -r requirements.txt

# Conditionally install local TTS engines based on build arg
COPY requirements-local.txt requirements-piper.txt requirements-pocket.txt ./
RUN if [ "$TTS_PROFILE" != "edge" ]; then \
        pip install --user --no-cache-dir -r requirements-local.txt; \
    fi

# ---------------------------------------------------------------------------
# Stage 2 — Runtime: slim image with only runtime deps
# ---------------------------------------------------------------------------
FROM python:3.11-slim AS runtime

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy installed Python packages from builder's user site-packages
COPY --from=builder /root/.local /root/.local
ENV PATH=/root/.local/bin:$PATH

# Copy application code
COPY . .

# Ensure entrypoint is executable
COPY docker-entrypoint.sh /app/docker-entrypoint.sh
RUN chmod +x /app/docker-entrypoint.sh

EXPOSE 8000

ENTRYPOINT ["/app/docker-entrypoint.sh"]
CMD ["python", "start.py"]
