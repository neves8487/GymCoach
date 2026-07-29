"""
GymCoach — FastAPI Webhook Application.

Two operating modes (auto-detected):

  LOCAL  — Runs the ADK Runner in-process (default, for dev).
  REMOTE — Queries a deployed Agent Engine instance via SDK.
           Activated by setting AGENT_ENGINE_RESOURCE_NAME.

Both modes share the same WhatsApp/Telegram integration layer.
"""

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Request, Response, HTTPException, BackgroundTasks

from google.genai import types

from webhook.whatsapp_client import WhatsAppClient
from webhook.telegram_client import TelegramClient
from webhook.signature import verify_signature

logger = logging.getLogger(__name__)

# ------------------------------------------------------------------
# Mode detection
# ------------------------------------------------------------------
_AGENT_ENGINE_RESOURCE = os.getenv("AGENT_ENGINE_RESOURCE_NAME", "")
_USE_REMOTE = bool(_AGENT_ENGINE_RESOURCE)

# ------------------------------------------------------------------
# Globals initialised at startup
# ------------------------------------------------------------------
runner = None          # Runner (local mode) or None
session_service = None # InMemorySessionService (local) or None
agent_engine = None    # ReasoningEngine handle (remote mode) or None
wa_client: WhatsAppClient | None = None
tg_client: TelegramClient | None = None


@asynccontextmanager
async def lifespan(application: FastAPI):
    """Initialise shared resources on startup."""
    global runner, session_service, agent_engine, wa_client, tg_client

    # Configure logging
    log_level = os.getenv("LOG_LEVEL", "INFO")
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    )
    logger.info("GymCoach starting up...")

    if _USE_REMOTE:
        # --- REMOTE mode: connect to Agent Engine ---
        import vertexai
        from vertexai import agent_engines

        project = os.getenv("GOOGLE_CLOUD_PROJECT")
        location = os.getenv("GOOGLE_CLOUD_LOCATION", "europe-west1")
        vertexai.init(project=project, location=location)

        agent_engine = agent_engines.get(_AGENT_ENGINE_RESOURCE)
        logger.info("Remote mode — connected to Agent Engine: %s", _AGENT_ENGINE_RESOURCE)
    else:
        # --- LOCAL mode: in-process Runner ---
        from google.adk.runners import Runner
        from google.adk.sessions import InMemorySessionService
        from gym_coach.agent import root_agent

        session_service = InMemorySessionService()
        runner = Runner(
            agent=root_agent,
            app_name="gym_coach",
            session_service=session_service,
        )
        logger.info("Local mode — Runner initialised with in-process agent")

    # Messaging clients
    wa_client = WhatsAppClient()
    tg_client = TelegramClient()

    logger.info("GymCoach ready")
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


import re


def _clean_session_id(raw_id: str) -> str:
    """Sanitise user/session ID to a valid GCP resource slug [a-z0-9-]."""
    slug = str(raw_id).lower().replace("_", "-").replace("+", "").replace(" ", "")
    clean = re.sub(r"[^a-z0-9-]", "", slug)
    return clean or "user"


# ------------------------------------------------------------------
# Shared agent execution — local Runner or remote Agent Engine
# ------------------------------------------------------------------

async def _run_agent(user_id: str, session_id: str, message: str) -> str:
    """
    Send a message to the agent and return the final text response.

    Transparently handles both modes:
      LOCAL  — Runner.run_async() with in-process sessions
      REMOTE — agent_engine.async_stream_query() via Agent Engine SDK
    """
    clean_user = _clean_session_id(user_id)
    clean_session = f"session-{clean_user}"

    if _USE_REMOTE:
        # --- Agent Engine SDK ---
        if agent_engine is None:
            raise RuntimeError("Agent Engine not initialised")

        # Auto-create session if it doesn't exist yet
        try:
            await agent_engine.async_get_session(user_id=clean_user, session_id=clean_session)
        except Exception:
            try:
                await agent_engine.async_create_session(
                    user_id=clean_user,
                    session_id=clean_session,
                    state={"user_phone": clean_user},
                )
                logger.info("Created new Agent Engine session %s for user %s", clean_session, clean_user)
            except Exception:
                logger.warning("Could not auto-create session %s (may already exist)", clean_session)

        final = ""
        async for event in agent_engine.async_stream_query(
            user_id=clean_user,
            session_id=clean_session,
            message=message,
        ):
            if isinstance(event, dict):
                content = event.get("content")
                if isinstance(content, str):
                    final += content
                elif isinstance(content, dict):
                    parts = content.get("parts", [])
                    if isinstance(parts, list):
                        for part in parts:
                            if isinstance(part, dict) and "text" in part:
                                final += str(part["text"])
            elif hasattr(event, "content") and event.content:
                c = event.content
                if isinstance(c, str):
                    final += c
                elif hasattr(c, "parts") and c.parts:
                    for part in c.parts:
                        if hasattr(part, "text") and part.text:
                            final += str(part.text)
        return final
    else:
        # --- Local Runner ---
        if runner is None or session_service is None:
            raise RuntimeError("Runner/session not initialised")

        # Ensure session exists
        session = await session_service.get_session(
            app_name="gym_coach",
            user_id=user_id,
            session_id=session_id,
        )
        if session is None:
            await session_service.create_session(
                app_name="gym_coach",
                user_id=user_id,
                session_id=session_id,
                state={"user_phone": user_id},
            )
            logger.info("New session created for %s", user_id)

        content = types.Content(
            role="user",
            parts=[types.Part(text=message)],
        )
        final = ""
        async for event in runner.run_async(
            user_id=user_id,
            session_id=session_id,
            new_message=content,
        ):
            if event.is_final_response():
                if event.content and event.content.parts:
                    for part in event.content.parts:
                        if part.text:
                            final += part.text
        return final


# ------------------------------------------------------------------
# WhatsApp message processing (runs in background)
# ------------------------------------------------------------------

async def _process_message(message_data: dict[str, Any]) -> None:
    """Process a single WhatsApp message through the agent."""
    if wa_client is None:
        logger.error("WhatsApp client not initialised")
        return

    phone = message_data["from"]
    msg_type = message_data["type"]

    # Mark as read
    try:
        await wa_client.mark_as_read(message_data["message_id"])
    except Exception:
        logger.warning("Failed to mark message as read")

    # Build message text
    if msg_type == "text":
        text = message_data.get("text", "")
        if not text:
            return
    elif msg_type == "image":
        image_id = message_data.get("image_id", "")
        caption = message_data.get("image_caption", "Analisa esta refeição.")
        if image_id:
            try:
                image_bytes = await wa_client.download_media(image_id)
                from gym_coach.services import storage_client
                gs_uri = storage_client.upload_photo(phone, image_bytes)
                text = f"{caption}\n\n[Foto guardada em: {gs_uri}]"
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
        await wa_client.send_text(
            phone,
            "Por agora só consigo processar mensagens de texto e fotos 📸",
        )
        return

    # Run the agent and send response
    try:
        response = await _run_agent(
            user_id=phone,
            session_id=phone,
            message=text,
        )
        if response:
            await wa_client.send_text(phone, response)
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


# ------------------------------------------------------------------
# Telegram Webhook — Incoming messages (POST)
# ------------------------------------------------------------------

@app.post("/telegram-webhook")
async def telegram_webhook_receive(
    request: Request,
    background_tasks: BackgroundTasks,
) -> dict[str, str]:
    """
    Receive incoming Telegram messages and process them via ADK.

    Returns 200 immediately and processes in background to avoid
    Telegram timeout/retry.
    """
    try:
        payload: dict[str, Any] = await request.json()
    except Exception:
        logger.exception("Failed to parse Telegram webhook payload")
        return {"status": "error"}

    # Extract update message
    message = payload.get("message")
    if not message:
        # We only care about normal message events
        return {"status": "no_message"}

    # Process in background
    background_tasks.add_task(_process_telegram_message, message)

    return {"status": "received"}


async def _process_telegram_message(message: dict[str, Any]) -> None:
    """Process a single Telegram message through the agent."""
    if tg_client is None:
        logger.error("Telegram client not initialised")
        return

    chat_id = message["chat"]["id"]
    text = message.get("text")
    photo = message.get("photo")
    caption = message.get("caption", "Analisa esta refeição.")
    user_id = f"telegram_{chat_id}"

    # Build message text
    if text:
        if text.startswith("/"):
            if text == "/start":
                text = "Olá! Quero começar a treinar e registar as minhas refeições."
            else:
                text = text.lstrip("/")
    elif photo:
        largest_photo = photo[-1]
        file_id = largest_photo["file_id"]
        try:
            image_bytes = await tg_client.download_file(file_id)
            from gym_coach.services import storage_client
            gs_uri = storage_client.upload_photo(user_id, image_bytes)
            text = f"{caption}\n\n[Foto guardada em: {gs_uri}]"
        except Exception:
            logger.exception("Failed to process Telegram photo %s", file_id)
            await tg_client.send_text(
                chat_id,
                "⚠️ Desculpa, não consegui processar a imagem. Tenta novamente.",
            )
            return
    else:
        await tg_client.send_text(
            chat_id,
            "Por agora só consigo processar mensagens de texto e fotos 📸",
        )
        return

    # Run the agent and send response
    try:
        response = await _run_agent(
            user_id=user_id,
            session_id=user_id,
            message=text,
        )
        if response:
            await tg_client.send_text(chat_id, response)
        else:
            logger.warning("Agent returned empty response for %s", user_id)
            await tg_client.send_text(
                chat_id,
                "🤔 Não consegui gerar uma resposta. Tenta reformular a mensagem.",
            )
    except Exception:
        logger.exception("Error running agent for %s", user_id)
        await tg_client.send_text(
            chat_id,
            "⚠️ Ocorreu um erro a processar a tua mensagem. Tenta novamente.",
        )

