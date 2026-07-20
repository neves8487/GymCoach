"""
WhatsApp webhook signature validation.

Every incoming webhook request from Meta includes an X-Hub-Signature-256
header. We verify it using HMAC-SHA256 with the app secret to ensure
the request genuinely comes from Meta.
"""

from __future__ import annotations

import hashlib
import hmac


def verify_signature(payload: bytes, signature: str, app_secret: str) -> bool:
    """
    Validate the X-Hub-Signature-256 header.

    Args:
        payload: Raw request body bytes.
        signature: Value of X-Hub-Signature-256 header (e.g. "sha256=abc123...").
        app_secret: The WhatsApp app secret.

    Returns:
        True if signature is valid.
    """
    if not signature or not signature.startswith("sha256="):
        return False

    expected = signature[7:]  # Strip "sha256=" prefix
    computed = hmac.new(
        key=app_secret.encode("utf-8"),
        msg=payload,
        digestmod=hashlib.sha256,
    ).hexdigest()

    return hmac.compare_digest(computed, expected)
