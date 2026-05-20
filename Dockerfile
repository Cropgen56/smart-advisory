# ─────────────────────────────────────────────────────────────────────────────
# Stage 1 — Builder
#   Installs all Python dependencies into an isolated prefix so the final
#   image doesn't need pip, build tools, or cache files.
# ─────────────────────────────────────────────────────────────────────────────
FROM python:3.11-slim AS builder

WORKDIR /install

# Install build dependencies needed by pandas / openpyxl C extensions
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install/deps -r requirements.txt


# ─────────────────────────────────────────────────────────────────────────────
# Stage 2 — Runtime
#   Lean image: only the installed packages + application code.
# ─────────────────────────────────────────────────────────────────────────────
FROM python:3.11-slim AS runtime

# Non-root user for security
RUN addgroup --system appgroup && adduser --system --ingroup appgroup appuser

WORKDIR /app

# Copy installed Python packages from builder stage
COPY --from=builder /install/deps /usr/local

# Copy application source
COPY --chown=appuser:appgroup . .

# Remove dev/test artefacts that don't belong in production
RUN rm -f test.py test_lifecycle.py analysis_results.md

# Switch to non-root user
USER appuser

# Uvicorn listens on PORT (default 8000) — Cloud Run / Kubernetes override via env
ENV PORT=8000
EXPOSE 8000

# ── Health check
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:${PORT}/health')"

# ── Start server
#   - 1 worker per container (scale horizontally via replicas)
#   - Binds to all interfaces so Docker port mapping works
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT} --workers 1"]
