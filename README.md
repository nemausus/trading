## Deployment

gcloud run deploy covered-calls --source . \
--region us-central1 \
--allow-unauthenticated \
--service-account="cloud-run-app-runner@<PROJECT_ID>.iam.gserviceaccount.com" \
--set-secrets="SCHWAB_CLIENT_ID=client_id:latest,SCHWAB_CLIENT_SECRET=client_secret:latest,IND_ACCOUNT=ind_account:latest,IRA_ACCOUNT=ira_account:latest,SCHWAB_ENCRYPTION_KEY=encryption_key:latest" \
--set-env-vars="SCHWAB_REDIRECT_URI=https://<YOUR_DOMAIN>/api/auth/schwab/callback,GCP_PROJECT_ID=<PROJECT_ID>,FIRESTORE_DATABASE_ID=<DATABASE_ID>"


## Local setup
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

python -m flask --app app run --debug --port 5000

