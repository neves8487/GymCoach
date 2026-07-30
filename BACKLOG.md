# 📋 GymCoach — Backlog de Melhorias & Manutenção

---

## 🛠️ Resolução do Erro `RESOURCE_EXHAUSTED` (Gemini 2.5 Flash + Cloud Run)

### 🚨 Causa do Problema
O erro ocorre por exaustão de quota/taxa (**HTTP 429**) na API da Vertex AI. Num sistema multi-agente, isto é provocado por:
- **Estouro de TPM (Tokens por Minuto)**: Envio do histórico completo do utilizador em todas as chamadas entre agentes.
- **Picos de Concorrência (Burst Traffic)**: Chamadas simultâneas em paralelo entre sub-agentes a exceder o limite por segundo.
- **Falta de Gestão de Erros**: Ausência de retentativas automáticas quando a API atinge o limite temporário.

### 📋 To-Do / Checklist de Implementação:
- [ ] **Quotas GCP**: Ir a *IAM & Admin > Quotas* e solicitar aumento de TPM/RPM para a Vertex AI API no Gemini 2.5 Flash na região `us-central1`.
- [ ] **Resiliência (Backoff Exponencial)**: Adicionar mecanismo de retentativas automáticas (*exponential backoff com jitter*) nas chamadas à Vertex AI SDK para capturar e tentar novamente erros 429.
- [ ] **Trava de Loops**: Definir um limite máximo de passagens/trocas de mensagens (`max_iterations`) na orquestração para evitar loops infinitos entre sub-agentes.
- [ ] **Otimização de Contexto**: Truncar ou resumir o histórico de treinos/conversas passado aos sub-agentes para reduzir drasticamente o consumo de tokens por minuto.

---

## 🥗 Melhorias de Nutrição & Treino (Concluídas)
- [x] **Comunicação Silenciosa**: Agentes não expõem raciocínios internos, meta-explicações ou diálogos inter-agente ao utilizador.
- [x] **Registo de Metas no Perfil**: Nutri calcula e atualiza automaticamente `calorias_alvo` e `macros_alvo.proteina` (1.8g - 2.2g/kg).
- [x] **Dicas de Perda de Peso Sem Contar Calorias**: Método da mão para porções, saciedade por proteína/fibra e regulação pela escala de fome (80%).
- [x] **Planos de Treino Flexíveis**: Guardar e obter planos por dia da semana (`guardar_plano_treino`, `obter_plano_treino`).
- [x] **Registo de Treino Simplificado**: Aceitar *"Fiz tudo o pedido"* e registar o treino prescrito sem exigir digitação redundante.
- [x] **Histórico Recente Abrangente**: Consultar histórico com `exercicio=None` para dar resumos globais e por grupo muscular (ex: *"Qual o meu último treino de costas?"*).
