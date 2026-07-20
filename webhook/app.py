"""
GymCoach — FastAPI Webhook Application.

Integrates the ADK Runner with WhatsApp Business API:
1. Receives messages from WhatsApp via POST /webhook
2. Passes them to the ADK root_agent via Runner
3. Sends the agent's response back via WhatsApp API

The ADK Runner manages sessions (conversation memory) per user.
"""

from __future__ import annotations

import base64
import logging
import os
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Request, Response, HTTPException, BackgroundTasks

from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

from gym_coach.agent import root_agent
from webhook.whatsapp_client import WhatsAppClient
from webhook.signature import verify_signature

logger = logging.getLogger(__name__)

# ------------------------------------------------------------------
# Globals initialised at startup
# ------------------------------------------------------------------
runner: Runner | None = None
session_service: InMemorySessionService | None = None
wa_client: WhatsAppClient | None = None


@asynccontextmanager
async def lifespan(application: FastAPI):
    """Initialise shared resources on startup."""
    global runner, session_service, wa_client

    # Configure logging
    log_level = os.getenv("LOG_LEVEL", "INFO")
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    )
    logger.info("GymCoach starting up...")

    # ADK Session Service
    # TODO: Replace with DatabaseSessionService (Firestore-backed) for production
    session_service = InMemorySessionService()

    # ADK Runner — connects the agent to the session service
    runner = Runner(
        agent=root_agent,
        app_name="gym_coach",
        session_service=session_service,
    )

    # WhatsApp client
    wa_client = WhatsAppClient()

    logger.info("GymCoach ready — runner and WhatsApp client initialised")
    yield
    logger.info("GymCoach shutting down")


app = FastAPI(
    title="GymCoach",
    description="WhatsApp PT + Nutritionist Agent (ADK + Vertex AI)",
    version="0.1.0",
    lifespan=lifespan,
)


# ------------------------------------------------------------------
# Health check
# ------------------------------------------------------------------

@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


# ------------------------------------------------------------------
# WhatsApp Webhook — Verification (GET)
# ------------------------------------------------------------------

@app.get("/webhook")
async def webhook_verify(request: Request) -> Response:
    """
    Respond to Meta's webhook verification challenge.

    Meta sends: ?hub.mode=subscribe&hub.challenge=X&hub.verify_token=Y
    We return the challenge if the token matches.
    """
    params = request.query_params
    verify_token = os.getenv("WHATSAPP_VERIFY_TOKEN", "")

    mode = params.get("hub.mode")
    token = params.get("hub.verify_token")
    challenge = params.get("hub.challenge")

    if mode == "subscribe" and token == verify_token:
        logger.info("Webhook verified successfully")
        return Response(content=challenge, media_type="text/plain")

    logger.warning("Webhook verification failed (mode=%s)", mode)
    raise HTTPException(status_code=403, detail="Verification failed")


# ------------------------------------------------------------------
# WhatsApp Webhook — Incoming messages (POST)
# ------------------------------------------------------------------

@app.post("/webhook")
async def webhook_receive(
    request: Request,
    background_tasks: BackgroundTasks,
) -> dict[str, str]:
    """
    Receive incoming WhatsApp messages and process them via ADK.

    Returns 200 immediately and processes in background to avoid
    WhatsApp timeout (WhatsApp retries on slow responses).
    """
    body = await request.body()

    # --- Signature validation (production only) ---
    app_secret = os.getenv("WHATSAPP_APP_SECRET", "")
    if app_secret:
        signature = request.headers.get("X-Hub-Signature-256", "")
        if not verify_signature(body, signature, app_secret):
            logger.warning("Invalid webhook signature")
            raise HTTPException(status_code=403, detail="Invalid signature")

    # --- Parse payload ---
    try:
        payload: dict[str, Any] = await request.json()
    except Exception:
        logger.exception("Failed to parse webhook payload")
        return {"status": "error"}

    # --- Extract message ---
    message_data = _extract_message(payload)
    if message_data is None:
        # Not a message event (could be status update, etc.)
        return {"status": "no_message"}

    # --- Process in background ---
    background_tasks.add_task(_process_message, message_data)

    return {"status": "received"}


# ------------------------------------------------------------------
# Message extraction
# ------------------------------------------------------------------

def _extract_message(payload: dict[str, Any]) -> dict[str, Any] | None:
    """
    Extract the relevant message data from WhatsApp webhook payload.

    Returns None if no message is present (e.g. status updates).
    """
    try:
        entry = payload.get("entry", [])
        if not entry:
            return None

        changes = entry[0].get("changes", [])
        if not changes:
            return None

        value = changes[0].get("value", {})
        messages = value.get("messages", [])
        if not messages:
            return None

        msg = messages[0]
        contact = value.get("contacts", [{}])[0]

        result: dict[str, Any] = {
            "message_id": msg.get("id", ""),
            "from": msg.get("from", ""),
            "timestamp": msg.get("timestamp", ""),
            "type": msg.get("type", "text"),
            "contact_name": contact.get("profile", {}).get("name", ""),
        }

        if msg.get("type") == "text":
            result["text"] = msg.get("text", {}).get("body", "")
        elif msg.get("type") == "image":
            result["image_id"] = msg.get("image", {}).get("id", "")
            result["image_caption"] = msg.get("image", {}).get("caption", "")
        elif msg.get("type") == "audio":
            result["audio_id"] = msg.get("audio", {}).get("id", "")

        return result

    except (KeyError, IndexError):
        logger.exception("Failed to extract message from payload")
        return None


# ------------------------------------------------------------------
# Message processing (runs in background)
# ------------------------------------------------------------------

async def _process_message(message_data: dict[str, Any]) -> None:
    """
    Process a single WhatsApp message through the ADK agent.

    Flow:
    1. Mark as read
    2. Ensure session exists (create if needed)
    3. Build the ADK content (text or image)
    4. Run the agent via Runner
    5. Send response back via WhatsApp
    """
    global runner, session_service, wa_client

    if runner is None or session_service is None or wa_client is None:
        logger.error("Runner/session/client not initialised")
        return

    phone = message_data["from"]
    msg_type = message_data["type"]

    # Mark as read
    try:
        await wa_client.mark_as_read(message_data["message_id"])
    except Exception:
        logger.warning("Failed to mark message as read")

    # Ensure session exists for this user
    session_id = phone  # 1 session per phone number
    session = await session_service.get_session(
        app_name="gym_coach",
        user_id=phone,
        session_id=session_id,
    )
    if session is None:
        session = await session_service.create_session(
            app_name="gym_coach",
            user_id=phone,
            session_id=session_id,
            state={"user_phone": phone},  # Inject phone into state for tools
        )
        logger.info("New session created for %s", phone)

    # Build ADK content based on message type
    parts: list[types.Part] = []

    if msg_type == "text":
        text = message_data.get("text", "")
        if not text:
            return
        parts.append(types.Part(text=text))

    elif msg_type == "image":
        # Download image from WhatsApp
        image_id = message_data.get("image_id", "")
        caption = message_data.get("image_caption", "Analisa esta refeição.")
        if image_id:
            try:
                image_bytes = await wa_client.download_media(image_id)

                # Upload to Cloud Storage
                from gym_coach.services import storage_client
                gs_uri = storage_client.upload_photo(phone, image_bytes)

                # Send image as inline data to Gemini
                image_b64 = base64.b64encode(image_bytes).decode("utf-8")
                parts.append(types.Part.from_bytes(
                    data=image_bytes,
                    mime_type="image/jpeg",
                ))
                parts.append(types.Part(
                    text=f"{caption}\n\n[Foto guardada em: {gs_uri}]"
                ))
            except Exception:
                logger.exception("Failed to process image %s", image_id)
                await wa_client.send_text(
                    phone,
                    "⚠️ Desculpa, não consegui processar a imagem. Tenta novamente.",
                )
                return
        else:
            return
    else:
        # Unsupported message type
        await wa_client.send_text(
            phone,
            "Por agora só consigo processar mensagens de texto e fotos 📸",
        )
        return

    # Run the agent
    try:
        content = types.Content(role="user", parts=parts)

        final_response = ""
        async for event in runner.run_async(
            user_id=phone,
            session_id=session_id,
            new_message=content,
        ):
            if event.is_final_response():
                if event.content and event.content.parts:
                    for part in event.content.parts:
                        if part.text:
                            final_response += part.text

        if final_response:
            await wa_client.send_text(phone, final_response)
        else:
            logger.warning("Agent returned empty response for %s", phone)
            await wa_client.send_text(
                phone,
                "🤔 Não consegui gerar uma resposta. Tenta reformular a mensagem.",
            )

    except Exception:
        logger.exception("Error running agent for %s", phone)
        await wa_client.send_text(
            phone,
            "⚠️ Ocorreu um erro a processar a tua mensagem. Tenta novamente.",
        )
