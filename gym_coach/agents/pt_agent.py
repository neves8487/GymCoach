"""
Agente PT (Personal Trainer) — Powerlifting.

Gere treinos, decide pesos com base no histórico, regista resultados.
Definido como Agent do ADK com tools de Firestore.
"""

from __future__ import annotations

from pathlib import Path

from google.adk.agents import Agent

from gym_coach.tools.pt_tools import (
    get_historico_exercicio,
    guardar_plano_treino,
    obter_plano_treino,
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
        "Gere treinos, sugere pesos com base no histórico, guarda e recupera "
        "planos de treino editáveis, regista resultados e aplica regras de progressão."
    ),
    instruction=_SYSTEM_PROMPT,
    tools=[
        get_historico_exercicio,
        registar_treino,
        guardar_plano_treino,
        obter_plano_treino,
    ],
)
