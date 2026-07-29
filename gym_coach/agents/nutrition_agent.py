"""
Agente Nutrição — Análise de refeições e contagem de macros.

Analisa fotos de comida (via Gemini Vision), estima calorias/macros,
e dá resumos diários/semanais. Definido como Agent do ADK.
"""

from __future__ import annotations

from pathlib import Path

from google.adk.agents import Agent

from gym_coach.tools.nutrition_tools import (
    registar_refeicao,
    get_resumo_diario,
    get_resumo_semanal,
    get_metas_nutricionais,
)

# Load system prompt from markdown file
_PROMPT_PATH = Path(__file__).parent.parent / "prompts" / "nutrition_system.md"
_SYSTEM_PROMPT = _PROMPT_PATH.read_text(encoding="utf-8")

nutrition_agent = Agent(
    name="nutrition_agent",
    model="gemini-2.5-flash",
    description=(
        "Agente Nutricionista especializado em nutrição desportiva. "
        "Analisa fotos de refeições para estimar calorias e macronutrientes, "
        "regista refeições, e dá resumos diários e semanais. "
        "Usa quando o utilizador envia uma foto de comida, fala sobre "
        "calorias, macros, dieta, ou pede resumos nutricionais."
    ),
    instruction=_SYSTEM_PROMPT,
    tools=[
        registar_refeicao,
        get_resumo_diario,
        get_resumo_semanal,
        get_metas_nutricionais,
    ],
)
