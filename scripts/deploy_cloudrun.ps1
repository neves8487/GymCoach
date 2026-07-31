#!/usr/bin/env pwsh
# deploy_cloudrun.ps1 — Deploy webhook to Cloud Run
# Usage: .\scripts\deploy_cloudrun.ps1

$PROJECT = "gymcoach-503009"
$REGION = "us-central1"
$SERVICE = "gym-coach"
$IMAGE = "gcr.io/$PROJECT/$SERVICE"
$SA = "agente-pt-nutricao@$PROJECT.iam.gserviceaccount.com"

# Agent Engine resource name do root agent (de .deploy_state.json)
$AGENT_ENGINE = "projects/582508796330/locations/us-central1/reasoningEngines/7208452657525030912"

Write-Host "=== Deploying $SERVICE to Cloud Run ===" -ForegroundColor Cyan

gcloud run deploy $SERVICE `
    --image=$IMAGE `
    --region=$REGION `
    --platform=managed `
    --allow-unauthenticated `
    --port=8080 `
    --memory=512Mi `
    --min-instances=0 `
    --max-instances=3 `
    --service-account=$SA `
    --set-secrets="WHATSAPP_TOKEN=whatsapp-token:latest,WHATSAPP_PHONE_NUMBER_ID=whatsapp-phone-id:latest,WHATSAPP_VERIFY_TOKEN=whatsapp-verify-token:latest,WHATSAPP_APP_SECRET=whatsapp-app-secret:latest,TELEGRAM_TOKEN=telegram-token:latest" `
    --set-env-vars="GOOGLE_GENAI_USE_VERTEXAI=TRUE,GOOGLE_CLOUD_PROJECT=$PROJECT,GOOGLE_CLOUD_LOCATION=$REGION,GCS_BUCKET_NAME=gymcoach-503009-fotos-refeicoes,LOG_LEVEL=INFO,AGENT_ENGINE_RESOURCE_NAME=$AGENT_ENGINE" `
    --project=$PROJECT

if ($LASTEXITCODE -eq 0) {
    Write-Host "=== Deploy concluido com sucesso! ===" -ForegroundColor Green
} else {
    Write-Host "=== Deploy falhou! ===" -ForegroundColor Red
    exit 1
}
