#!/usr/bin/env python3
"""
GymCoach — Test script for Root Agent calling PT and Nutrition agents.

Sends queries to the deployed Root Agent Engine on Vertex AI, which delegates
to the PT Agent Engine and Nutrition Agent Engine.
"""

from __future__ import annotations

import json
import logging
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

STATE_FILE = PROJECT_ROOT / ".deploy_state.json"
logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)-8s | %(message)s")
logger = logging.getLogger(__name__)


def load_state() -> dict:
    if STATE_FILE.exists():
        with open(STATE_FILE, encoding="utf-8") as f:
            return json.load(f)
    return {}


def extract_text_from_events(events) -> str:
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


def run_test():
    import vertexai
    from vertexai import agent_engines

    project = "gymcoach-503009"
    location = "us-central1"
    vertexai.init(project=project, location=location)

    state = load_state()
    root_resource = state.get("root", {}).get("resource_name")
    if not root_resource:
        logger.error("Root agent resource name não encontrado no .deploy_state.json")
        return

    logger.info("A ligar ao Root Agent Engine: %s", root_resource)
    engine = agent_engines.get(root_resource)

    prompts = [
        ("TESTE 1: Treino de Pernas (delega ao PT Agent)", "Quero um treino de pernas com foco em força no agachamento."),
        ("TESTE 2: Proteína e Nutrição (delega ao Nutri Agent)", "Quantas gramas de proteína devo comer por dia para hipertrofia pesando 80kg?"),
    ]

    for title, prompt_text in prompts:
        print("\n" + "=" * 70)
        print(f"  {title}")
        print("=" * 70)
        print(f"User: {prompt_text}\n")

        events = list(engine.stream_query(message=prompt_text, user_id="user"))
        response = extract_text_from_events(events)
        print(f"GymCoach (Root): {response}\n")


def main():
    run_test()


if __name__ == "__main__":
    main()
