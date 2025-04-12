#PROJECT_ID=kano-456408 
PROJECT_ID=prompt-engineering-79711
docker build -t gcr.io/$PROJECT_ID/kano-app .
gcloud auth login
gcloud config set project $PROJECT_ID
docker push gcr.io/$PROJECT_ID/kano-app

gcloud services enable run.googleapis.com
gcloud run deploy kano-app \
  --image gcr.io/$PROJECT_ID/kano-app \
  --platform managed \
  --region us-central1 \
  --allow-unauthenticated

