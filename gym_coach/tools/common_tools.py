"""
Common tools — shared across agents.

Tools for user profile management and RGPD data deletion.
ADK automatically injects ToolContext when the parameter is present.
"""

from __future__ import annotations

from google.adk.tools import ToolContext

from gym_coach.services import firestore_client as db


def get_perfil(tool_context: ToolContext) -> dict:
    """
    Obtém o perfil completo do utilizador atual.
    Retorna os dados do perfil incluindo nome, peso, altura, objetivo, 1RMs, e metas nutricionais.
    Se o utilizador não tiver perfil, retorna uma indicação de que precisa de fazer onboarding.
    """
    user_phone = tool_context.state.get("user_phone", "")
    if not user_phone:
        return {"error": "Número de telefone não disponível no estado da sessão."}

    profile = db.get_user(user_phone)
    if profile is None:
        return {
            "existe": False,
            "mensagem": "Utilizador não tem perfil. Precisa de fazer onboarding.",
        }

    return {"existe": True, "perfil": profile}


def atualizar_perfil(
    campo: str,
    valor: str,
    tool_context: ToolContext,
) -> dict:
    """
    Atualiza um campo específico do perfil do utilizador.

    Args:
        campo: Nome do campo a atualizar. Valores possíveis:
               'nome', 'peso_corporal', 'altura', 'objetivo',
               'calorias_alvo', 'preferencias_alimentares', 'alergias'.
               Para 1RMs usar formato 'one_rm.agachamento', 'one_rm.banco', 'one_rm.terra'.
               Para macros usar formato 'macros_alvo.proteina', 'macros_alvo.hidratos', 'macros_alvo.gordura'.
        valor: O novo valor para o campo (será convertido para o tipo adequado).
    """
    user_phone = tool_context.state.get("user_phone", "")
    if not user_phone:
        return {"error": "Número de telefone não disponível."}

    # Handle nested fields (e.g., "one_rm.agachamento")
    if "." in campo:
        parts = campo.split(".", 1)
        parent = parts[0]
        child = parts[1]

        # Get existing data for the parent field
        profile = db.get_user(user_phone) or {}
        parent_data = profile.get(parent, {})
        if not isinstance(parent_data, dict):
            parent_data = {}

        # Try to convert to float for numeric fields
        try:
            parent_data[child] = float(valor)
        except (ValueError, TypeError):
            parent_data[child] = valor

        db.upsert_user(user_phone, {parent: parent_data})
    else:
        # Simple field update — try numeric conversion
        try:
            converted = float(valor)
            # Keep as int if it's a whole number
            if converted == int(converted):
                converted = int(converted)
            db.upsert_user(user_phone, {campo: converted})
        except (ValueError, TypeError):
            db.upsert_user(user_phone, {campo: valor})

    return {"status": "ok", "campo": campo, "valor": valor}


def apagar_dados(confirmar: bool, tool_context: ToolContext) -> dict:
    """
    Apaga TODOS os dados do utilizador (perfil, treinos, refeições, fotos).
    Conformidade com RGPD. Esta ação é irreversível.

    Args:
        confirmar: Deve ser True para confirmar a eliminação. Se False, retorna aviso.
    """
    user_phone = tool_context.state.get("user_phone", "")
    if not user_phone:
        return {"error": "Número de telefone não disponível."}

    if not confirmar:
        return {
            "status": "pendente",
            "mensagem": "Para confirmar a eliminação de todos os teus dados, "
            "diz explicitamente que queres apagar.",
        }

    # Delete Firestore data
    deleted = db.delete_all_user_data(user_phone)

    # Delete photos from Cloud Storage
    try:
        from gym_coach.services import storage_client as storage
        photos_deleted = storage.delete_user_photos(user_phone)
        deleted["fotos"] = photos_deleted
    except Exception:
        deleted["fotos"] = "erro ao eliminar fotos"

    return {
        "status": "eliminado",
        "dados_apagados": deleted,
        "mensagem": "Todos os teus dados foram eliminados permanentemente.",
    }
