"""
Nutrition Agent tools — meal logging, daily/weekly summaries.

These are Python functions that ADK exposes as tools to the nutrition agent.
"""

from __future__ import annotations

from google.adk.tools import ToolContext

from gym_coach.services import firestore_client as db


def registar_refeicao(
    descricao: str,
    alimentos: list[dict],
    calorias_estimadas: float,
    proteina: float,
    hidratos: float,
    gordura: float,
    foto_url: str,
    micronutrientes: dict,
    tool_context: ToolContext,
) -> dict:
    """
    Regista uma refeição analisada no Firestore.

    Args:
        descricao: Descrição breve da refeição (ex: "Almoço — frango com arroz e salada").
        alimentos: Lista de alimentos identificados. Cada item é um dicionário com:
                   - nome (str): nome do alimento
                   - quantidade_g (float): quantidade estimada em gramas
                   - calorias (float): calorias estimadas
                   - proteina (float): proteína em gramas
                   - hidratos (float): hidratos de carbono em gramas
                   - gordura (float): gordura em gramas
        calorias_estimadas: Total de calorias estimadas para a refeição.
        proteina: Total de proteína em gramas.
        hidratos: Total de hidratos de carbono em gramas.
        gordura: Total de gordura em gramas.
        foto_url: URL da foto no Cloud Storage (gs://...), ou string vazia se não houver foto.
        micronutrientes: Dicionário com micronutrientes estimados (ex: {"ferro_mg": 3.5, "vitamina_c_mg": 45}).
                         Pode estar vazio se não aplicável.
    """
    user_phone = tool_context.state.get("user_phone", "")
    if not user_phone:
        return {"error": "Número de telefone não disponível."}

    entry = {
        "descricao": descricao,
        "alimentos": alimentos,
        "calorias_estimadas": calorias_estimadas,
        "proteina": proteina,
        "hidratos": hidratos,
        "gordura": gordura,
        "foto_url": foto_url if foto_url else None,
        "micronutrientes": micronutrientes if micronutrientes else None,
        "margem_erro": "±15-20%",
        "confirmado": False,
    }

    doc_id = db.add_meal(user_phone, entry)

    return {
        "status": "registado",
        "refeicao_id": doc_id,
        "resumo": {
            "calorias": calorias_estimadas,
            "proteina": proteina,
            "hidratos": hidratos,
            "gordura": gordura,
        },
    }


def get_resumo_diario(
    data: str,
    tool_context: ToolContext,
) -> dict:
    """
    Obtém o resumo nutricional do dia: total de calorias e macronutrientes.

    Args:
        data: Data no formato "YYYY-MM-DD". Usa a data de hoje se não especificada.
              Exemplo: "2025-07-20".
    """
    user_phone = tool_context.state.get("user_phone", "")
    if not user_phone:
        return {"error": "Número de telefone não disponível."}

    meals = db.get_daily_meals(user_phone, date=data if data else None)

    if not meals:
        return {
            "data": data,
            "total_refeicoes": 0,
            "mensagem": "Sem refeições registadas para este dia.",
        }

    total_cal = sum(m.get("calorias_estimadas", 0) for m in meals)
    total_prot = sum(m.get("proteina", 0) for m in meals)
    total_carb = sum(m.get("hidratos", 0) for m in meals)
    total_fat = sum(m.get("gordura", 0) for m in meals)

    # Get user targets for comparison
    profile = db.get_user(user_phone) or {}
    targets = {
        "calorias_alvo": profile.get("calorias_alvo"),
        "macros_alvo": profile.get("macros_alvo"),
    }

    return {
        "data": data,
        "total_refeicoes": len(meals),
        "totais": {
            "calorias": round(total_cal),
            "proteina": round(total_prot, 1),
            "hidratos": round(total_carb, 1),
            "gordura": round(total_fat, 1),
        },
        "metas": targets,
        "refeicoes": [
            {
                "descricao": m.get("descricao", ""),
                "calorias": m.get("calorias_estimadas", 0),
                "confirmado": m.get("confirmado", False),
            }
            for m in meals
        ],
    }


def get_resumo_semanal(tool_context: ToolContext) -> dict:
    """
    Obtém o resumo nutricional da última semana: médias diárias de calorias e macros.
    Útil para avaliar tendências e aderência ao plano alimentar.
    """
    user_phone = tool_context.state.get("user_phone", "")
    if not user_phone:
        return {"error": "Número de telefone não disponível."}

    meals = db.get_weekly_meals(user_phone)

    if not meals:
        return {
            "total_refeicoes": 0,
            "mensagem": "Sem refeições registadas nos últimos 7 dias.",
        }

    total_cal = sum(m.get("calorias_estimadas", 0) for m in meals)
    total_prot = sum(m.get("proteina", 0) for m in meals)
    total_carb = sum(m.get("hidratos", 0) for m in meals)
    total_fat = sum(m.get("gordura", 0) for m in meals)

    # Group by day for daily averages
    days: set[str] = set()
    for m in meals:
        data_str = m.get("data", "")
        if isinstance(data_str, str) and len(data_str) >= 10:
            days.add(data_str[:10])

    num_days = max(len(days), 1)

    # Get user targets
    profile = db.get_user(user_phone) or {}
    targets = {
        "calorias_alvo": profile.get("calorias_alvo"),
        "macros_alvo": profile.get("macros_alvo"),
    }

    return {
        "periodo": "últimos 7 dias",
        "dias_com_registos": num_days,
        "total_refeicoes": len(meals),
        "totais_semana": {
            "calorias": round(total_cal),
            "proteina": round(total_prot, 1),
            "hidratos": round(total_carb, 1),
            "gordura": round(total_fat, 1),
        },
        "medias_diarias": {
            "calorias": round(total_cal / num_days),
            "proteina": round(total_prot / num_days, 1),
            "hidratos": round(total_carb / num_days, 1),
            "gordura": round(total_fat / num_days, 1),
        },
        "metas": targets,
    }


def get_metas_nutricionais(tool_context: ToolContext) -> dict:
    """
    Obtém as metas nutricionais do utilizador (calorias alvo e macros alvo).
    Útil para comparar com o consumo atual.
    """
    user_phone = tool_context.state.get("user_phone", "")
    if not user_phone:
        return {"error": "Número de telefone não disponível."}

    profile = db.get_user(user_phone)
    if profile is None:
        return {"metas_definidas": False, "mensagem": "Sem perfil. Precisa de onboarding."}

    calorias = profile.get("calorias_alvo")
    macros = profile.get("macros_alvo")

    if not calorias and not macros:
        return {
            "metas_definidas": False,
            "mensagem": "Utilizador não tem metas nutricionais definidas. Sugerir definir.",
        }

    return {
        "metas_definidas": True,
        "calorias_alvo": calorias,
        "macros_alvo": macros,
        "preferencias": profile.get("preferencias_alimentares", []),
        "alergias": profile.get("alergias", []),
    }
