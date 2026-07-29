# --- Build stage ---
FROM python:3.12-slim AS builder

WORKDIR /build
COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# --- Runtime stage ---
FROM python:3.12-slim

WORKDIR /app

# Copy installed packages from builder
COPY --from=builder /install /usr/local

# Copy minimal application code required for webhook + GCS photo service
COPY webhook/ ./webhook/
COPY gym_coach/services/ ./gym_coach/services/
COPY gym_coach/__init__.py ./gym_coach/

EXPOSE 8080

CMD ["uvicorn", "webhook.app:app", "--host", "0.0.0.0", "--port", "8080", "--log-level", "info"]
