# PowerShell script to provision GCP resources for naturallyEasy
param (
    [Parameter(Mandatory=$true)]
    [string]$ProjectId,

    [string]$Region = "us-central1",
    [string]$BucketName = "wardrobe_sfs",
    [string]$DatasetName = "naturally_easy_analytics"
)

Write-Host "=== NaturallyEasy GCP Resource Provisioning ===" -ForegroundColor Cyan

# 1. Set Active Project
Write-Host "`n[1/6] Setting active GCP project: $ProjectId"
gcloud config set project $ProjectId

# 2. Enable Required APIs
Write-Host "`n[2/6] Enabling Google Cloud Services..."
gcloud services enable `
    aiplatform.googleapis.com `
    storage.googleapis.com `
    firestore.googleapis.com `
    bigquery.googleapis.com `
    run.googleapis.com `
    artifactregistry.googleapis.com `
    cloudbuild.googleapis.com

# 3. Create Cloud Storage Bucket
Write-Host "`n[3/6] Creating GCS Bucket: gs://$BucketName..."
gcloud storage buckets create gs://$BucketName `
    --location=$Region `
    --uniform-bucket-level-access `
    --public-access-prevention

# 4. Create Firestore in Native Mode
Write-Host "`n[4/6] Creating Firestore (Native Mode) in $Region..."
gcloud firestore databases create `
    --location=$Region `
    --type=firestore-native `
    --quiet

# 5. Create BigQuery Dataset and Tables
Write-Host "`n[5/6] Creating BigQuery Dataset: $DatasetName..."
bq --location=$Region mk --dataset "${ProjectId}:${DatasetName}"

Write-Host "Creating BigQuery Table: Items (Clustered by user_id)..."
bq mk --table `
    --clustering_fields=user_id,category `
    "${ProjectId}:${DatasetName}.Items" `
    item_id:STRING,user_id:STRING,category:STRING,occasion:STRING,material:STRING,season_tag:STRING,wear_frequency_expectation:STRING,embedding_id:STRING,item_gs_uri:STRING

Write-Host "Creating BigQuery Table: Outfits (Partitioned by worn_date, Clustered by user_id)..."
bq mk --table `
    --time_partitioning_field=worn_date `
    --clustering_fields=user_id `
    "${ProjectId}:${DatasetName}.Outfits" `
    outfit_id:STRING,user_id:STRING,worn_date:DATE,occasion:STRING,weather_summary:STRING,outfit_gs_uri:STRING

Write-Host "Creating BigQuery Table: Outfit_Items..."
bq mk --table `
    --clustering_fields=outfit_id,item_id `
    "${ProjectId}:${DatasetName}.Outfit_Items" `
    outfit_item_id:STRING,outfit_id:STRING,item_id:STRING

# 6. Deploy to Cloud Run
Write-Host "`n[6/6] Building and Deploying to Google Cloud Run..."
gcloud run deploy naturally-easy-agent `
    --source . `
    --region=$Region `
    --platform=managed `
    --allow-unauthenticated `
    --set-env-vars="GCP_PROJECT_ID=$ProjectId,GCS_BUCKET_NAME=$BucketName,BIGQUERY_DATASET=$DatasetName,DEFAULT_GEMINI_MODEL=gemini-3.5-flash-lite"

Write-Host "`n=== Deployment Complete! ===" -ForegroundColor Green
