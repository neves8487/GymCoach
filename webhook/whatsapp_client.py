"""
WhatsApp Cloud API client.

Handles sending messages (text, images) and downloading media
via the Meta Graph API v20.0.
"""

from __future__ import annotations

import logging
import os
from typing import Any

import httpx

logger = logging.getLogger(__name__)

GRAPH_API_BASE = "https://graph.facebook.com/v20.0"


class WhatsAppClient:
    """Async client for the WhatsApp Business Cloud API."""

    def __init__(
        self,
        token: str | None = None,
        phone_number_id: str | None = None,
    ) -> None:
        self._token = (token or os.getenv("WHATSAPP_TOKEN", "")).strip()
        self._phone_number_id = (phone_number_id or os.getenv("WHATSAPP_PHONE_NUMBER_ID", "")).strip()
        self._base_url = f"{GRAPH_API_BASE}/{self._phone_number_id}/messages"
        self._headers = {
            "Authorization": f"Bearer {self._token}",
            "Content-Type": "application/json",
        }

    # ------------------------------------------------------------------
    # Sending messages
    # ------------------------------------------------------------------

    async def send_text(self, to: str, message: str) -> dict[str, Any]:
        """
        Send a text message. Auto-splits at 4096 chars (WhatsApp limit).
        """
        max_len = 4096
        chunks = [message[i : i + max_len] for i in range(0, len(message), max_len)]
        last_response: dict[str, Any] = {}

        async with httpx.AsyncClient(timeout=30) as client:
            for i, chunk in enumerate(chunks):
                payload = {
                    "messaging_product": "whatsapp",
                    "recipient_type": "individual",
                    "to": to,
                    "type": "text",
                    "text": {"preview_url": False, "body": chunk},
                }
                response = await client.post(
                    self._base_url, headers=self._headers, json=payload,
                )
                response.raise_for_status()
                last_response = response.json()
                logger.info("Message sent to %s (%d/%d)", to, i + 1, len(chunks))

        return last_response

    async def send_image(
        self, to: str, image_url: str, caption: str = ""
    ) -> dict[str, Any]:
        """Send an image message via URL."""
        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": to,
            "type": "image",
            "image": {"link": image_url, "caption": caption},
        }
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(
                self._base_url, headers=self._headers, json=payload,
            )
            response.raise_for_status()
            return response.json()

    # ------------------------------------------------------------------
    # Downloading media
    # ------------------------------------------------------------------

    async def download_media(self, media_id: str) -> bytes:
        """
        Download media from WhatsApp (two-step: get URL, then download).
        """
        async with httpx.AsyncClient(timeout=60) as client:
            # Step 1: Get media URL
            url_resp = await client.get(
                f"{GRAPH_API_BASE}/{media_id}",
                headers={"Authorization": f"Bearer {self._token}"},
            )
            url_resp.raise_for_status()
            media_url = url_resp.json()["url"]

            # Step 2: Download binary
            media_resp = await client.get(
                media_url,
                headers={"Authorization": f"Bearer {self._token}"},
            )
            media_resp.raise_for_status()
            logger.info("Downloaded media %s (%d bytes)", media_id, len(media_resp.content))
            return media_resp.content

    # ------------------------------------------------------------------
    # Read receipts
    # ------------------------------------------------------------------

    async def mark_as_read(self, message_id: str) -> None:
        """Send a read receipt."""
        payload = {
            "messaging_product": "whatsapp",
            "status": "read",
            "message_id": message_id,
        }
        async with httpx.AsyncClient(timeout=10) as client:
            await client.post(
                self._base_url, headers=self._headers, json=payload,
            )
