# 🏋️ GymCoach — Agente PT + Nutricionista via WhatsApp

Assistente pessoal de treino de powerlifting e nutrição desportiva, acessível via WhatsApp. Construído com **Google ADK**, **Gemini 2.0 Flash** via **Vertex AI**, e deploy em **Cloud Run**.

## Arquitetura

```
WhatsApp → Cloud Run (FastAPI) → ADK Runner → Root Agent
                                                  ├── PT Agent (treinos, progressão)
                                                  └── Nutrition Agent (fotos, macros)
                                                          ↓
                                              Firestore + Cloud Storage
```

## Stack

| Componente | Tecnologia |
|---|---|
| Framework de Agentes | Google ADK |
| Modelo | Gemini 2.0 Flash (Vertex AI) |
| Orquestração | AgentTool (multi-agent) |
| Dados | Firestore + Cloud Storage |
| Webhook | FastAPI + uvicorn |
| Deploy | Cloud Run + Cloud Build |
| Segredos | Secret Manager |
| Entrada | WhatsApp Business Cloud API |

## Setup Local

### 1. Pré-requisitos

- Python 3.12+
- Conta GCP com projeto activo
- Conta Meta for Developers com app WhatsApp Business

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

### 4. Testar com ADK UI

```bash
adk web
# Abre http://localhost:8000
# Seleciona "gym_coach" no dropdown
```

### 5. Correr o Telegram Bot localmente (Recomendado para Testes)

1. Cria um Bot no Telegram enviando `/newbot` ao [@BotFather](https://t.me/BotFather) e obtém o token da API.
2. Adiciona o token ao teu ficheiro `.env`:
   ```env
   TELEGRAM_TOKEN=o_teu_token_aqui
   ```
3. Executa o bot:
   ```bash
   python telegram_bot.py
   ```
4. Abre o Telegram e envia mensagens ou fotos ao teu bot para testar a experiência conversacional!

### 6. Correr o Webhook do WhatsApp localmente


```bash
uvicorn webhook.app:app --reload --port 8080
```

Para testar com WhatsApp real, usa um túnel (ex: ngrok):
```bash
ngrok http 8080
# Usa o URL HTTPS do ngrok como webhook URL na Meta Developer Console
```

## Deploy

### Cloud Run (via Cloud Build)

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

3. Configurar webhook na Meta Developer Console (WhatsApp):
   - URL: `https://gym-coach-XXXXX.run.app/webhook`
   - Verify token: o mesmo que guardaste no Secret Manager

4. Configurar webhook no Telegram:
   Envia um pedido HTTP para registar o teu URL do Cloud Run como webhook do teu bot:
   `https://api.telegram.org/bot<TELEGRAM_TOKEN>/setWebhook?url=https://gym-coach-XXXXX.run.app/telegram-webhook`


## Funcionalidades

### 🏋️ Agente PT
- Sugere treinos com pesos baseados no histórico
- Regras de progressão linear + RPE
- Deload automático após falhas consecutivas
- Nunca sobe carga se houver dor reportada

### 🥗 Agente Nutrição
- Analisa fotos de refeições (via Gemini Vision)
- Estima calorias, macros e micronutrientes
- Resumos diários e semanais
- Compara com metas definidas no perfil

### ⚙️ Gestão de Perfil
- Onboarding automático na primeira mensagem
- Actualização de peso, 1RMs, metas nutricionais
- Eliminação de dados (RGPD)

## Estrutura do Projeto

```
GymCoach/
├── gym_coach/                 # Pacote ADK
│   ├── agent.py               # Root agent (orquestrador)
│   ├── agents/                # Sub-agentes
│   │   ├── pt_agent.py
│   │   └── nutrition_agent.py
│   ├── tools/                 # Function tools
│   │   ├── pt_tools.py
│   │   ├── nutrition_tools.py
│   │   └── common_tools.py
│   ├── prompts/               # System prompts
│   │   ├── root_system.md
│   │   ├── pt_system.md
│   │   └── nutrition_system.md
│   └── services/              # GCP clients
│       ├── firestore_client.py
│       └── storage_client.py
├── webhook/                   # FastAPI + WhatsApp
│   ├── app.py
│   ├── whatsapp_client.py
│   └── signature.py
├── Dockerfile
├── cloudbuild.yaml
└── requirements.txt
```

## Disclaimer

⚠️ Este bot é uma ferramenta de apoio ao treino e nutrição. **Não substitui acompanhamento médico ou nutricional profissional.** As estimativas calóricas baseadas em fotos têm uma margem de erro de ±15-20%.
