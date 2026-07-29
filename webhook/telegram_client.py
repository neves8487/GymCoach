"""
Telegram Bot API client.

Handles sending text messages and downloading files from Telegram.
"""

from __future__ import annotations

import logging
import os
from typing import Any

import httpx

logger = logging.getLogger(__name__)


class TelegramClient:
    """Async client for the Telegram Bot API."""

    def __init__(self, token: str | None = None) -> None:
        self._token = (token or os.getenv("TELEGRAM_TOKEN", "")).strip()
        self._base_url = f"https://api.telegram.org/bot{self._token}"
        self._file_url = f"https://api.telegram.org/file/bot{self._token}"

    async def send_text(self, chat_id: int, message: str) -> dict[str, Any]:
        """
        Send a text message back to Telegram. Auto-splits at 4096 chars.
        """
        max_len = 4096
        chunks = [message[i : i + max_len] for i in range(0, len(message), max_len)]
        last_response: dict[str, Any] = {}

        async with httpx.AsyncClient(timeout=30) as client:
            for i, chunk in enumerate(chunks):
                payload = {
                    "chat_id": chat_id,
                    "text": chunk,
                }
                response = await client.post(
                    f"{self._base_url}/sendMessage",
                    json=payload,
                )
                response.raise_for_status()
                last_response = response.json()
                logger.info("Telegram message sent to %s (%d/%d)", chat_id, i + 1, len(chunks))

        return last_response

    async def download_file(self, file_id: str) -> bytes:
        """
        Download a file from Telegram (two-step: get path, then download binary).
        """
        async with httpx.AsyncClient(timeout=60) as client:
            # Step 1: Get file path
            url = f"{self._base_url}/getFile"
            resp = await client.get(url, params={"file_id": file_id})
            resp.raise_for_status()
            file_path = resp.json()["result"]["file_path"]

            # Step 2: Download binary
            download_url = f"{self._file_url}/{file_path}"
            file_resp = await client.get(download_url)
            file_resp.raise_for_status()
            logger.info("Downloaded Telegram file %s (%d bytes)", file_id, len(file_resp.content))
            return file_resp.content
