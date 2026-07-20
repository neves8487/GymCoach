"""
GymCoach — Root Agent (Orquestrador).

This is the main entry point for the ADK framework.
The root_agent uses AgentTool to delegate to the PT and Nutrition sub-agents,
while keeping control of the conversation flow.

Conventions:
- `root_agent` is the variable name that ADK expects
- `adk web` will discover this agent automatically
"""

from __future__ import annotations

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

root_agent = Agent(
    name="gym_coach",
    model="gemini-2.0-flash",
    description=(
        "GymCoach — assistente pessoal de treino de powerlifting e nutrição "
        "desportiva. Orquestra sub-agentes especializados para treino (PT) "
        "e nutrição, gere perfis de utilizador, e interage via WhatsApp."
    ),
    instruction=_SYSTEM_PROMPT,
    tools=[
        # Sub-agents as tools — root keeps control, delegates discrete tasks
        AgentTool(agent=pt_agent),
        AgentTool(agent=nutrition_agent),
        # Direct tools for profile management
        get_perfil,
        atualizar_perfil,
        apagar_dados,
    ],
)
