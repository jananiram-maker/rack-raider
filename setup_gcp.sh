#!/bin/bash
# Shell script to provision GCP resources for naturallyEasy
set -e

PROJECT_ID=${1:-$GCP_PROJECT_ID}
REGION=${2:-"us-central1"}
BUCKET_NAME=${3:-"wardrobe_sfs"}
DATASET_NAME=${4:-"naturally_easy_analytics"}

if [ -z "$PROJECT_ID" ]; then
    echo "Usage: ./setup_gcp.sh <PROJECT_ID> [REGION] [BUCKET_NAME] [DATASET_NAME]"
    exit 1
fi

echo "=== Provisioning GCP Resources for naturallyEasy ==="
gcloud config set project "$PROJECT_ID"

echo "[1/6] Enabling APIs..."
gcloud services enable \
    aiplatform.googleapis.com \
    storage.googleapis.com \
    firestore.googleapis.com \
    bigquery.googleapis.com \
    run.googleapis.com \
    artifactregistry.googleapis.com \
    cloudbuild.googleapis.com

echo "[2/6] Creating GCS Bucket: gs://$BUCKET_NAME..."
gcloud storage buckets create "gs://$BUCKET_NAME" \
    --location="$REGION" \
    --uniform-bucket-level-access \
    --public-access-prevention || true

echo "[3/6] Creating Firestore Database in Native Mode..."
gcloud firestore databases create \
    --location="$REGION" \
    --type=firestore-native --quiet || true

echo "[4/6] Creating BigQuery Dataset: $DATASET_NAME..."
bq --location="$REGION" mk --dataset "${PROJECT_ID}:${DATASET_NAME}" || true

echo "[5/6] Creating BigQuery Tables (Partitioned & Clustered)..."
bq mk --table --clustering_fields=user_id,category "${PROJECT_ID}:${DATASET_NAME}.Items" \
    item_id:STRING,user_id:STRING,category:STRING,occasion:STRING,material:STRING,season_tag:STRING,wear_frequency_expectation:STRING,embedding_id:STRING,item_gs_uri:STRING || true

bq mk --table --time_partitioning_field=worn_date --clustering_fields=user_id "${PROJECT_ID}:${DATASET_NAME}.Outfits" \
    outfit_id:STRING,user_id:STRING,worn_date:DATE,occasion:STRING,weather_summary:STRING,outfit_gs_uri:STRING || true

bq mk --table --clustering_fields=outfit_id,item_id "${PROJECT_ID}:${DATASET_NAME}.Outfit_Items" \
    outfit_item_id:STRING,outfit_id:STRING,item_id:STRING || true

echo "[6/6] Deploying to Cloud Run..."
gcloud run deploy naturally-easy-agent \
    --source . \
    --region="$REGION" \
    --platform=managed \
    --allow-unauthenticated \
    --set-env-vars="GCP_PROJECT_ID=$PROJECT_ID,GCS_BUCKET_NAME=$BUCKET_NAME,BIGQUERY_DATASET=$DATASET_NAME,DEFAULT_GEMINI_MODEL=gemini-3.5-flash-lite"

echo "=== Deployment Successfully Completed! ==="
