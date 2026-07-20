"""
PT Agent tools — workout history, logging, and progression.

These are Python functions that ADK exposes as tools to the PT agent.
ADK auto-generates the tool schema from the function signature + docstring.
"""

from __future__ import annotations

from google.adk.tools import ToolContext

from gym_coach.services import firestore_client as db


def get_historico_exercicio(
    exercicio: str,
    ultimas_n: int,
    tool_context: ToolContext,
) -> dict:
    """
    Obtém as últimas N sessões de um exercício específico do histórico do utilizador.
    Usa esta tool antes de sugerir pesos para garantir que as recomendações
    são baseadas em dados reais.

    Args:
        exercicio: Nome do exercício (ex: 'agachamento', 'banco', 'terra',
                   'press_militar', 'remada', 'romeno').
        ultimas_n: Número de sessões a retornar (recomendado: 3-5).
    """
    user_phone = tool_context.state.get("user_phone", "")
    if not user_phone:
        return {"error": "Número de telefone não disponível."}

    workouts = db.get_recent_workouts(
        phone=user_phone,
        exercicio=exercicio,
        limit=ultimas_n,
    )

    if not workouts:
        return {
            "exercicio": exercicio,
            "sessoes": [],
            "nota": f"Sem histórico para '{exercicio}'. Pergunta ao utilizador por onde começar.",
        }

    return {
        "exercicio": exercicio,
        "total_sessoes": len(workouts),
        "sessoes": workouts,
    }


def registar_treino(
    exercicio: str,
    series: list[dict],
    notas: str,
    dor_reportada: bool,
    tool_context: ToolContext,
) -> dict:
    """
    Regista os resultados de uma sessão de treino no Firestore.

    Args:
        exercicio: Nome do exercício (ex: 'agachamento', 'banco', 'terra').
        series: Lista de séries realizadas. Cada série é um dicionário com:
                - peso (float): peso em kg
                - reps (int): repetições completadas
                - rpe (float, opcional): RPE de 6 a 10
                - falhou (bool): se a série foi falhada/incompleta
                Exemplo: [{"peso": 140, "reps": 5, "rpe": 8.5, "falhou": false}]
        notas: Notas livres do utilizador sobre a sessão.
        dor_reportada: True se o utilizador reportou dor durante o exercício.
    """
    user_phone = tool_context.state.get("user_phone", "")
    if not user_phone:
        return {"error": "Número de telefone não disponível."}

    entry = {
        "exercicio": exercicio,
        "series": series,
        "notas": notas,
        "dor_reportada": dor_reportada,
    }

    doc_id = db.add_workout(user_phone, entry)

    # Analyse for progression decisions
    analysis = _analyse_session(series, dor_reportada)

    return {
        "status": "registado",
        "treino_id": doc_id,
        "exercicio": exercicio,
        "analise": analysis,
    }


def _analyse_session(series: list[dict], dor: bool) -> dict:
    """Quick analysis of a session for the agent to use in its response."""
    if not series:
        return {"nota": "Sem séries registadas."}

    total_sets = len(series)
    failed_sets = sum(1 for s in series if s.get("falhou", False))
    rpes = [s["rpe"] for s in series if s.get("rpe") is not None]
    max_weight = max((s.get("peso", 0) for s in series), default=0)

    result: dict = {
        "total_series": total_sets,
        "series_falhadas": failed_sets,
        "peso_maximo": max_weight,
    }

    if rpes:
        avg_rpe = sum(rpes) / len(rpes)
        last_rpe = rpes[-1]
        result["rpe_medio"] = round(avg_rpe, 1)
        result["rpe_ultimo_set"] = last_rpe

        # Progression suggestion
        if dor:
            result["sugestao"] = "REDUZIR — dor reportada. Não subir carga."
        elif failed_sets > 0:
            result["sugestao"] = "REDUZIR 5-10% — houve falha."
        elif last_rpe < 8:
            result["sugestao"] = "SUBIR peso na próxima sessão."
        elif last_rpe <= 9:
            result["sugestao"] = "MANTER peso na próxima sessão."
        else:
            result["sugestao"] = "REDUZIR 5-10% — RPE muito alto."
    elif dor:
        result["sugestao"] = "REDUZIR — dor reportada."
    elif failed_sets > 0:
        result["sugestao"] = "REDUZIR 5-10% — houve falha."

    return result
