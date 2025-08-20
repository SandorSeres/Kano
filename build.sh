#!/bin/bash

# Hibakezelés: ha bármely parancs hibára fut, a script is leáll
set -e


# Itt állíthatod be a régiót és a kívánt bucket, app  nevet.
BUCKET_NAME="haziorvosai-responses"
BUCKET_LOCATION="us-central1"
APP_NAME="kano-app"
SERVICE_NAME="kano-app"
REGION="us-central1"

# 1. Google Cloud SDK-ba való bejelentkezés
echo "Bejelentkezés a Google Cloud SDK-ba..."
gcloud auth login

# 2. Google Cloud projekt beállítása
PROJECT_ID="kano-app1"
echo "Projekt kiválasztása: $PROJECT_ID"
gcloud config set project "$PROJECT_ID"

# 3. Szükséges API-k engedélyezése: Cloud Run, Container Registry, Storage
# Ha a Bucket is kell, a Storage API is hasznos lehet (storage-component.googleapis.com).
echo "Cloud Run, Container Registry és Storage API-k engedélyezése..."
gcloud services enable run.googleapis.com
gcloud services enable containerregistry.googleapis.com
gcloud services enable storage-component.googleapis.com

# 4. Docker hitelesítés a Google Container Registry-hez
echo "Docker hitelesítés a Google Container Registry-hez..."
gcloud auth configure-docker

# 5. (Opcionális) Bucket létrehozása, ha még nem létezik
echo "Ellenőrizzük, hogy létezik-e a bucket: gs://$BUCKET_NAME"
if gsutil ls -b "gs://$BUCKET_NAME" > /dev/null 2>&1; then
  echo "A(z) $BUCKET_NAME bucket már létezik."
else
  echo "Bucket létrehozása: gs://$BUCKET_NAME"
  gsutil mb -p "$PROJECT_ID" -l "$BUCKET_LOCATION" "gs://$BUCKET_NAME"
fi

# 6. Docker image buildelése
IMAGE_TAG="gcr.io/$PROJECT_ID/$APP_NAME:latest"
echo "Docker image buildelése: $IMAGE_TAG"
docker build -t "$IMAGE_TAG" .

# 7. Docker image feltöltése a Google Container Registry-be
echo "Docker image feltöltése a Google Container Registry-be..."
docker push "$IMAGE_TAG"

# 8. Alkalmazás deployolása a Google Cloud Run-ra
echo "Alkalmazás deployolása a Cloud Run-ra..."
gcloud run deploy "$SERVICE_NAME" \
  --image "$IMAGE_TAG" \
  --platform managed \
  --region "$REGION" \
  --allow-unauthenticated

# 9. Az alkalmazás URL-jének megjelenítése
URL=$(gcloud run services describe "$SERVICE_NAME" --region "$REGION" --format "value(status.url)")
echo "Az alkalmazás sikeresen telepítve. Elérhető itt: $URL"

# 10. (Opcionális) Környezeti változók beállítása
# Ha hozzá szeretnél adni környezeti változókat (pl. a bucket nevét),
# ki tudod egészíteni így (távolítsd el a komment jeleket):
# echo "Környezeti változók beállítása..."
# gcloud run services update "$SERVICE_NAME" \
#   --update-env-vars BUCKET_NAME=$BUCKET_NAME,VAR2=value2

# 11. (Opcionális) Secret Manager használata
# echo -n "SECRET_VALUE" | gcloud secrets create SECRET_NAME --data-file=-
# gcloud run services update "$SERVICE_NAME" \
#   --update-secrets ENV_VAR_NAME=SECRET_NAME:latest

echo "Minden lépés sikeresen lefutott!"


