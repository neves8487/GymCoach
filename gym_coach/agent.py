"""
GymCoach — Root Agent (Orquestrador).

Deploy: Vertex AI Agent Engine (expõe A2A endpoint automaticamente).

Chama os sub-agentes PT e Nutrition via Agent Engine SDK (stream_query),
que internamente usa o protocolo A2A de cada Reasoning Engine.

Os resource names dos sub-agentes são injectados como env vars pelo
deploy_agent.py:
  PT_AGENT_RESOURCE_NAME        = projects/.../reasoningEngines/...
  NUTRITION_AGENT_RESOURCE_NAME = projects/.../reasoningEngines/...
"""

from __future__ import annotations

import os
from datetime import date
from pathlib import Path
from typing import Any

from google.adk.agents import Agent
from google.adk.tools import ToolContext

from gym_coach.tools.common_tools import (
    get_perfil,
    atualizar_perfil,
    apagar_dados,
)

_PROMPT_PATH = Path(__file__).parent / "prompts" / "root_system.md"
_SYSTEM_PROMPT = _PROMPT_PATH.read_text(encoding="utf-8")

# Resource names dos sub-agentes no Agent Engine
# Injectados pelo deploy_agent.py --agent root (lidos do .deploy_state.json)
PT_RESOURCE_NAME = os.getenv(
    "PT_AGENT_RESOURCE_NAME",
    "projects/582508796330/locations/us-central1/reasoningEngines/1907715896109957120",
)
NUTRITION_RESOURCE_NAME = os.getenv(
    "NUTRITION_AGENT_RESOURCE_NAME",
    "projects/582508796330/locations/us-central1/reasoningEngines/8235273372565504000",
)


# ---------------------------------------------------------------
# Helper — extrai texto dos eventos de streaming do Agent Engine
# ---------------------------------------------------------------
def _extract_text_from_events(events: Any) -> str:
    """Extrai o texto final de uma lista de eventos de streaming."""
    final = ""
    for event in events:
        if isinstance(event, dict):
            content = event.get("content")
            if isinstance(content, str):
                final = content
            elif isinstance(content, dict):
                parts = content.get("parts", [])
                if isinstance(parts, list):
                    for part in parts:
                        if isinstance(part, dict) and "text" in part:
                            final = str(part["text"])
        elif hasattr(event, "content") and event.content:
            c = event.content
            if isinstance(c, str):
                final = c
            elif hasattr(c, "parts") and c.parts:
                for part in c.parts:
                    if hasattr(part, "text") and part.text:
                        final = str(part.text)
    return final


# ---------------------------------------------------------------
# Tool functions (picklables — sem httpx, sem RLock)
# Chamam os sub-agentes via Agent Engine SDK (protocolo A2A interno)
# ---------------------------------------------------------------
def pt_agent(mensagem: str, tool_context: ToolContext) -> str:
    """Delega a tarefa de treino ao PT Agent (Agent Engine A2A) via resource name."""
    import vertexai
    from vertexai import agent_engines

    user_phone = tool_context.state.get("user_phone", "user")
    session_id = f"session-{user_phone}-{date.today().isoformat()}"

    res_name = os.getenv("PT_AGENT_RESOURCE_NAME", PT_RESOURCE_NAME)
    project = os.getenv("GOOGLE_CLOUD_PROJECT", "gymcoach-503009")
    location = os.getenv("GOOGLE_CLOUD_LOCATION", "us-central1")
    vertexai.init(project=project, location=location)
    engine = agent_engines.get(res_name)

    try:
        engine.get_session(user_id=user_phone, session_id=session_id)
    except Exception:
        try:
            engine.create_session(
                user_id=user_phone,
                session_id=session_id,
                state={"user_phone": user_phone},
            )
        except Exception:
            pass

    events = list(
        engine.stream_query(
            message=mensagem,
            user_id=user_phone,
            session_id=session_id,
        )
    )
    return _extract_text_from_events(events)


def nutrition_agent(mensagem: str, tool_context: ToolContext) -> str:
    """Delega a tarefa de nutrição ao Nutrition Agent (Agent Engine A2A) via resource name."""
    import vertexai
    from vertexai import agent_engines

    user_phone = tool_context.state.get("user_phone", "user")
    session_id = f"session-{user_phone}-{date.today().isoformat()}"

    res_name = os.getenv("NUTRITION_AGENT_RESOURCE_NAME", NUTRITION_RESOURCE_NAME)
    project = os.getenv("GOOGLE_CLOUD_PROJECT", "gymcoach-503009")
    location = os.getenv("GOOGLE_CLOUD_LOCATION", "us-central1")
    vertexai.init(project=project, location=location)
    engine = agent_engines.get(res_name)

    try:
        engine.get_session(user_id=user_phone, session_id=session_id)
    except Exception:
        try:
            engine.create_session(
                user_id=user_phone,
                session_id=session_id,
                state={"user_phone": user_phone},
            )
        except Exception:
            pass

    events = list(
        engine.stream_query(
            message=mensagem,
            user_id=user_phone,
            session_id=session_id,
        )
    )
    return _extract_text_from_events(events)


# ---------------------------------------------------------------
# Root Agent
# ---------------------------------------------------------------
root_agent = Agent(
    name="gym_coach",
    model="gemini-2.5-flash",
    description=(
        "GymCoach — assistente pessoal de treino de powerlifting e nutrição "
        "desportiva. Orquestra sub-agentes especializados para treino (PT) "
        "e nutrição, gere perfis de utilizador, e interage via WhatsApp e Telegram."
    ),
    instruction=_SYSTEM_PROMPT,
    tools=[
        pt_agent,
        nutrition_agent,
        get_perfil,
        atualizar_perfil,
        apagar_dados,
    ],
)