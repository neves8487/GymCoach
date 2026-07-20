"""
Cloud Storage client — upload and manage meal photos.

Bucket structure: gs://{bucket}/{phone}/{timestamp}.jpg
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta

from google.cloud import storage  # type: ignore[import-untyped]

logger = logging.getLogger(__name__)

_client: storage.Client | None = None
_bucket_name: str | None = None


def _get_bucket() -> storage.Bucket:
    """Lazy-init Cloud Storage bucket."""
    global _client, _bucket_name
    if _client is None:
        project = os.getenv("GOOGLE_CLOUD_PROJECT")
        _client = storage.Client(project=project)
        _bucket_name = os.getenv("GCS_BUCKET_NAME", "fotos-refeicoes")
    return _client.bucket(_bucket_name)


def upload_photo(phone: str, image_data: bytes) -> str:
    """
    Upload a meal photo.

    Returns:
        The gs:// URI of the uploaded file.
    """
    bucket = _get_bucket()
    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    blob_name = f"{phone}/{timestamp}.jpg"
    blob = bucket.blob(blob_name)

    blob.upload_from_string(image_data, content_type="image/jpeg")
    gs_uri = f"gs://{bucket.name}/{blob_name}"
    logger.info("Photo uploaded: %s", gs_uri)
    return gs_uri


def get_signed_url(gs_uri: str, expiration_minutes: int = 60) -> str:
    """Generate a temporary signed URL for a photo."""
    bucket = _get_bucket()
    # Parse: gs://bucket-name/path → path
    prefix = f"gs://{bucket.name}/"
    blob_name = gs_uri[len(prefix):]
    blob = bucket.blob(blob_name)

    url = blob.generate_signed_url(
        expiration=timedelta(minutes=expiration_minutes),
        method="GET",
    )
    return url


def delete_user_photos(phone: str) -> int:
    """Delete all photos for a user (RGPD). Returns count deleted."""
    bucket = _get_bucket()
    blobs = list(bucket.list_blobs(prefix=f"{phone}/"))
    for blob in blobs:
        blob.delete()
    logger.info("Deleted %d photos for %s", len(blobs), phone)
    return len(blobs)
