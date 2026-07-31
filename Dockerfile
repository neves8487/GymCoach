# --- Build stage ---
FROM python:3.12-slim AS builder

WORKDIR /build
COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# --- Runtime stage ---
FROM python:3.12-slim

WORKDIR /app

COPY --from=builder /install /usr/local

# Webhook + todo o pacote gym_coach (agentes, tools, prompts, services)
COPY webhook/ ./webhook/
COPY gym_coach/ ./gym_coach/

EXPOSE 8080

CMD ["uvicorn", "webhook.app:app", "--host", "0.0.0.0", "--port", "8080", "--log-level", "info"]
