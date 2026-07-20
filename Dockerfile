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

# Copy application code
COPY gym_coach/ ./gym_coach/
COPY webhook/ ./webhook/
COPY .env.example ./.env.example

# Cloud Run expects port 8080
EXPOSE 8080

CMD ["uvicorn", "webhook.app:app", "--host", "0.0.0.0", "--port", "8080", "--log-level", "info"]
