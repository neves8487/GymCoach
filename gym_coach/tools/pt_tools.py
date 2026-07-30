"""
PT Agent tools — workout history, logging, and progression.

These are Python functions that ADK exposes as tools to the PT agent.
ADK auto-generates the tool schema from the function signature + docstring.
"""

from __future__ import annotations

from google.adk.tools import ToolContext

from gym_coach.services import firestore_client as db


def obter_contexto_completo_pt(
    tool_context: ToolContext,
    exercicio: str | None = None,
) -> dict:
    """
    Obtém num ÚNICO passo todo o contexto do utilizador para prescrição de treino:
    - Perfil e 1RMs (agachamento, supino, terra)
    - Notas clínicas e lesões/dores ativas
    - Histórico recente de treinos

    Usa esta tool como PRIMEIRO PASSO para prescrever treino para máxima eficiência.
    """
    user_phone = tool_context.state.get("user_phone", "")
    if not user_phone:
        return {"error": "Número de telefone não disponível."}

    profile = db.get_user(user_phone) or {}
    notas = db.get_notas_clinicas(user_phone)
    workouts = db.get_recent_workouts(phone=user_phone, exercicio=exercicio, limit=5)

    return {
        "perfil": profile,
        "1rms": profile.get("one_rm", {}),
        "notas_clinicas_lesoes": notas,
        "historico_recente": workouts,
    }


def get_historico_exercicio(
    tool_context: ToolContext,
    exercicio: str | None = None,
    ultimas_n: int = 5,
) -> dict:
    """
    Obtém as últimas N sessões de treino do histórico do utilizador.

    Usa esta tool para consultar o histórico antes de sugerir pesos ou quando o
    utilizador pergunta pelo seu último treino ou histórico recente.

    Args:
        exercicio: Nome do exercício opcional (ex: 'agachamento', 'banco', 'terra', 'remada').
                   Se omitido ou None, retorna as sessões de treino mais recentes de QUALQUER exercício
                   (permitindo consultar o último treino completo ou sessões por grupo muscular).
        ultimas_n: Número de sessões a retornar (padrão: 5, recomendado: 3-10).
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
        nota = f"Sem histórico para '{exercicio}'." if exercicio else "Sem histórico de treinos registados."
        return {
            "exercicio": exercicio,
            "sessoes": [],
            "nota": nota,
        }

    return {
        "exercicio": exercicio or "todos",
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


def guardar_plano_treino(
    dia_semana: str,
    nome_treino: str,
    exercicios: list[dict],
    notas: str = "",
    tool_context: ToolContext | None = None,
) -> dict:
    """
    Guarda ou atualiza o plano de treino estruturado para um dia da semana (ex: 'segunda', 'terca',
    'quarta', 'quinta', 'sexta', 'sabado', 'domingo').

    Args:
        dia_semana: Dia da semana ou nome da divisão.
        nome_treino: Nome/foco do treino ).
        exercicios: Lista de exercícios planeados. Cada exercício é um dicionário com:
                    - nome (str): nome do exercício (ex: 'Remada Bent Over')
                    - peso (float): peso recomendado em kg
                    - sets (int): número de séries alvo
                    - reps (int): número de repetições alvo
                    - rpe_alvo (float, opcional): RPE alvo (ex: 8.0)
                    - notas (str, opcional): observações/equipamento (ex: 'Barra W')
        notas: Notas ou orientações gerais para o treino.
    """
    if tool_context is None:
        return {"error": "ToolContext não fornecido."}

    user_phone = tool_context.state.get("user_phone", "")
    if not user_phone:
        return {"error": "Número de telefone não disponível."}

    plan_data = {
        "nome_treino": nome_treino,
        "exercicios": exercicios,
        "notas": notas,
    }

    dia_id = db.save_workout_plan(user_phone, dia_semana, plan_data)
    return {
        "status": "plano_guardado",
        "dia_semana": dia_id,
        "nome_treino": nome_treino,
        "total_exercicios": len(exercicios),
    }


def obter_plano_treino(
    tool_context: ToolContext,
    dia_semana: str | None = None,
) -> dict:
    """
    Obtém o plano de treino guardado para um dia específico (ex: 'quarta') ou
    todos os planos guardados para a semana se dia_semana for omitido/None.

    Args:
        dia_semana: Dia da semana opcional (ex: 'segunda', 'quarta', 'pull').
    """
    user_phone = tool_context.state.get("user_phone", "")
    if not user_phone:
        return {"error": "Número de telefone não disponível."}

    planos = db.get_workout_plan(user_phone, dia_semana)
    if not planos:
        msg = f"Sem plano guardado para '{dia_semana}'." if dia_semana else "Sem planos de treino guardados."
        return {"planos": [], "nota": msg}

    return {
        "total_planos": len(planos),
        "planos": planos,
    }


def guardar_treino_prescrito(
    nome_treino: str,
    exercicios: list[dict],
    notas: str = "",
    tool_context: ToolContext | None = None,
) -> dict:
    """
    Guarda o treino que o agente acabou de prescrever ao utilizador para o dia de hoje.
    DEVE ser chamada SEMPRE que prescreves um treino ao utilizador, para que o sistema
    saiba o que foi prescrito mesmo numa sessão nova.

    Args:
        nome_treino: Nome/foco do treino (ex: 'Costas e Bíceps', 'Push Day').
        exercicios: Lista de exercícios prescritos. Cada exercício é um dicionário com:
                    - nome (str): nome do exercício (ex: 'Remada Bent Over')
                    - peso (float): peso recomendado em kg
                    - sets (int): número de séries alvo
                    - reps (int): número de repetições alvo
                    - rpe_alvo (float, opcional): RPE alvo (ex: 8.0)
                    - notas (str, opcional): observações (ex: 'Barra W')
        notas: Notas ou orientações gerais para o treino.
    """
    if tool_context is None:
        return {"error": "ToolContext não fornecido."}

    user_phone = tool_context.state.get("user_phone", "")
    if not user_phone:
        return {"error": "Número de telefone não disponível."}

    workout_data = {
        "nome_treino": nome_treino,
        "exercicios": exercicios,
        "notas": notas,
    }

    data_id = db.save_prescribed_workout(user_phone, workout_data)
    return {
        "status": "prescrito_guardado",
        "data": data_id,
        "nome_treino": nome_treino,
        "total_exercicios": len(exercicios),
    }


def obter_treino_prescrito(
    tool_context: ToolContext,
    data: str | None = None,
) -> dict:
    """
    Obtém o treino prescrito pelo agente para uma data específica ou para hoje.
    Usa esta tool quando o utilizador diz 'Fiz tudo o pedido' ou 'Cumpri o treino'
    para saber exactamente o que foi prescrito e registar o treino executado.

    Args:
        data: Data no formato 'YYYY-MM-DD'. Se omitido, retorna o treino prescrito de hoje.
    """
    user_phone = tool_context.state.get("user_phone", "")
    if not user_phone:
        return {"error": "Número de telefone não disponível."}

    prescrito = db.get_prescribed_workout(user_phone, data)
    if not prescrito:
        msg = f"Sem treino prescrito para '{data}'." if data else "Sem treino prescrito para hoje."
        return {"prescrito": None, "nota": msg}

    return {
        "data": prescrito.get("data"),
        "nome_treino": prescrito.get("nome_treino"),
        "exercicios": prescrito.get("exercicios", []),
        "notas": prescrito.get("notas", ""),
    }


def registar_nota_clinica(
    descricao: str,
    tool_context: ToolContext,
) -> dict:
    """
    Regista uma nota clínica no perfil do utilizador: dor, lesão, restrição médica
    ou qualquer condição que afete o treino.
    Usa esta tool sempre que o utilizador reportar dor, lesão ou limitação física.

    Args:
        descricao: Descrição da condição (ex: 'Dor no ombro direito durante press militar',
                   'Lesão antiga no joelho esquerdo', 'Hérnia discal L4-L5').
    """
    user_phone = tool_context.state.get("user_phone", "")
    if not user_phone:
        return {"error": "Número de telefone não disponível."}

    nota = db.add_nota_clinica(user_phone, descricao)
    return {
        "status": "nota_registada",
        "nota": nota,
    }


def obter_notas_clinicas(tool_context: ToolContext) -> dict:
    """
    Obtém as notas clínicas ativas do utilizador (dores, lesões, restrições médicas).
    Usa esta tool SEMPRE antes de prescrever treinos para evitar exercícios que agravem
    condições existentes.
    """
    user_phone = tool_context.state.get("user_phone", "")
    if not user_phone:
        return {"error": "Número de telefone não disponível."}

    notas = db.get_notas_clinicas(user_phone)
    if not notas:
        return {"notas": [], "nota": "Sem notas clínicas registadas."}

    return {
        "total_notas": len(notas),
        "notas": notas,
    }
