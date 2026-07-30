#!/usr/bin/env python3
"""
GymCoach — Reusable Agent Engine deployment script.

Deploys ADK agents to Vertex AI Agent Engine.
Uses the existing gym_coach/ package directly — no code duplication.

Usage:
    python scripts/deploy_agent.py --agent all
    python scripts/deploy_agent.py --agent pt
    python scripts/deploy_agent.py --agent root --update
    python scripts/deploy_agent.py --agent all --delete
    python scripts/deploy_agent.py --status
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import subprocess
import sys
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(message)s",
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------
# Paths & Environment
# ---------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

STATE_FILE = PROJECT_ROOT / ".deploy_state.json"

# Sub-agents first, orchestrator last
DEPLOY_ORDER = ["pt", "nutrition", "root"]

# Shared requirements for Agent Engine
REQUIREMENTS_FILE = str(PROJECT_ROOT / "requirements.txt")


# ---------------------------------------------------------------
# Agent factory — imports and wraps each agent
# ---------------------------------------------------------------

def _clean_pycache():
    """Remove stale compiled python bytecode and sys.modules cache before packaging."""
    import shutil
    for p in PROJECT_ROOT.rglob("__pycache__"):
        try:
            shutil.rmtree(p)
        except Exception:
            pass
    for mod in list(sys.modules.keys()):
        if mod.startswith("gym_coach"):
            del sys.modules[mod]


def _build_agent(name: str, env_vars: dict | None = None):
    """Import the agent object, wrap in App and AdkApp."""
    _clean_pycache()
    from google.adk.apps import App
    from vertexai import agent_engines

    # Set env vars before importing (root agent reads them at import time)
    if env_vars:
        for k, v in env_vars.items():
            os.environ[k] = v

    if name == "pt":
        from gym_coach.agents.pt_agent import pt_agent
        app = App(root_agent=pt_agent, name="pt_agent")
        return agent_engines.AdkApp(app=app)

    elif name == "nutrition":
        from gym_coach.agents.nutrition_agent import nutrition_agent
        app = App(root_agent=nutrition_agent, name="nutrition_agent")
        return agent_engines.AdkApp(app=app)

    elif name == "root":
        from gym_coach.agent import root_agent
        app = App(root_agent=root_agent, name="gym_coach")
        return agent_engines.AdkApp(app=app)

    else:
        raise ValueError(f"Unknown agent: {name}")


def _agent_display_name(name: str) -> str:
    return {
        "pt": "GymCoach — PT Agent",
        "nutrition": "GymCoach — Nutrition Agent",
        "root": "GymCoach — Root Orchestrator",
    }[name]


# ---------------------------------------------------------------
# State management
# ---------------------------------------------------------------

def load_state() -> dict:
    if STATE_FILE.exists():
        with open(STATE_FILE, encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_state(state: dict) -> None:
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, ensure_ascii=False)
    logger.info("State saved → %s", STATE_FILE)


def a2a_url_from_resource(resource_name: str, location: str) -> str:
    """Build the A2A agent-card URL from an Agent Engine resource name."""
    base = f"https://{location}-aiplatform.googleapis.com/v1/{resource_name}"
    return f"{base}/.well-known/agent.json"


# ---------------------------------------------------------------
# Deploy / Update / Delete
# ---------------------------------------------------------------

def deploy_agent(
    name: str,
    project: str,
    location: str,
    staging_bucket: str,
    env_vars: dict | None = None,
    update: bool = False,
    service_account: str | None = None,
) -> dict:
    """Deploy or update a single agent on Agent Engine."""
    import vertexai
    from vertexai import agent_engines

    display = _agent_display_name(name)

    logger.info("=" * 60)
    logger.info("  %s  %s", "Updating" if update else "Deploying", display)
    logger.info("=" * 60)

    vertexai.init(project=project, location=location, staging_bucket=staging_bucket)

    state = load_state()

    # Build AdkApp wrapper
    adk_app = _build_agent(name, env_vars)

    # Read and clean requirements
    reqs = []
    if os.path.exists(REQUIREMENTS_FILE):
        with open(REQUIREMENTS_FILE, encoding="utf-8") as f:
            reqs = [
                line.strip()
                for line in f
                if line.strip() and not line.strip().startswith("#")
            ]

    # Common kwargs
    common_kw: dict = {
        "requirements": reqs,
        "extra_packages": ["gym_coach"],
    }
    if service_account:
        common_kw["service_account"] = service_account

    if update and name in state:
        resource_name = state[name]["resource_name"]
        logger.info("Updating %s …", resource_name)

        agent_engines.update(
            resource_name=resource_name,
            agent_engine=adk_app,
            **common_kw,
        )
        a2a_url = a2a_url_from_resource(resource_name, location)
        logger.info("✅ Updated: %s", resource_name)
    else:
        logger.info("Creating new agent …")

        create_kw: dict = {
            "display_name": display,
            **common_kw,
        }
        if env_vars:
            create_kw["env_vars"] = env_vars

        engine = agent_engines.create(adk_app, **create_kw)
        resource_name = engine.resource_name
        a2a_url = a2a_url_from_resource(resource_name, location)
        logger.info("✅ Deployed: %s", resource_name)

    entry = {
        "resource_name": resource_name,
        "a2a_url": a2a_url,
        "display_name": display,
        "project": project,
        "location": location,
    }
    state[name] = entry
    save_state(state)
    return entry


def deploy_all(
    project: str,
    location: str,
    staging_bucket: str,
    update: bool = False,
    service_account: str | None = None,
) -> dict:
    """Deploy all agents in order, injecting A2A URLs into root."""
    state = load_state()
    results: dict = {}

    for name in DEPLOY_ORDER:
        env_vars: dict = {}

        if name == "root":
            pt = results.get("pt") or state.get("pt")
            nutri = results.get("nutrition") or state.get("nutrition")
            if pt:
                env_vars["PT_AGENT_A2A_URL"] = pt["a2a_url"]
            else:
                logger.warning("⚠️  PT not deployed — root won't have PT")
            if nutri:
                env_vars["NUTRITION_AGENT_A2A_URL"] = nutri["a2a_url"]
            else:
                logger.warning("⚠️  Nutrition not deployed — root won't have Nutrition")

        results[name] = deploy_agent(
            name=name,
            project=project,
            location=location,
            staging_bucket=staging_bucket,
            env_vars=env_vars or None,
            update=update,
            service_account=service_account,
        )

    return results


def delete_agent(name: str, project: str, location: str) -> None:
    """Delete a single deployed agent."""
    import vertexai
    from vertexai import agent_engines

    state = load_state()
    if name not in state:
        logger.warning("'%s' not in deploy state", name)
        return

    resource = state[name]["resource_name"]
    logger.info("Deleting %s (%s) …", name, resource)

    vertexai.init(project=project, location=location)
    agent_engines.delete(resource_name=resource, force=True)
    logger.info("✅ Deleted %s", resource)

    del state[name]
    save_state(state)


def delete_all(project: str, location: str) -> None:
    for name in reversed(DEPLOY_ORDER):
        try:
            delete_agent(name, project, location)
        except Exception:
            logger.exception("Failed to delete %s — continuing", name)


# ---------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------

def _resolve_project(arg: str | None) -> str:
    if arg:
        return arg
    env = os.environ.get("GOOGLE_CLOUD_PROJECT", "")
    if env and env != "your-gcp-project-id":
        return env
    try:
        r = subprocess.run(
            ["gcloud", "config", "get-value", "project"],
            capture_output=True, text=True, check=True,
        )
        if r.stdout.strip():
            return r.stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        pass
    logger.error("Cannot determine GCP project. Use --project or set GOOGLE_CLOUD_PROJECT.")
    sys.exit(1)


def _resolve_location(arg: str | None) -> str:
    return arg or os.environ.get("GOOGLE_CLOUD_LOCATION", "us-central1")


# ---------------------------------------------------------------
# CLI
# ---------------------------------------------------------------

def main() -> None:
    p = argparse.ArgumentParser(
        description="Deploy GymCoach agents to Vertex AI Agent Engine.",
        epilog="""
Examples:
  python scripts/deploy_agent.py --agent all --staging-bucket gs://my-bucket
  python scripts/deploy_agent.py --agent pt
  python scripts/deploy_agent.py --agent root --update
  python scripts/deploy_agent.py --agent all --delete
  python scripts/deploy_agent.py --status
        """,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("--agent", choices=["pt", "nutrition", "root", "all"])
    p.add_argument("--project", default=None)
    p.add_argument("--location", default=None)
    p.add_argument("--staging-bucket", default=None)
    p.add_argument("--service-account", default=None)
    p.add_argument("--update", action="store_true", help="Update existing deploy")
    p.add_argument("--delete", action="store_true", help="Delete deployed agent(s)")
    p.add_argument("--status", action="store_true", help="Show deploy state")

    args = p.parse_args()

    if args.status:
        state = load_state()
        if not state:
            print("No agents deployed.")
        else:
            print(json.dumps(state, indent=2, ensure_ascii=False))
        return

    if not args.agent:
        p.print_help()
        return

    project = _resolve_project(args.project)
    location = _resolve_location(args.location)
    bucket = args.staging_bucket or os.environ.get("STAGING_BUCKET")

    if not bucket and not args.delete:
        logger.error("Staging bucket required. Use --staging-bucket or set STAGING_BUCKET.")
        sys.exit(1)

    if args.delete:
        (delete_all if args.agent == "all" else lambda p, l: delete_agent(args.agent, p, l))(project, location)
        return

    if args.agent == "all":
        deploy_all(project, location, bucket, args.update, args.service_account)
    else:
        env_vars: dict = {}
        if args.agent == "root":
            st = load_state()
            if "pt" in st:
                env_vars["PT_AGENT_A2A_URL"] = st["pt"]["a2a_url"]
            if "nutrition" in st:
                env_vars["NUTRITION_AGENT_A2A_URL"] = st["nutrition"]["a2a_url"]
        deploy_agent(args.agent, project, location, bucket, env_vars or None, args.update, args.service_account)

    # Summary
    print("\n" + "=" * 60)
    print("DEPLOY SUMMARY")
    print("=" * 60)
    for n, info in load_state().items():
        print(f"\n  {info['display_name']}")
        print(f"    Resource: {info['resource_name']}")
        print(f"    A2A URL:  {info['a2a_url']}")

    state = load_state()
    if "root" in state:
        print("\n  Webhook .env:")
        print(f"    AGENT_ENGINE_RESOURCE_NAME={state['root']['resource_name']}")
    print()


if __name__ == "__main__":
    main()
