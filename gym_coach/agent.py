"""
GymCoach — Root Agent (Orquestrador).

Unified entry point for the ADK framework:
- If PT_AGENT_A2A_URL or NUTRITION_AGENT_A2A_URL are set: uses RemoteA2aAgent via A2A protocol.
- Otherwise: delegates in-process via AgentTool for local development (`adk web`).
"""

from __future__ import annotations

import os
from pathlib import Path

from google.adk.agents import Agent
from google.adk.tools.agent_tool import AgentTool

from gym_coach.tools.common_tools import (
    get_perfil,
    atualizar_perfil,
    apagar_dados,
)

# Load system prompt from markdown file
_PROMPT_PATH = Path(__file__).parent / "prompts" / "root_system.md"
_SYSTEM_PROMPT = _PROMPT_PATH.read_text(encoding="utf-8")

_PT_URL = os.environ.get("PT_AGENT_A2A_URL", "")
_NUTRI_URL = os.environ.get("NUTRITION_AGENT_A2A_URL", "")

_sub_agents: list = []
_tools: list = [get_perfil, atualizar_perfil, apagar_dados]

if _PT_URL or _NUTRI_URL:
    # A2A Remote Mode — delegate across network endpoints
    from google.adk.agents.remote_a2a_agent import RemoteA2aAgent

    if _PT_URL:
        _sub_agents.append(
            RemoteA2aAgent(
                name="pt_agent",
                description=(
                    "Agente Personal Trainer especializado em powerlifting. "
                    "Gere treinos, sugere pesos com base no histórico, regista "
                    "resultados e aplica regras de progressão."
                ),
                agent_card=_PT_URL,
            )
        )
    if _NUTRI_URL:
        _sub_agents.append(
            RemoteA2aAgent(
                name="nutrition_agent",
                description=(
                    "Agente Nutricionista especializado em nutrição desportiva. "
                    "Analisa fotos de refeições, estima calorias e macronutrientes, "
                    "regista refeições, e dá resumos diários e semanais."
                ),
                agent_card=_NUTRI_URL,
            )
        )
else:
    # Local Mode — delegate in-process
    from gym_coach.agents.pt_agent import pt_agent
    from gym_coach.agents.nutrition_agent import nutrition_agent

    _tools.insert(0, AgentTool(agent=pt_agent))
    _tools.insert(1, AgentTool(agent=nutrition_agent))

root_agent = Agent(
    name="gym_coach",
    model="gemini-2.5-flash",
    description=(
        "GymCoach — assistente pessoal de treino de powerlifting e nutrição "
        "desportiva. Orquestra sub-agentes especializados para treino (PT) "
        "e nutrição, gere perfis de utilizador, e interage via WhatsApp."
    ),
    instruction=_SYSTEM_PROMPT,
    sub_agents=_sub_agents,
    tools=_tools,
)
