# 🏋️ GymCoach — AI Personal Trainer & Nutritionist

> A production-grade multi-agent personal training and nutrition assistant accessible via **Telegram**.  
> Built with **Google ADK** (Agent Development Kit), **Gemini 2.5 Flash** on **Google Cloud Vertex AI**, deployed to **Cloud Run** and **Vertex AI Agent Engine**.

---

## 🏗️ System Architecture

```
                       Telegram User
                             │
                             ▼
                  Cloud Run Webhook (FastAPI)
                             │
              ┌──────────────┴──────────────┐
              │                             │
       LOCAL Mode                    REMOTE Mode
   ADK Runner (In-Process)      Agent Engine SDK (A2A Protocol)
              │                             │
              └──────────────┬──────────────┘
                             │
                  Root Agent (Orchestrator)
                  ├── PT Agent ────────── Workouts, RPE Progression, Prescriptions
                  └── Nutrition Agent ─── Meal Photos, Macros, Non-Calorie Weight Loss
                             │
                 Firestore + Cloud Storage
```

### Execution Modes

| Mode | Trigger Condition | Description |
|---|---|---|
| **Local** | `AGENT_ENGINE_RESOURCE_NAME` is unset | In-process execution using `adk web` or local FastAPI runner. |
| **Remote** | `AGENT_ENGINE_RESOURCE_NAME` is set | Production mode querying deployed agents on Vertex AI Agent Engine via A2A protocol. |

---

## ⚙️ Tech Stack

| Component | Technology |
|---|---|
| **Agent Framework** | Google ADK (Agent Development Kit) |
| **Foundation Model** | Gemini 2.5 Flash (Google Cloud Vertex AI) |
| **Multi-Agent Protocol** | AgentTool (Local) / A2A RemoteAgent (Remote) |
| **Persistence Store** | Google Cloud Firestore (Document Database) |
| **Media Storage** | Google Cloud Storage (Bucket) |
| **Webhook Service** | FastAPI + Uvicorn (Python 3.12, Dockerized) |
| **Messaging Channel** | Telegram Bot API |
| **Cloud Hosting** | GCP Cloud Run (Serverless Webhook) |
| **Agent Engine** | Vertex AI Agent Engine (Managed Reasoning Engines) |
| **CI/CD & Deployment** | GCP Cloud Build + Custom Deployment Script (`scripts/deploy_agent.py`) |
| **Secret Management** | GCP Secret Manager |

---

## 💡 Key Features

### 🏋️ PT Agent (Personal Trainer)
- **Linear Load Progression**: RPE-driven overload rules (<8 RPE -> +2.5kg upper / +5kg lower; 8-9 RPE -> maintain; >=9.5 RPE or failure -> -5-10% deload).
- **Automated Prescriptions**: Saves daily prescribed workouts (`users/{phone}/treinos_prescritos/{date}`) allowing users to confirm completion ("I did everything") without re-typing exercises or context bloat.
- **Clinical Notes & Pain Safety**: Tracks user injuries, pain reports, and medical restrictions persistently (`notas_clinicas`) and automatically adjusts exercise selection.
- **Structured Workout Plans**: Saves and queries weekly split routines (`planos_treino`).

### 🥗 Nutrition Agent
- **Visual Meal Analysis**: Multi-modal photo evaluation via Gemini Vision, estimating food items, portions, calories, and macros with declared error margins (±15-20%).
- **Non-Calorie Counting Strategies**: Practical portion-control guidance using the Hand Method (palms, fists, cupped hands, thumbs) and satiety cues.
- **Daily & Weekly Summaries**: Aggregates tracked meals against targets saved in the user profile.

### 🔄 Dynamic Session Rotation (Context Bloat Prevention)
- Generates **daily session IDs** (`session-{user}-{YYYY-MM-DD}`) at the webhook layer.
- Ensures every new day starts with a fresh context window, eliminating TPM (Tokens per Minute) explosion and preventing GCP `RESOURCE_EXHAUSTED` (429) rate limit errors.

### 📱 Telegram Integration & Clean Formatting
- Clean output formatting designed specifically for Telegram (emojis, structured line breaks, no invalid raw markdown syntax).
- Handles text messages, photo analysis, and Telegram commands (`/start`, `/perfil`, `/ajuda`, `/apagar`).

---

## 🗄️ Database Architecture (Firestore Schema)

```
users/{phone}                          -> Profile (weight, height, goal, 1RMs, clinical notes, exercise preferences)
├── treinos/{treino_id}                 -> Executed workout logs (exercise, sets, reps, weight, RPE, pain reported)
├── refeicoes/{refeicao_id}             -> Tracked meal logs (description, foods, calories, macros, photo GCS URI)
├── planos_treino/{dia_semana}          -> Saved workout splits per day of week
└── treinos_prescritos/{YYYY-MM-DD}     -> Daily prescribed workout snapshots
```

---

## 🚀 Local Setup & Development

### 1. Prerequisites
- Python 3.12+
- Active GCP Project with Firestore & Vertex AI APIs enabled
- Telegram Bot Token from [@BotFather](https://t.me/BotFather)

### 2. Environment Setup

```bash
git clone https://github.com/neves8487/GymCoach.git
cd GymCoach

python -m venv .venv
# Windows:
.venv\Scripts\activate
# Linux/Mac:
# source .venv/bin/activate

pip install -r requirements.txt
```

### 3. GCP Credentials

```bash
gcloud auth application-default login
gcloud config set project YOUR_PROJECT_ID
```

### 4. Run via ADK Web UI

```bash
adk web
# Opens http://localhost:8000
```

### 5. Run Webhook Locally with Telegram

```bash
cp .env.example .env
# Set TELEGRAM_TOKEN in .env

uvicorn webhook.app:app --reload --port 8080
```

Register your local webhook URL via ngrok:
```bash
ngrok http 8080
curl "https://api.telegram.org/bot<YOUR_TELEGRAM_TOKEN>/setWebhook?url=https://<NGROK_HOST>/telegram-webhook"
```

---

## 📦 Cloud Deployment

### 1. Deploy Agents to Vertex AI Agent Engine

```bash
# Deploy all agents (PT -> Nutrition -> Root Orchestrator)
python scripts/deploy_agent.py --agent all --project YOUR_PROJECT_ID --staging-bucket gs://YOUR_STAGING_BUCKET

# Update existing reasoning engine deployments
python scripts/deploy_agent.py --agent all --update --project YOUR_PROJECT_ID --staging-bucket gs://YOUR_STAGING_BUCKET
```

### 2. Deploy Webhook Service to Cloud Run

Via GCP Cloud Build:
```bash
# Build & deploy webhook container
gcloud builds submit --config cloudbuild.yaml
```

Or via PowerShell deployment script (Windows):
```powershell
.\scripts\deploy_cloudrun.ps1
```

### 3. Test Agent Locally

```bash
# Interactively test agent responses from CLI
python scripts/test_agent.py
```

### 4. Set Telegram Webhook

```bash
curl "https://api.telegram.org/bot<YOUR_TELEGRAM_TOKEN>/setWebhook?url=https://<YOUR_CLOUD_RUN_URL>/telegram-webhook"
```

---

## 📁 Repository Structure

```
GymCoach/
├── gym_coach/                  # ADK Package & Agent Definitions
│   ├── __init__.py
│   ├── agent.py                # Root Agent — Orchestrator (Local & Remote A2A)
│   ├── agents/                 # Specialized Sub-Agents
│   │   ├── pt_agent.py         #   Personal Trainer (Powerlifting & Load Progression)
│   │   └── nutrition_agent.py  #   Sports Nutritionist (Photos & Macros)
│   ├── tools/                  # Function Tools (Auto-Schema via ADK)
│   │   ├── pt_tools.py         #   Workout logs, prescriptions, clinical notes, plans
│   │   ├── nutrition_tools.py  #   Meal tracking, daily & weekly summaries
│   │   └── common_tools.py     #   User profiles, onboarding, RGPD deletion
│   ├── prompts/                # Modular System Prompts (Lookup-table style)
│   │   ├── root_system.md
│   │   ├── pt_system.md
│   │   └── nutrition_system.md
│   └── services/               # Google Cloud Client Wrappers
│       ├── firestore_client.py #   Firestore CRUD (Users, Workouts, Prescriptions, Meals)
│       └── storage_client.py   #   Cloud Storage (Meal Photo Uploads)
├── webhook/                    # FastAPI Webhook Server
│   ├── app.py                  #   Main Router & Telegram Webhook Processor
│   └── telegram_client.py      #   Async Telegram Bot API Client
├── scripts/
│   ├── deploy_agent.py         # Automated Deployment Script for Agent Engine
│   ├── deploy_cloudrun.ps1     # Cloud Run Build & Deploy PowerShell Script
│   └── test_agent.py           # CLI Local Testing Script
├── tests/                      # Unit & Integration Tests
├── Dockerfile                  # Production Multi-Stage Build (Python 3.12-slim)
├── cloudbuild.yaml             # GCP Cloud Build Configuration
├── requirements.txt            # Python Dependencies
└── README.md
```

---

## ⚠️ Disclaimer

GymCoach is an AI-powered fitness and nutrition assistant intended for informational and training guidance purposes only. **It is not a substitute for professional medical advice, diagnosis, or clinical nutrition counseling.** Visual meal calorie estimations carry an inherent margin of error of ±15-20%.
