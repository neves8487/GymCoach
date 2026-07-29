# 🏋️ GymCoach — AI Personal Trainer & Nutritionist

> Assistente pessoal de treino de powerlifting e nutrição desportiva, acessível via **WhatsApp** e **Telegram**.  
> Construído com **Google ADK**, **Gemini 2.5 Flash** via **Vertex AI**, com deploy em **Cloud Run** e **Agent Engine**.

---

## 🏗️ Arquitetura

```
WhatsApp / Telegram
        │
        ▼
  Cloud Run (FastAPI)
        │
        ├─ LOCAL mode ──▶ ADK Runner (in-process)
        │                       │
        └─ REMOTE mode ─▶ Agent Engine SDK
                                │
                          Root Agent (Orquestrador)
                           ├── PT Agent ─────────── Treinos, progressão, planos
                           └── Nutrition Agent ──── Fotos, macros, resumos
                                    │
                          Firestore + Cloud Storage
```

### Modos de Operação

| Modo | Quando | Como |
|---|---|---|
| **Local** | Dev / `adk web` | Runner in-process com `AgentTool` |
| **Remote** | Produção | Agent Engine via A2A protocol (`RemoteA2aAgent`) |

O modo é auto-detectado: se `AGENT_ENGINE_RESOURCE_NAME` está definido, usa Remote; caso contrário, Local.

---

## ⚙️ Stack

| Componente | Tecnologia |
|---|---|
| Framework de Agentes | Google ADK |
| Modelo | Gemini 2.5 Flash (Vertex AI) |
| Orquestração Multi-Agent | AgentTool (local) / A2A RemoteAgent (remote) |
| Dados | Firestore + Cloud Storage |
| Webhook | FastAPI + uvicorn |
| Canais | WhatsApp Business Cloud API + Telegram Bot API |
| Deploy — Webhook | Cloud Run + Cloud Build |
| Deploy — Agentes | Vertex AI Agent Engine |
| Segredos | Secret Manager |
| Deploy Script | `scripts/deploy_agent.py` |

---

## 🚀 Setup Local

### 1. Pré-requisitos

- Python 3.12+
- Conta GCP com projeto ativo
- Conta Meta for Developers com app WhatsApp Business (para WhatsApp)
- Bot Telegram via [@BotFather](https://t.me/BotFather) (para Telegram)

### 2. Instalação

```bash
cd GymCoach
python -m venv .venv
.venv\Scripts\activate       # Windows
# source .venv/bin/activate  # Linux/Mac

pip install -r requirements.txt
```

### 3. Configuração

```bash
cp .env.example .env
# Editar .env com as tuas credenciais
```

Autenticação GCP:
```bash
gcloud auth application-default login
gcloud config set project YOUR_PROJECT_ID
```

### 4. Testar com ADK Web UI

```bash
adk web
# Abre http://localhost:8000
# Seleciona "gym_coach" no dropdown
```

### 5. Testar com Telegram (recomendado)

1. Cria um bot no Telegram enviando `/newbot` ao [@BotFather](https://t.me/BotFather)
2. Adiciona o token ao `.env`:
   ```env
   TELEGRAM_TOKEN=o_teu_token_aqui
   ```
3. Executa o bot:
   ```bash
   python telegram_bot.py
   ```
4. Abre o Telegram e envia mensagens ou fotos ao teu bot!

### 6. Correr o Webhook localmente

```bash
uvicorn webhook.app:app --reload --port 8080
```

Para testar com WhatsApp/Telegram real, usa um túnel:
```bash
ngrok http 8080
# Usa o URL HTTPS do ngrok como webhook URL
```

---

## 📦 Deploy

### Opção A — Agent Engine (agentes na cloud)

Deploy dos agentes no Vertex AI Agent Engine com A2A protocol:

```bash
# Deploy de todos (PT → Nutrition → Root com A2A URLs)
python scripts/deploy_agent.py --agent all --staging-bucket gs://your-bucket

# Deploy individual
python scripts/deploy_agent.py --agent pt --staging-bucket gs://your-bucket

# Atualizar um deploy existente
python scripts/deploy_agent.py --agent root --update

# Ver estado do deploy
python scripts/deploy_agent.py --status

# Apagar agentes
python scripts/deploy_agent.py --agent all --delete
```

Após o deploy, o script imprime o `AGENT_ENGINE_RESOURCE_NAME` para configurar no webhook.

### Opção B — Cloud Run (webhook)

1. Criar segredos no Secret Manager:
```bash
echo -n "TOKEN" | gcloud secrets create whatsapp-token --data-file=-
echo -n "PHONE_ID" | gcloud secrets create whatsapp-phone-id --data-file=-
echo -n "VERIFY" | gcloud secrets create whatsapp-verify-token --data-file=-
echo -n "SECRET" | gcloud secrets create whatsapp-app-secret --data-file=-
echo -n "TELEGRAM_TOKEN" | gcloud secrets create telegram-token --data-file=-
```

2. Deploy:
```bash
gcloud builds submit --config cloudbuild.yaml
```

3. Configurar webhooks:
   - **WhatsApp** — URL: `https://gym-coach-XXXXX.run.app/webhook` na Meta Developer Console
   - **Telegram** — Registar webhook:
     ```
     https://api.telegram.org/bot<TOKEN>/setWebhook?url=https://gym-coach-XXXXX.run.app/telegram-webhook
     ```

---

## 🧠 Funcionalidades

### 🏋️ Agente PT (Personal Trainer)
- Sugere treinos com pesos baseados no histórico real
- Regras de progressão linear com análise de RPE
- Deload automático após falhas consecutivas
- Nunca sobe carga se houver dor reportada
- Planos de treino editáveis por dia da semana
- Guarda e recupera planos estruturados

### 🥗 Agente Nutrição
- Analisa fotos de refeições via Gemini Vision
- Estima calorias, macronutrientes e micronutrientes
- Regista refeições com breakdown por alimento
- Resumos diários e semanais com comparação a metas
- Margem de erro declarada (±15-20%)

### ⚙️ Gestão de Perfil
- Onboarding automático na primeira mensagem
- Atualização de peso, 1RMs, metas nutricionais
- Suporte a campos nested (ex: `one_rm.agachamento`, `macros_alvo.proteina`)
- Eliminação completa de dados — conformidade RGPD

### 🔌 Integrações
- **WhatsApp**: texto, imagens (com upload para Cloud Storage), validação de assinatura
- **Telegram**: texto, fotos, comandos (`/start`), auto-split de mensagens longas
- **Health check**: `GET /health`

---

## 🗂️ Estrutura do Projeto

```
GymCoach/
├── gym_coach/                  # Pacote ADK
│   ├── __init__.py
│   ├── agent.py                # Root agent — orquestrador (local + A2A remote)
│   ├── agents/                 # Sub-agentes
│   │   ├── pt_agent.py         #   Personal Trainer (powerlifting)
│   │   └── nutrition_agent.py  #   Nutricionista (fotos + macros)
│   ├── tools/                  # Function tools (auto-schema via ADK)
│   │   ├── pt_tools.py         #   Histórico, registo, planos, progressão
│   │   ├── nutrition_tools.py  #   Refeições, resumos diários/semanais
│   │   └── common_tools.py     #   Perfil, onboarding, RGPD
│   ├── prompts/                # System prompts (markdown)
│   │   ├── root_system.md
│   │   ├── pt_system.md
│   │   └── nutrition_system.md
│   └── services/               # GCP clients
│       ├── firestore_client.py #   Firestore CRUD (perfis, treinos, refeições)
│       └── storage_client.py   #   Cloud Storage (fotos de refeições)
├── webhook/                    # FastAPI — WhatsApp + Telegram
│   ├── app.py                  #   Webhook principal (local/remote auto-detect)
│   ├── whatsapp_client.py      #   WhatsApp Business API client
│   ├── telegram_client.py      #   Telegram Bot API client
│   └── signature.py            #   Validação de assinatura WhatsApp
├── scripts/
│   └── deploy_agent.py         # Deploy de agentes no Agent Engine
├── tests/
├── Dockerfile                  # Multi-stage build (Python 3.12-slim)
├── cloudbuild.yaml             # CI/CD para Cloud Run
├── requirements.txt
├── .env.example
└── .gitignore
```

---

## 🔧 Variáveis de Ambiente

| Variável | Descrição |
|---|---|
| `GOOGLE_GENAI_USE_VERTEXAI` | `TRUE` para usar Vertex AI |
| `GOOGLE_CLOUD_PROJECT` | ID do projeto GCP |
| `GOOGLE_CLOUD_LOCATION` | Região (ex: `us-central1`) |
| `WHATSAPP_TOKEN` | Token de acesso da WhatsApp Business API |
| `WHATSAPP_PHONE_NUMBER_ID` | ID do número de telefone WhatsApp |
| `WHATSAPP_VERIFY_TOKEN` | Token de verificação do webhook |
| `WHATSAPP_APP_SECRET` | App secret para validação de assinatura |
| `TELEGRAM_TOKEN` | Token do bot Telegram |
| `GCS_BUCKET_NAME` | Bucket para fotos de refeições |
| `AGENT_ENGINE_RESOURCE_NAME` | Resource name do Agent Engine (ativa modo remote) |
| `PT_AGENT_A2A_URL` | URL A2A do PT Agent (injetado pelo deploy script) |
| `NUTRITION_AGENT_A2A_URL` | URL A2A do Nutrition Agent (injetado pelo deploy script) |
| `LOG_LEVEL` | Nível de logging (default: `INFO`) |

---

## ⚠️ Disclaimer

Este bot é uma ferramenta de apoio ao treino e nutrição. **Não substitui acompanhamento médico ou nutricional profissional.** As estimativas calóricas baseadas em fotos têm uma margem de erro de ±15-20%.
