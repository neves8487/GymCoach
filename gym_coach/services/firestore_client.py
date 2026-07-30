"""
Firestore client — CRUD for users, workouts, and meals.

Collections:
  users/{phone}
  users/{phone}/treinos/{treino_id}
  users/{phone}/refeicoes/{refeicao_id}
  users/{phone}/planos_treino/{dia_semana}
  users/{phone}/treinos_prescritos/{data_YYYY-MM-DD}
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
    deleted = {"treinos": 0, "refeicoes": 0, "planos_treino": 0, "treinos_prescritos": 0}

    for sub in ("treinos", "refeicoes", "planos_treino", "treinos_prescritos"):
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


# =====================================================================
# Workout Plans (planos_treino)
# =====================================================================

def save_workout_plan(phone: str, dia_semana: str, plan_data: dict[str, Any]) -> str:
    """
    Save or update a planned workout for a specific day of the week or split name.
    Collection: users/{phone}/planos_treino/{dia_semana_clean}
    """
    dia_clean = str(dia_semana).lower().strip()
    plan_data["dia_semana"] = dia_clean
    plan_data["updated_at"] = datetime.utcnow().isoformat()

    ref = (
        _get_db()
        .collection("users")
        .document(phone)
        .collection("planos_treino")
        .document(dia_clean)
    )
    ref.set(plan_data, merge=True)
    logger.info("Workout plan saved for %s on %s", phone, dia_clean)
    return dia_clean


def get_workout_plan(phone: str, dia_semana: str | None = None) -> list[dict[str, Any]]:
    """
    Fetch workout plan(s). If dia_semana is provided, fetches that specific plan.
    Otherwise returns all saved workout plans for the user.
    """
    user_ref = _get_db().collection("users").document(phone).collection("planos_treino")
    if dia_semana:
        dia_clean = str(dia_semana).lower().strip()
        doc = user_ref.document(dia_clean).get()
        if doc.exists:
            d = doc.to_dict()
            d["id"] = doc.id
            return [d]
        return []

    docs = list(user_ref.stream())
    results = []
    for doc in docs:
        d = doc.to_dict()
        d["id"] = doc.id
        results.append(d)
    return results


def delete_workout_plan(phone: str, dia_semana: str) -> None:
    """Delete a workout plan for a specific day."""
    dia_clean = str(dia_semana).lower().strip()
    _get_db().collection("users").document(phone).collection("planos_treino").document(dia_clean).delete()
    logger.info("Workout plan %s deleted for %s", dia_clean, phone)


# =====================================================================
# Prescribed Workouts (treinos_prescritos)
# =====================================================================

def save_prescribed_workout(phone: str, workout_data: dict[str, Any]) -> str:
    """
    Save the workout prescribed by the agent for a specific date.
    Collection: users/{phone}/treinos_prescritos/{YYYY-MM-DD}
    Overwrites any previous prescription for the same date.
    """
    data_str = workout_data.get("data") or datetime.utcnow().strftime("%Y-%m-%d")
    workout_data["data"] = data_str
    workout_data["created_at"] = datetime.utcnow().isoformat()

    ref = (
        _get_db()
        .collection("users")
        .document(phone)
        .collection("treinos_prescritos")
        .document(data_str)
    )
    ref.set(workout_data)
    logger.info("Prescribed workout saved for %s on %s", phone, data_str)
    return data_str


def get_prescribed_workout(
    phone: str, data: str | None = None
) -> dict[str, Any] | None:
    """
    Fetch the prescribed workout for a specific date.
    Defaults to today if no date is provided.
    """
    if data is None:
        data = datetime.utcnow().strftime("%Y-%m-%d")

    doc = (
        _get_db()
        .collection("users")
        .document(phone)
        .collection("treinos_prescritos")
        .document(data)
        .get()
    )
    if doc.exists:
        d = doc.to_dict()
        d["id"] = doc.id
        return d
    return None


# =====================================================================
# Clinical Notes (notas_clinicas — stored in user profile)
# =====================================================================

def add_nota_clinica(phone: str, descricao: str) -> dict[str, Any]:
    """
    Add a clinical note (injury, pain, medical restriction) to the user profile.
    Stored as a list of dicts in the 'notas_clinicas' field.
    """
    profile = get_user(phone) or {}
    notas = profile.get("notas_clinicas", [])
    if not isinstance(notas, list):
        notas = []

    nova_nota = {
        "descricao": descricao,
        "data": datetime.utcnow().strftime("%Y-%m-%d"),
        "ativo": True,
    }
    notas.append(nova_nota)
    upsert_user(phone, {"notas_clinicas": notas})
    logger.info("Clinical note added for %s: %s", phone, descricao)
    return nova_nota


def get_notas_clinicas(phone: str, apenas_ativas: bool = True) -> list[dict[str, Any]]:
    """
    Get clinical notes for a user. By default returns only active notes.
    """
    profile = get_user(phone) or {}
    notas = profile.get("notas_clinicas", [])
    if not isinstance(notas, list):
        return []
    if apenas_ativas:
        return [n for n in notas if n.get("ativo", True)]
    return notas
