"""
Backend Webhook — Retry Helper com Backoff Exponencial.

Proporciona utilitários síncronos e assíncronos para tratar erros de
Rate Limit (HTTP 429, ResourceExhausted, Quota Exceeded) ao comunicar
com as APIs do Vertex AI Agent Engine no servidor Backend.
"""

from __future__ import annotations

import asyncio
import logging
import random
import time
from typing import Any, Callable, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")


def is_rate_limit_error(exc: Exception) -> bool:
    """Verifica se a exceção é um erro de rate limit (429, ResourceExhausted, Quota)."""
    exc_str = str(exc).lower()
    if any(
        term in exc_str
        for term in [
            "429",
            "resource_exhausted",
            "resourceexhausted",
            "quota",
            "too many requests",
            "rate limit",
            "ratelimit",
        ]
    ):
        return True
    if hasattr(exc, "code") and getattr(exc, "code") in (429, 503):
        return True
    if hasattr(exc, "status_code") and getattr(exc, "status_code") in (429, 503):
        return True
    return False


def retry_sync_with_backoff(
    func: Callable[[], T],
    max_retries: int = 3,
    initial_delay: float = 2.0,
    backoff_factor: float = 2.0,
) -> T:
    """Executa uma função síncrona com retry e backoff exponencial em caso de erro 429 / Rate Limit."""
    delay = initial_delay
    for attempt in range(1, max_retries + 1):
        try:
            return func()
        except Exception as e:
            if attempt == max_retries or not is_rate_limit_error(e):
                raise
            jitter = random.uniform(0, 0.5)
            sleep_time = delay + jitter
            logger.warning(
                "Rate limit (429) detetado no Backend (tentativa %d/%d). Aguardando %.2fs... Erro: %s",
                attempt,
                max_retries,
                sleep_time,
                e,
            )
            time.sleep(sleep_time)
            delay *= backoff_factor
    raise RuntimeError("Unreachable")


async def retry_async_with_backoff(
    coro_func: Callable[[], Any],
    max_retries: int = 3,
    initial_delay: float = 2.0,
    backoff_factor: float = 2.0,
) -> Any:
    """Executa uma função assíncrona com retry e backoff exponencial em caso de erro 429 / Rate Limit."""
    delay = initial_delay
    for attempt in range(1, max_retries + 1):
        try:
            return await coro_func()
        except Exception as e:
            if attempt == max_retries or not is_rate_limit_error(e):
                raise
            jitter = random.uniform(0, 0.5)
            sleep_time = delay + jitter
            logger.warning(
                "Rate limit (429) detetado no Backend (tentativa %d/%d async). Aguardando %.2fs... Erro: %s",
                attempt,
                max_retries,
                sleep_time,
                e,
            )
            await asyncio.sleep(sleep_time)
            delay *= backoff_factor
    raise RuntimeError("Unreachable")
