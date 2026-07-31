"""
GymCoach — FastAPI Webhook Application.

Chama o Root Agent deployado no Vertex AI Agent Engine via Agent Engine SDK.
O Root Agent orquestra PT e Nutrition Agents (também no Agent Engine)
via protocolo A2A nativo (RemoteA2aAgent).

Para dev local, define AGENT_ENGINE_RESOURCE_NAME="" e o webhook corre
o root agent em processo.
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
from contextlib import asynccontextmanager
from datetime import date
from typing import Any

from fastapi import FastAPI, Request, Response, HTTPException, BackgroundTasks

from google.genai import types

from webhook.whatsapp_client import WhatsAppClient
from webhook.telegram_client import TelegramClient
from webhook.signature import verify_signature

logger = logging.getLogger(__name__)

# ------------------------------------------------------------------
# Mode: REMOTE = Agent Engine SDK | LOCAL = in-process Runner (dev)
# ------------------------------------------------------------------
_AGENT_ENGINE_RESOURCE = os.getenv("AGENT_ENGINE_RESOURCE_NAME", "")
_USE_REMOTE = bool(_AGENT_ENGINE_RESOURCE)

# ------------------------------------------------------------------
# Globals
# ------------------------------------------------------------------
runner = None
session_service = None
agent_engine = None
wa_client: WhatsAppClient | None = None
tg_client: TelegramClient | None = None


@asynccontextmanager
async def lifespan(application: FastAPI):
    """Initialise shared resources on startup."""
    global runner, session_service, agent_engine, wa_client, tg_client

    log_level = os.getenv("LOG_LEVEL", "INFO")
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    )
    logger.info("GymCoach starting up...")

    if _USE_REMOTE:
        import vertexai
        from vertexai import agent_engines

        project = os.getenv("GOOGLE_CLOUD_PROJECT")
        location = os.getenv("GOOGLE_CLOUD_LOCATION", "us-central1")
        vertexai.init(project=project, location=location)
        agent_engine = agent_engines.get(_AGENT_ENGINE_RESOURCE)
        logger.info("REMOTE mode — Root Agent Engine: %s", _AGENT_ENGINE_RESOURCE)
    else:
        from google.adk.runners import Runner
        from google.adk.sessions import InMemorySessionService
        from gym_coach.agent import root_agent

        session_service = InMemorySessionService()
        runner = Runner(
            agent=root_agent,
            app_name="gym_coach",
            session_service=session_service,
        )
        logger.info("LOCAL mode — Runner com root_agent em processo")

    wa_client = WhatsAppClient()
    tg_client = TelegramClient()

    logger.info("GymCoach ready")
    yield
    logger.info("GymCoach shutting down")


app = FastAPI(
    title="GymCoach",
    description="WhatsApp PT + Nutritionist Agent (ADK + A2A + Vertex AI Agent Engine)",
    version="0.2.0",
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
    message_data = _extract_whatsapp_message(payload)
    if message_data is None:
        # Not a message event (could be status update, etc.)
        return {"status": "no_message"}

    # --- Process in background ---
    background_tasks.add_task(_process_whatsapp_message, message_data)

    return {"status": "received"}


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
        return {"status": "no_message"}

    # Process in background
    background_tasks.add_task(_process_telegram_message, message)

    return {"status": "received"}


# ------------------------------------------------------------------
# WhatsApp message extraction
# ------------------------------------------------------------------

def _extract_whatsapp_message(payload: dict[str, Any]) -> dict[str, Any] | None:
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
# Session & Agent helpers
# ------------------------------------------------------------------

def _clean_session_id(raw_id: str) -> str:
    """Sanitise user/session ID to a valid GCP resource slug [a-z0-9-]."""
    slug = str(raw_id).lower().replace("_", "-").replace("+", "").replace(" ", "")
    clean = re.sub(r"[^a-z0-9-]", "", slug)
    return clean or "user"


def _extract_text_from_event(event: Any) -> str:
    """
    Extract text from a single Agent Engine streaming event.

    Agent Engine events can arrive in many formats depending on
    whether the response comes from the root agent directly or after
    sub-agent delegation (AgentTool). This function handles all known
    event structures:

      - dict with "content" -> str
      - dict with "content" -> dict with "parts" -> list of dicts with "text"
      - dict with "actions" -> dict with "parts" -> list of dicts with "text"
      - object with .content.parts[].text attributes
      - object with .text directly

    Returns the extracted text, or empty string if no text found.
    """

    def _extract_parts_text(parts: Any) -> str:
        """Extract text from a list of parts (dict or object)."""
        collected = ""
        if not isinstance(parts, (list, tuple)):
            return ""
        for part in parts:
            if isinstance(part, dict):
                t = part.get("text")
                if t:
                    collected += str(t)
            elif hasattr(part, "text") and part.text:
                collected += str(part.text)
        return collected

    def _extract_content_text(content: Any) -> str:
        """Extract text from a content value (str, dict, or object)."""
        if isinstance(content, str):
            return content
        if isinstance(content, dict):
            # dict with "parts" key
            parts = content.get("parts")
            if parts:
                return _extract_parts_text(parts)
            # dict with direct "text" key
            t = content.get("text")
            if t:
                return str(t)
            return ""
        # Object with .parts attribute
        if hasattr(content, "parts") and content.parts:
            return _extract_parts_text(content.parts)
        # Object with .text attribute
        if hasattr(content, "text") and content.text:
            return str(content.text)
        return ""

    try:
        if isinstance(event, dict):
            # Try "content" key first (most common)
            content = event.get("content")
            if content is not None:
                text = _extract_content_text(content)
                if text:
                    return text

            # Try "actions" key (some Agent Engine versions)
            actions = event.get("actions")
            if isinstance(actions, dict):
                parts = actions.get("parts")
                if parts:
                    text = _extract_parts_text(parts)
                    if text:
                        return text

            # Try nested "parts" at top level
            parts = event.get("parts")
            if parts:
                text = _extract_parts_text(parts)
                if text:
                    return text

        else:
            # Object-style event
            if hasattr(event, "content") and event.content:
                text = _extract_content_text(event.content)
                if text:
                    return text

            if hasattr(event, "text") and event.text:
                return str(event.text)

            if hasattr(event, "parts") and event.parts:
                text = _extract_parts_text(event.parts)
                if text:
                    return text

    except Exception:
        logger.exception("Error extracting text from event: %s", type(event).__name__)

    return ""


# ------------------------------------------------------------------
# Agent execution via ADK Runner
# (root_agent delega via RemoteA2aAgent → Agent Engine sub-agents)
# ------------------------------------------------------------------

async def _run_agent(user_id: str, message: str) -> str:
    """Envia mensagem ao root agent e devolve a resposta final em texto."""
    if _USE_REMOTE:
        return await _run_agent_remote(user_id, message)
    return await _run_agent_local(user_id, message)


async def _run_agent_remote(user_id: str, message: str) -> str:
    """Modo REMOTE — chama o Root Agent Engine via async_stream_query.

    Gera um session_id diário (session-{user}-{YYYY-MM-DD}) para:
    - Manter contexto ao longo do dia (o agente lembra-se das mensagens anteriores).
    - Fazer rotação automática a cada dia novo (evita context bloat / 429s).
    - user_phone guardado no estado da sessão para as tools de Firestore.
    """
    if agent_engine is None:
        raise RuntimeError("Agent Engine not initialised")

    clean_user = _clean_session_id(user_id)
    session_id = f"session-{clean_user}-{date.today().isoformat()}"

    logger.info("REMOTE query — user=%s session=%s", clean_user, session_id)

    # Garante que a sessão existe com user_phone em state
    try:
        await agent_engine.async_get_session(user_id=clean_user, session_id=session_id)
    except Exception:
        try:
            await agent_engine.async_create_session(
                user_id=clean_user,
                session_id=session_id,
                state={"user_phone": clean_user},
            )
            logger.info("Created new Agent Engine session %s for user %s", session_id, clean_user)
        except Exception:
            logger.warning("Could not auto-create session %s (may already exist)", session_id)

    final = ""
    async for event in agent_engine.async_stream_query(
        user_id=clean_user,
        session_id=session_id,
        message=message,
    ):
        text = _extract_text_from_event(event)
        if text:
            final = text  # keep the last meaningful chunk

    logger.info("REMOTE — done for %s (session=%s)", clean_user, session_id)
    return final


async def _run_agent_local(user_id: str, message: str) -> str:
    """Modo LOCAL — corre o root_agent em processo via ADK Runner."""
    clean_user = _clean_session_id(user_id)
    clean_session = f"session-{clean_user}-{date.today().isoformat()}"

    if runner is None or session_service is None:
        raise RuntimeError("Runner/session not initialised")

    session = await session_service.get_session(
        app_name="gym_coach",
        user_id=user_id,
        session_id=clean_session,
    )
    if session is None:
        await session_service.create_session(
            app_name="gym_coach",
            user_id=user_id,
            session_id=clean_session,
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
        session_id=clean_session,
        new_message=content,
    ):
        if event.is_final_response():
            if event.content and event.content.parts:
                for part in event.content.parts:
                    if part.text:
                        final += part.text
    return final


# ------------------------------------------------------------------
# Shared retry logic for agent calls
# ------------------------------------------------------------------

_MAX_ATTEMPTS = 3
_BACKOFF_DELAYS = [3, 6, 12]


async def _run_agent_with_retry(user_id: str, message: str) -> str | None:
    """
    Call _run_agent with exponential backoff on 429 rate limits.

    Returns the agent response text, or None if all retries failed.
    Raises non-retriable exceptions directly.
    """
    for attempt in range(_MAX_ATTEMPTS):
        try:
            return await _run_agent(user_id=user_id, message=message)
        except Exception as e:
            err_repr = f"{type(e).__name__}: {repr(e)}: {str(e)}".lower()
            is_rate_limit = any(k in err_repr for k in ["429", "resource_exhausted", "resourceexhausted"])
            if is_rate_limit:
                if attempt < _MAX_ATTEMPTS - 1:
                    delay = _BACKOFF_DELAYS[attempt]
                    logger.warning(
                        "Rate limit (429/ResourceExhausted) for %s (attempt %d/%d), retrying in %ds...",
                        user_id, attempt + 1, _MAX_ATTEMPTS, delay,
                    )
                    await asyncio.sleep(delay)
                    continue
                else:
                    logger.error("Rate limit exhausted for %s after %d attempts", user_id, _MAX_ATTEMPTS)
                    return None
            else:
                raise  # Non-retriable error
    return None


# ------------------------------------------------------------------
# WhatsApp message processing (runs in background)
# ------------------------------------------------------------------

async def _process_whatsapp_message(message_data: dict[str, Any]) -> None:
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
    text = await _build_whatsapp_text(phone, msg_type, message_data)
    if text is None:
        return

    # Run the agent
    await _send_agent_response(
        user_id=phone,
        message=text,
        send_fn=lambda msg: wa_client.send_text(phone, msg),
    )


async def _build_whatsapp_text(
    phone: str, msg_type: str, message_data: dict[str, Any]
) -> str | None:
    """Extract or build the text payload from a WhatsApp message. Returns None to skip."""
    if msg_type == "text":
        text = message_data.get("text", "")
        return text if text else None

    if msg_type == "image":
        image_id = message_data.get("image_id", "")
        caption = message_data.get("image_caption", "Analisa esta refeição.")
        if not image_id:
            return None
        try:
            image_bytes = await wa_client.download_media(image_id)
            from gym_coach.services import storage_client
            gs_uri = storage_client.upload_photo(phone, image_bytes)
            return f"{caption}\n\n[Foto guardada em: {gs_uri}]"
        except Exception:
            logger.exception("Failed to process image %s", image_id)
            await wa_client.send_text(
                phone,
                "⚠️ Desculpa, não consegui processar a imagem. Tenta novamente.",
            )
            return None

    # Unsupported type
    await wa_client.send_text(
        phone,
        "Por agora só consigo processar mensagens de texto e fotos 📸",
    )
    return None


# ------------------------------------------------------------------
# Telegram message processing (runs in background)
# ------------------------------------------------------------------

async def _process_telegram_message(message: dict[str, Any]) -> None:
    """Process a single Telegram message through the agent."""
    if tg_client is None:
        logger.error("Telegram client not initialised")
        return

    chat_id = message["chat"]["id"]
    user_id = f"telegram_{chat_id}"

    # Build message text
    text = await _build_telegram_text(user_id, chat_id, message)
    if text is None:
        return

    # Run the agent
    await _send_agent_response(
        user_id=user_id,
        message=text,
        send_fn=lambda msg: tg_client.send_text(chat_id, msg),
    )


async def _build_telegram_text(
    user_id: str, chat_id: int, message: dict[str, Any]
) -> str | None:
    """Extract or build the text payload from a Telegram message. Returns None to skip."""
    text = message.get("text")
    photo = message.get("photo")
    caption = message.get("caption", "Analisa esta refeição.")

    if text:
        # Handle commands
        if text.startswith("/"):
            if text == "/start":
                return "Olá! Quero começar a treinar e registar as minhas refeições."
            else:
                return text.lstrip("/")
        return text

    if photo:
        largest_photo = photo[-1]
        file_id = largest_photo["file_id"]
        try:
            image_bytes = await tg_client.download_file(file_id)
            from gym_coach.services import storage_client
            gs_uri = storage_client.upload_photo(user_id, image_bytes)
            return f"{caption}\n\n[Foto guardada em: {gs_uri}]"
        except Exception:
            logger.exception("Failed to process Telegram photo %s", file_id)
            await tg_client.send_text(
                chat_id,
                "⚠️ Desculpa, não consegui processar a imagem. Tenta novamente.",
            )
            return None

    # Unsupported type
    await tg_client.send_text(
        chat_id,
        "Por agora só consigo processar mensagens de texto e fotos 📸",
    )
    return None


# ------------------------------------------------------------------
# Shared: run agent and send response
# ------------------------------------------------------------------

async def _send_agent_response(
    user_id: str,
    message: str,
    send_fn,
) -> None:
    """
    Run the agent for a user message and send the response via send_fn.
    Handles retries, empty responses, and errors uniformly.
    """
    try:
        response = await _run_agent_with_retry(user_id=user_id, message=message)
    except Exception:
        logger.exception("Error running agent for %s", user_id)
        await send_fn("⚠️ Ocorreu um erro a processar a tua mensagem. Tenta novamente.")
        return

    if response is None:
        # Rate limit exhausted
        await send_fn("⏳ Muitas mensagens em simultâneo! Aguarda alguns segundos e tenta novamente.")
    elif response:
        await send_fn(response)
    else:
        logger.warning("Agent returned empty response for %s", user_id)
        await send_fn("🤔 Não consegui gerar uma resposta. Tenta reformular a mensagem.")
