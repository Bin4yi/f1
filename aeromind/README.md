# AeroMind v5

## Deploy to Cloud Run

```bash
gcloud builds submit --config deploy/cloudbuild.yaml
gcloud run deploy aeromind --image gcr.io/PROJECT_ID/aeromind:latest --region us-central1
gcloud run services describe aeromind --region us-central1 --format='value(status.url)'
```
