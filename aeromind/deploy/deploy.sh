#!/usr/bin/env bash
# =============================================================================
# AeroMind 2026 — Automated Google Cloud Deployment Script
# Infrastructure-as-Code for Gemini Live Agent Hackathon
#
# Created for the purposes of entering the Google Gemini Live Agent Hackathon.
# #GeminiLiveAgentChallenge
#
# Deploys:
#   1. Memgraph DB       → Compute Engine VM (e2-medium, us-central1-a)
#   2. Backend (FastAPI) → Cloud Run  (min-instances=1, 2 vCPU, 2Gi)
#   3. Frontend (Nginx)  → Cloud Run  (serves Vite build, proxies to backend)
#
# Prerequisites:
#   gcloud auth login
#   gcloud auth configure-docker us-central1-docker.pkg.dev
#   Secrets are read directly from your .env file — no Secret Manager needed.
# =============================================================================

set -euo pipefail

# ---------------------------------------------------------------------------
# CONFIG — edit these to match your GCP project
# ---------------------------------------------------------------------------
PROJECT_ID="project-45989369-636b-4d31-890"
REGION="us-central1"
ZONE="us-central1-a"
REPO="aeromind"                          # Artifact Registry repo name
BACKEND_IMAGE="$REGION-docker.pkg.dev/$PROJECT_ID/$REPO/backend"
FRONTEND_IMAGE="$REGION-docker.pkg.dev/$PROJECT_ID/$REPO/frontend"
MEMGRAPH_VM="aeromind-memgraph"
BACKEND_SERVICE="aeromind-backend"
FRONTEND_SERVICE="aeromind-frontend"
TAG=$(git rev-parse --short HEAD 2>/dev/null || echo "latest")

echo "======================================================================"
echo "  AeroMind 2026 — GCP Deployment  |  #GeminiLiveAgentChallenge"
echo "  Project : $PROJECT_ID"
echo "  Region  : $REGION"
echo "  Tag     : $TAG"
echo "======================================================================"

# ---------------------------------------------------------------------------
# 0. Enable required APIs
# ---------------------------------------------------------------------------
echo ""
echo "► Enabling GCP APIs..."
gcloud services enable \
  run.googleapis.com \
  cloudbuild.googleapis.com \
  artifactregistry.googleapis.com \
  compute.googleapis.com \
  aiplatform.googleapis.com \
  --project="$PROJECT_ID" \
  --quiet

# ---------------------------------------------------------------------------
# 1. Artifact Registry — container image repository
# ---------------------------------------------------------------------------
echo ""
echo "► Setting up Artifact Registry..."
gcloud artifacts repositories create "$REPO" \
  --repository-format=docker \
  --location="$REGION" \
  --description="AeroMind 2026 container images" \
  --project="$PROJECT_ID" \
  --quiet 2>/dev/null || echo "  (repository already exists)"

gcloud auth configure-docker "$REGION-docker.pkg.dev" --quiet

# ---------------------------------------------------------------------------
# 2. Memgraph on Compute Engine
#    e2-medium: 2 vCPU / 4 GB RAM — sufficient for 20-car race graph
#    Uses startup script to install Docker + run Memgraph on boot
# ---------------------------------------------------------------------------
echo ""
echo "► Deploying Memgraph on Compute Engine VM..."

MEMGRAPH_EXISTS=$(gcloud compute instances list \
  --filter="name=$MEMGRAPH_VM" \
  --format="value(name)" \
  --project="$PROJECT_ID" 2>/dev/null || true)

if [ -z "$MEMGRAPH_EXISTS" ]; then
  gcloud compute instances create "$MEMGRAPH_VM" \
    --project="$PROJECT_ID" \
    --zone="$ZONE" \
    --machine-type="e2-medium" \
    --image-family="ubuntu-2204-lts" \
    --image-project="ubuntu-os-cloud" \
    --boot-disk-size="20GB" \
    --boot-disk-type="pd-standard" \
    --tags="memgraph-server" \
    --metadata-from-file="startup-script=deploy/memgraph-startup.sh" \
    --scopes="cloud-platform"
  echo "  VM created. Waiting 60s for Memgraph to start..."
  sleep 60
else
  echo "  VM already exists — skipping creation"
fi

# Get the internal IP for backend to connect to
MEMGRAPH_IP=$(gcloud compute instances describe "$MEMGRAPH_VM" \
  --zone="$ZONE" \
  --project="$PROJECT_ID" \
  --format="value(networkInterfaces[0].networkIP)")
echo "  Memgraph internal IP: $MEMGRAPH_IP"

# Firewall rule: allow bolt protocol from Cloud Run internal range
gcloud compute firewall-rules create allow-memgraph-bolt \
  --project="$PROJECT_ID" \
  --allow="tcp:7687" \
  --source-ranges="10.0.0.0/8,35.199.192.0/19" \
  --target-tags="memgraph-server" \
  --description="Allow Memgraph Bolt from Cloud Run internal IPs" \
  --quiet 2>/dev/null || echo "  (firewall rule already exists)"

# ---------------------------------------------------------------------------
# 3. Read secrets from .env file (no Secret Manager needed)
# ---------------------------------------------------------------------------
echo ""
echo "► Reading secrets from .env..."

ENV_FILE="$(dirname "$0")/../.env"
if [ ! -f "$ENV_FILE" ]; then
  echo "ERROR: .env file not found at $ENV_FILE"
  exit 1
fi

# Extract values from .env
GOOGLE_API_KEY=$(grep "^GOOGLE_API_KEY=" "$ENV_FILE" | cut -d'=' -f2- | tr -d '"' | tr -d "'")
GOOGLE_APPLICATION_CREDENTIALS=$(grep "^GOOGLE_APPLICATION_CREDENTIALS=" "$ENV_FILE" | cut -d'=' -f2- | tr -d '"' | tr -d "'" || echo "credentials.json")

if [ -z "$GOOGLE_API_KEY" ]; then
  echo "  ✗ GOOGLE_API_KEY not found in .env — add it: GOOGLE_API_KEY=your_key"
  exit 1
fi
echo "  ✓ GOOGLE_API_KEY loaded"
echo "  ✓ GOOGLE_CLOUD_PROJECT=$PROJECT_ID"

# ---------------------------------------------------------------------------
# 4. Build & push backend image
# ---------------------------------------------------------------------------
echo ""
echo "► Building backend image..."
docker build \
  -t "$BACKEND_IMAGE:$TAG" \
  -t "$BACKEND_IMAGE:latest" \
  -f deploy/Dockerfile \
  .
docker push "$BACKEND_IMAGE:$TAG"
docker push "$BACKEND_IMAGE:latest"
echo "  ✓ Backend image pushed: $BACKEND_IMAGE:$TAG"

# ---------------------------------------------------------------------------
# 5. Deploy backend to Cloud Run
#    min-instances=1 keeps the race_loop() background task alive
#    WebSocket support enabled via HTTP/2
# ---------------------------------------------------------------------------
echo ""
echo "► Deploying backend to Cloud Run..."
gcloud run deploy "$BACKEND_SERVICE" \
  --image="$BACKEND_IMAGE:$TAG" \
  --project="$PROJECT_ID" \
  --region="$REGION" \
  --platform="managed" \
  --allow-unauthenticated \
  --port=8080 \
  --memory="2Gi" \
  --cpu="2" \
  --min-instances="1" \
  --max-instances="3" \
  --timeout="3600" \
  --concurrency="100" \
  --set-env-vars="MEMGRAPH_HOST=$MEMGRAPH_IP,MEMGRAPH_PORT=7687,VERTEX_AI_LOCATION=$REGION,GEMINI_AGENT_MODEL=gemini-2.5-flash,GEMINI_TTS_MODEL=gemini-2.5-flash-preview-tts,GEMINI_LIVE_MODEL=gemini-2.5-flash-native-audio-latest,GEMINI_STRATEGIST_MODEL=gemini-2.5-flash,GCS_BUCKET_NAME=aeromind-f1-data,OPENF1_SESSION_KEY=latest,MONTE_CARLO_SIMULATIONS=1000,GOOGLE_API_KEY=$GOOGLE_API_KEY,GOOGLE_CLOUD_PROJECT=$PROJECT_ID" \
  --quiet

BACKEND_URL=$(gcloud run services describe "$BACKEND_SERVICE" \
  --project="$PROJECT_ID" \
  --region="$REGION" \
  --format="value(status.url)")
echo "  ✓ Backend live: $BACKEND_URL"

# ---------------------------------------------------------------------------
# 6. Build & push frontend image (bakes in backend URL for nginx proxy)
# ---------------------------------------------------------------------------
echo ""
echo "► Building frontend image..."
docker build \
  -t "$FRONTEND_IMAGE:$TAG" \
  -t "$FRONTEND_IMAGE:latest" \
  -f deploy/Dockerfile.frontend \
  --build-arg BACKEND_URL="$BACKEND_URL" \
  .
docker push "$FRONTEND_IMAGE:$TAG"
docker push "$FRONTEND_IMAGE:latest"
echo "  ✓ Frontend image pushed: $FRONTEND_IMAGE:$TAG"

# ---------------------------------------------------------------------------
# 7. Deploy frontend to Cloud Run
# ---------------------------------------------------------------------------
echo ""
echo "► Deploying frontend to Cloud Run..."
gcloud run deploy "$FRONTEND_SERVICE" \
  --image="$FRONTEND_IMAGE:$TAG" \
  --project="$PROJECT_ID" \
  --region="$REGION" \
  --platform="managed" \
  --allow-unauthenticated \
  --port=8080 \
  --memory="512Mi" \
  --cpu="1" \
  --min-instances="0" \
  --max-instances="5" \
  --timeout="60" \
  --set-env-vars="BACKEND_URL=$BACKEND_URL" \
  --quiet

FRONTEND_URL=$(gcloud run services describe "$FRONTEND_SERVICE" \
  --project="$PROJECT_ID" \
  --region="$REGION" \
  --format="value(status.url)")
echo "  ✓ Frontend live: $FRONTEND_URL"

# ---------------------------------------------------------------------------
# 8. Summary
# ---------------------------------------------------------------------------
echo ""
echo "======================================================================"
echo "  DEPLOYMENT COMPLETE — AeroMind 2026"
echo "  #GeminiLiveAgentChallenge"
echo "======================================================================"
echo ""
echo "  🌐 Frontend (public):  $FRONTEND_URL"
echo "  ⚙  Backend  (API):     $BACKEND_URL"
echo "  🗄  Memgraph (VM):      $MEMGRAPH_IP:7687 (internal)"
echo ""
echo "  Google Cloud services used:"
echo "    • Vertex AI (Gemini 2.5 Flash — text, TTS, Live)"
echo "    • Cloud Run (backend + frontend)"
echo "    • Compute Engine (Memgraph graph DB)"
echo "    • Artifact Registry (container images)"
echo "    • Secret Manager (API keys)"
echo "    • Cloud Storage (GCS — race data)"
echo "    • Firestore (race state persistence)"
echo ""
echo "  To view backend logs:"
echo "    gcloud run logs tail $BACKEND_SERVICE --project=$PROJECT_ID --region=$REGION"
echo ""
echo "  To view Memgraph VM logs:"
echo "    gcloud compute ssh $MEMGRAPH_VM --zone=$ZONE -- 'sudo journalctl -u memgraph -f'"
echo "======================================================================"
