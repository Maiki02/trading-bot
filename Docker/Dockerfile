# =============================================================================
# Dockerfile - Trading Bot High-Frequency Application
# =============================================================================
# Python 3.10 - Optimized for 24/7 production runtime
# Base Image: python:3.10-slim (Debian-based, stable for NumPy/Pandas C extensions)
# =============================================================================

FROM python:3.10-slim

# =============================================================================
# Environment Variables - Performance & Logging Optimization
# =============================================================================
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# =============================================================================
# System Dependencies - Minimal set for Pandas/NumPy compilation
# =============================================================================
# gcc: Required for compiling NumPy/Pandas C extensions
# libgomp1: OpenMP support for NumPy multithreading
# =============================================================================
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        gcc \
        g++ \
        libgomp1 && \
    rm -rf /var/lib/apt/lists/*

# =============================================================================
# Working Directory
# =============================================================================
WORKDIR /app

# =============================================================================
# Python Dependencies - Leverage Docker layer caching
# =============================================================================
# Copy requirements first to cache this layer if dependencies don't change
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# =============================================================================
# Application Code
# =============================================================================
COPY . .

# =============================================================================
# User Configuration - Security Best Practice
# =============================================================================
# Using non-root user for security hardening.
# The 'appuser' will have ownership of /app, ensuring write access to /app/data
# when the volume is mounted (Docker handles permissions correctly).
# =============================================================================
RUN useradd -m -u 1000 appuser && \
    chown -R appuser:appuser /app

USER appuser

# =============================================================================
# Health Check - Monitor bot availability
# =============================================================================
# Validates that main.py process is still running
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD pgrep -f "python.*main.py" || exit 1

# =============================================================================
# Entry Point
# =============================================================================
CMD ["python", "main.py"]
