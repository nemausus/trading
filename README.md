## Deployment

gcloud run deploy covered_calls --source . \
--region us-central1 \
--allow-unauthenticated \
--service-account="cloud-run-app-runner@<PROJECT_ID>.iam.gserviceaccount.com" \
--set-secrets="SCHWAB_CLIENT_ID=client_id:latest,SCHWAB_CLIENT_SECRET=client_secret:latest,IND_ACCOUNT=ind_account:latest,IRA_ACCOUNT=ira_account:latest,SCHWAB_ENCRYPTION_KEY=encryption_key:latest" \
--set-env-vars="SCHWAB_REDIRECT_URI=https://<YOUR_DOMAIN>/api/auth/schwab/callback"
