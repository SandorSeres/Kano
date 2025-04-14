#!/bin/bash

# Ha bármely parancs hibára fut, álljon le a script
set -e

# 1. Beállítások
PROJECT_ID="kano-456408"
REGION="us-central1"
SERVICE_NAME="kano-app"
IMAGE_NAME="kano-app"
BUCKET_NAME="kano-responses"

#PROJECT_ID="prompt-engineering-79711"
#REGION="us-central1"
#SERVICE_NAME="kano-app"
#IMAGE_NAME="kano-app"
#BUCKET_NAME="prompt_engineering-responses"

# 2. (Opcionális) GCP bejelentkezés és projekt kiválasztása
echo "Bejelentkezés a Google Cloud SDK-ba..."
gcloud auth login

echo "Projekt beállítása: $PROJECT_ID"
gcloud config set project "$PROJECT_ID"

# 3. Cloud Run szolgáltatás törlése
echo "Cloud Run szolgáltatás törlése: $SERVICE_NAME a(z) $REGION régióban..."
echo y | gcloud run services delete "$SERVICE_NAME" --region "$REGION"

# 4. Docker image törlése a Container Registry-ből
echo "Docker image törlése: gcr.io/$PROJECT_ID/$IMAGE_NAME:latest"
echo y | gcloud container images delete "gcr.io/$PROJECT_ID/$IMAGE_NAME:latest"

# 5. GCS bucket törlése (benne lévő fájlokkal együtt)
# Ha a bucket használata során létrejöhettek alkönyvtárak (objektumok), akkor 
# a -r kapcsoló mindet rekurzívan törli.
echo "Bucket törlése: gs://$BUCKET_NAME"
echo y | gsutil rm -r "gs://$BUCKET_NAME/"

echo "Minden kijelölt erőforrás sikeresen törlésre került!"

