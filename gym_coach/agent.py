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

from gym_coach.agents.pt_agent import pt_agent
from gym_coach.agents.nutrition_agent import nutrition_agent
from gym_coach.tools.common_tools import (
    get_perfil,
    atualizar_perfil,
    apagar_dados,
)

# Load system prompt from markdown file
_PROMPT_PATH = Path(__file__).parent / "prompts" / "root_system.md"
_SYSTEM_PROMPT = _PROMPT_PATH.read_text(encoding="utf-8")

_tools: list = [
    AgentTool(agent=pt_agent),
    AgentTool(agent=nutrition_agent),
    get_perfil,
    atualizar_perfil,
    apagar_dados,
]

root_agent = Agent(
    name="gym_coach",
    model="gemini-2.5-flash",
    description=(
        "GymCoach — assistente pessoal de treino de powerlifting e nutrição "
        "desportiva. Orquestra sub-agentes especializados para treino (PT) "
        "e nutrição, gere perfis de utilizador, e interage via WhatsApp."
    ),
    instruction=_SYSTEM_PROMPT,
    tools=_tools,
)
