#!/bin/bash
# startup_all_years_cog_v20260430.sh
# GCP Spot VM startup script: copy raw TIFFs into versioned prefix, then convert all years to COG.
# Deploy on e2-highcpu-32 for 32-parallel conversion.

LOG_FILE="/var/log/cog_convert_all_v20260430.log"
exec > >(tee -a "$LOG_FILE") 2>&1

echo "Starting v20260430 FULL conversion at $(date)"

# 1. Setup
apt-get update && apt-get install -y gdal-bin

RAW_BUCKET="smp-ee-files"
RAW_PREFIX="30m_land_sent/"

DEST_BUCKET="akveg-data"
VERSION="v20260430"
RAW_ARCHIVE_ROOT="disturbance/potter_cnn/${VERSION}/smp-ee-files/30m_land_sent"
COG_ROOT="disturbance/potter_cnn/${VERSION}"

TEMP_DIR="/tmp/cog_convert_${VERSION}"
mkdir -p "$TEMP_DIR"

# 2. Archive raw TIFFs into versioned prefix (idempotent — skips existing)
echo "Archiving raw TIFFs to gs://${DEST_BUCKET}/${RAW_ARCHIVE_ROOT}/..."
gsutil -m rsync -r -x '.*(?<!\.tif)$' \
    "gs://${RAW_BUCKET}/${RAW_PREFIX}" \
    "gs://${DEST_BUCKET}/${RAW_ARCHIVE_ROOT}/"
echo "Archive complete at $(date)"

# 3. List all archived TIFs
echo "Listing archived source files..."
ALL_FILES=$(gsutil ls -r "gs://${DEST_BUCKET}/${RAW_ARCHIVE_ROOT}/**.tif")

# 4. Process function
process_file() {
    local GCS_PATH="$1"

    local REL_PATH="${GCS_PATH#gs://${DEST_BUCKET}/${RAW_ARCHIVE_ROOT}/}"
    local YEAR_DIR=$(dirname "$REL_PATH")
    local FILENAME=$(basename "$REL_PATH")

    local LOCAL_DIR="$TEMP_DIR/$YEAR_DIR"
    mkdir -p "$LOCAL_DIR"

    local LOCAL_IN="$TEMP_DIR/$REL_PATH"
    local LOCAL_OUT="${LOCAL_IN%.tif}_cog.tif"
    local DEST_PATH="gs://${DEST_BUCKET}/${COG_ROOT}/${REL_PATH}"

    if gsutil -q stat "$DEST_PATH"; then
        echo "Skipping $REL_PATH (exists)"
        return
    fi

    echo "Processing $REL_PATH..."
    gsutil -q cp "$GCS_PATH" "$LOCAL_IN"
    gdal_translate -of COG -co COMPRESS=DEFLATE -co RESAMPLING=AVERAGE "$LOCAL_IN" "$LOCAL_OUT"
    gsutil -q cp "$LOCAL_OUT" "$DEST_PATH"
    rm "$LOCAL_IN" "$LOCAL_OUT"
}

export -f process_file
export DEST_BUCKET RAW_ARCHIVE_ROOT COG_ROOT TEMP_DIR

# 5. Run parallel (32 cores for e2-highcpu-32)
echo "$ALL_FILES" | xargs -n 1 -P 32 -I {} bash -c 'process_file "{}"'

echo "FULL conversion complete at $(date). Uploading log..."
gsutil -h "Content-Type:text/plain" cp "$LOG_FILE" \
    "gs://${DEST_BUCKET}/${COG_ROOT}/logs/all_years_conversion_$(date +%Y%m%d_%H%M%S).txt"

# 6. Self-delete
INSTANCE_NAME=$(curl -H "Metadata-Flavor: Google" http://metadata.google.internal/computeMetadata/v1/instance/name)
ZONE=$(curl -H "Metadata-Flavor: Google" http://metadata.google.internal/computeMetadata/v1/instance/zone | cut -d/ -f4)
echo "Self-deleting instance $INSTANCE_NAME in $ZONE..."
gcloud compute instances delete "$INSTANCE_NAME" --zone="$ZONE" --quiet
