#!/bin/bash

# Hibakezelés: ha bármely parancs hibára fut, a script is leáll
set -e

# ---- 🟩 Konfiguráció ----
PROJECT_ID="politikai-dashboard-1234"  # Cseréld a saját projektedre!
REGION="europe-west1"
BUCKET_NAME="politikai-indikator-adatok"
BUCKET_LOCATION="EU"
APP_NAME="politikai-dashboard"
SERVICE_NAME="politikai-dashboard"

# ---- 🟩 GCP-bejelentkezés és projekt beállítás ----
echo "Google Cloud SDK hitelesítés..."
gcloud auth login
gcloud config set project "$PROJECT_ID"

# ---- 🟩 API-k engedélyezése ----
echo "API-k engedélyezése..."
gcloud services enable run.googleapis.com
gcloud services enable containerregistry.googleapis.com
gcloud services enable storage-component.googleapis.com

# ---- 🟩 Bucket ellenőrzés / létrehozás ----
echo "Bucket ellenőrzése: gs://$BUCKET_NAME"
if gsutil ls -b "gs://$BUCKET_NAME" > /dev/null 2>&1; then
  echo "Bucket már létezik."
else
  echo "Bucket létrehozása: gs://$BUCKET_NAME"
  gsutil mb -p "$PROJECT_ID" -l "$BUCKET_LOCATION" "gs://$BUCKET_NAME"
fi

# ---- 🟩 Docker hitelesítés ----
echo "Docker hitelesítés a Google Container Registry-hez..."
gcloud auth configure-docker

# ---- 🟩 Docker image build ----
IMAGE_TAG="gcr.io/$PROJECT_ID/$APP_NAME:latest"
echo "Docker image buildelése: $IMAGE_TAG"
docker build -t "$IMAGE_TAG" .

# ---- 🟩 Docker image push ----
echo "Docker image feltöltése a Container Registry-be..."
docker push "$IMAGE_TAG"

# ---- 🟩 Cloud Run deploy ----
echo "Cloud Run deploy..."
gcloud run deploy "$SERVICE_NAME" \
  --image "$IMAGE_TAG" \
  --platform managed \
  --region "$REGION" \
  --allow-unauthenticated \
  --set-env-vars "BUCKET_NAME=$BUCKET_NAME"

# ---- 🟩 URL kiírása ----
URL=$(gcloud run services describe "$SERVICE_NAME" --region "$REGION" --format "value(status.url)")
echo "Dashboard sikeresen deployolva! Elérhető itt: $URL"

# ---- 🟩 Secret Manager (opcionális) ----
# Ha a service_account.json fájlt titkosítva szeretnéd kezelni:
# echo "Secret Manager integráció (opcionális)..."
# gcloud secrets create dashboard-sa-key --data-file=service_account.json
# gcloud run services update "$SERVICE_NAME" \
#   --update-secrets SERVICE_ACCOUNT_JSON=dashboard-sa-key:latest

echo "🚀 A teljes deploy sikeresen lefutott!"

