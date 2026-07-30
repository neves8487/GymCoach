"""
Agente PT (Personal Trainer) — Powerlifting.

Gere treinos, decide pesos com base no histórico, regista resultados.
Definido como Agent do ADK com tools de Firestore.
"""

from __future__ import annotations

from pathlib import Path

from google.adk.agents import Agent

from gym_coach.tools.common_tools import atualizar_perfil, get_perfil
from gym_coach.tools.pt_tools import (
    get_historico_exercicio,
    guardar_plano_treino,
    guardar_treino_prescrito,
    obter_contexto_completo_pt,
    obter_notas_clinicas,
    obter_plano_treino,
    obter_treino_prescrito,
    registar_nota_clinica,
    registar_treino,
)

# Load system prompt from markdown file
_PROMPT_PATH = Path(__file__).parent.parent / "prompts" / "pt_system.md"
_SYSTEM_PROMPT = _PROMPT_PATH.read_text(encoding="utf-8")

pt_agent = Agent(
    name="pt_agent",
    model="gemini-2.5-flash",
    description=(
        "Agente Personal Trainer especializado em powerlifting. "
        "Gere treinos, responde a dúvidas e dá conselhos sobre treino, estruturação de divisão semanal e força. "
        "Sugere pesos com base no histórico, guarda e recupera planos de treino editáveis, regista resultados, "
        "guarda treinos prescritos, gere notas clínicas (lesões/dores) e aplica regras de progressão."
    ),
    instruction=_SYSTEM_PROMPT,
    tools=[
        obter_contexto_completo_pt,
        get_perfil,
        atualizar_perfil,
        get_historico_exercicio,
        registar_treino,
        guardar_plano_treino,
        obter_plano_treino,
        guardar_treino_prescrito,
        obter_treino_prescrito,
        registar_nota_clinica,
        obter_notas_clinicas,
    ],
)
