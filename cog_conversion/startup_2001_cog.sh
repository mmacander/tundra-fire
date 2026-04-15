#!/bin/bash
# startup_2001_cog.sh
# Startup script for GCP Spot VM to convert 2001 TIFFs to COG.

LOG_FILE="/var/log/cog_convert.log"
exec > >(tee -a "$LOG_FILE") 2>&1

echo "Starting conversion at $(date)"

# 1. Setup - GDAL is often not on base images
apt-get update && apt-get install -y gdal-bin

SOURCE_BUCKET="akveg-data"
SOURCE_PREFIX="disturbance/potter_cnn/v20260414/smp-ee-files/30m_land_sent/2001/"
DEST_BUCKET="akveg-data"
DEST_PREFIX="disturbance/potter_cnn/v20260414/2001/"
TEMP_DIR="/tmp/cog_convert"
mkdir -p "$TEMP_DIR"

# 2. Get 2001 Files
FILES=$(gsutil ls "gs://${SOURCE_BUCKET}/${SOURCE_PREFIX}*.tif")

# 3. Process Function
process_file() {
    local GCS_PATH="$1"
    local FILENAME=$(basename "$GCS_PATH")
    local LOCAL_IN="$TEMP_DIR/$FILENAME"
    local LOCAL_OUT="${LOCAL_IN%.tif}_cog.tif"
    local DEST_PATH="gs://${DEST_BUCKET}/${DEST_PREFIX}${FILENAME}"

    # Skip if exists
    if gsutil -q stat "$DEST_PATH"; then
        echo "Skipping $FILENAME (exists)"
        return
    fi

    echo "Processing $FILENAME..."
    gsutil -q cp "$GCS_PATH" "$LOCAL_IN"
    gdal_translate -of COG -co COMPRESS=DEFLATE -co RESAMPLING=AVERAGE "$LOCAL_IN" "$LOCAL_OUT"
    gsutil -q cp "$LOCAL_OUT" "$DEST_PATH"
    rm "$LOCAL_IN" "$LOCAL_OUT"
}

export -f process_file
export SOURCE_BUCKET SOURCE_PREFIX DEST_BUCKET DEST_PREFIX TEMP_DIR

# 4. Run Parallel (8 cores)
echo "$FILES" | xargs -n 1 -P 8 -I {} bash -c 'process_file "{}"'

echo "Conversion of 2001 complete at $(date). Uploading logs..."
gsutil -h "Content-Type:text/plain" cp "$LOG_FILE" "gs://${DEST_BUCKET}/disturbance/potter_cnn/v20260414/logs/2001_conversion_$(date +%Y%m%d_%H%M%S).txt"

# 5. Done - Self Delete
INSTANCE_NAME=$(curl -H "Metadata-Flavor: Google" http://metadata.google.internal/computeMetadata/v1/instance/name)
ZONE=$(curl -H "Metadata-Flavor: Google" http://metadata.google.internal/computeMetadata/v1/instance/zone | cut -d/ -f4)
echo "Self-deleting instance $INSTANCE_NAME in $ZONE..."
gcloud compute instances delete "$INSTANCE_NAME" --zone="$ZONE" --quiet
