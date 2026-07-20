"""
Firestore client — CRUD for users, workouts, and meals.

Collections:
  users/{phone}
  users/{phone}/treinos/{treino_id}
  users/{phone}/refeicoes/{refeicao_id}
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta
from typing import Any

from google.cloud import firestore  # type: ignore[import-untyped]

logger = logging.getLogger(__name__)

# Singleton — initialised on first call
_db: firestore.Client | None = None


def _get_db() -> firestore.Client:
    """Lazy-init Firestore client."""
    global _db
    if _db is None:
        project = os.getenv("GOOGLE_CLOUD_PROJECT")
        _db = firestore.Client(project=project)
    return _db


# =====================================================================
# Users
# =====================================================================

def get_user(phone: str) -> dict[str, Any] | None:
    """Fetch user profile. Returns None if not found."""
    doc = _get_db().collection("users").document(phone).get()
    if doc.exists:
        data = doc.to_dict()
        data["phone"] = doc.id
        return data
    return None


def upsert_user(phone: str, data: dict[str, Any]) -> None:
    """Create or merge-update a user profile."""
    data["updated_at"] = datetime.utcnow().isoformat()
    if "created_at" not in data:
        data["created_at"] = data["updated_at"]
    _get_db().collection("users").document(phone).set(data, merge=True)
    logger.info("User %s upserted", phone)


def delete_all_user_data(phone: str) -> dict[str, int]:
    """
    Delete user + all sub-collections (RGPD).
    Returns count of deleted documents.
    """
    db = _get_db()
    user_ref = db.collection("users").document(phone)
    deleted = {"treinos": 0, "refeicoes": 0}

    for sub in ("treinos", "refeicoes"):
        docs = list(user_ref.collection(sub).stream())
        for doc in docs:
            doc.reference.delete()
            deleted[sub] += 1

    user_ref.delete()
    logger.info("Deleted all data for %s: %s", phone, deleted)
    return deleted


# =====================================================================
# Workouts
# =====================================================================

def add_workout(phone: str, entry: dict[str, Any]) -> str:
    """Add a workout entry. Returns the generated document ID."""
    if "data" not in entry:
        entry["data"] = datetime.utcnow().isoformat()
    ref = (
        _get_db()
        .collection("users")
        .document(phone)
        .collection("treinos")
        .document()
    )
    ref.set(entry)
    logger.info("Workout added for %s: %s", phone, entry.get("exercicio", "?"))
    return ref.id


def get_recent_workouts(
    phone: str,
    exercicio: str | None = None,
    limit: int = 10,
) -> list[dict[str, Any]]:
    """
    Get most recent workouts. Optionally filter by exercise.
    """
    query = (
        _get_db()
        .collection("users")
        .document(phone)
        .collection("treinos")
        .order_by("data", direction=firestore.Query.DESCENDING)
    )
    if exercicio:
        query = query.where(filter=firestore.FieldFilter("exercicio", "==", exercicio))
    query = query.limit(limit)

    results = []
    for doc in query.stream():
        d = doc.to_dict()
        d["id"] = doc.id
        results.append(d)
    return results


# =====================================================================
# Meals
# =====================================================================

def add_meal(phone: str, entry: dict[str, Any]) -> str:
    """Add a meal entry. Returns the generated document ID."""
    if "data" not in entry:
        entry["data"] = datetime.utcnow().isoformat()
    if "confirmado" not in entry:
        entry["confirmado"] = False
    ref = (
        _get_db()
        .collection("users")
        .document(phone)
        .collection("refeicoes")
        .document()
    )
    ref.set(entry)
    logger.info("Meal added for %s", phone)
    return ref.id


def get_daily_meals(phone: str, date: str | None = None) -> list[dict[str, Any]]:
    """
    Get all meals for a specific day.
    date format: "YYYY-MM-DD". Defaults to today.
    """
    if date is None:
        date = datetime.utcnow().strftime("%Y-%m-%d")

    start = f"{date}T00:00:00"
    end = f"{date}T23:59:59"

    query = (
        _get_db()
        .collection("users")
        .document(phone)
        .collection("refeicoes")
        .where(filter=firestore.FieldFilter("data", ">=", start))
        .where(filter=firestore.FieldFilter("data", "<=", end))
        .order_by("data")
    )

    results = []
    for doc in query.stream():
        d = doc.to_dict()
        d["id"] = doc.id
        results.append(d)
    return results


def get_weekly_meals(phone: str) -> list[dict[str, Any]]:
    """Get all meals from the last 7 days."""
    start = (datetime.utcnow() - timedelta(days=7)).isoformat()

    query = (
        _get_db()
        .collection("users")
        .document(phone)
        .collection("refeicoes")
        .where(filter=firestore.FieldFilter("data", ">=", start))
        .order_by("data")
    )

    results = []
    for doc in query.stream():
        d = doc.to_dict()
        d["id"] = doc.id
        results.append(d)
    return results


def confirm_meal(phone: str, meal_id: str) -> None:
    """Mark a meal as confirmed by the user."""
    (
        _get_db()
        .collection("users")
        .document(phone)
        .collection("refeicoes")
        .document(meal_id)
        .update({"confirmado": True})
    )
    logger.info("Meal %s confirmed for %s", meal_id, phone)
