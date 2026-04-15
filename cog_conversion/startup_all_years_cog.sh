#!/bin/bash
# startup_all_years_cog.sh
# Startup script for GCP Spot VM to convert all remaining years to COG.

LOG_FILE="/var/log/cog_convert_all.log"
exec > >(tee -a "$LOG_FILE") 2>&1

echo "Starting FULL conversion at $(date)"

# 1. Setup
apt-get update && apt-get install -y gdal-bin

SOURCE_BUCKET="akveg-data"
SOURCE_ROOT="disturbance/potter_cnn/v20260414/smp-ee-files/30m_land_sent"
DEST_BUCKET="akveg-data"
DEST_ROOT="disturbance/potter_cnn/v20260414"
TEMP_DIR="/tmp/cog_convert_all"
mkdir -p "$TEMP_DIR"

# 2. List all .tif files, excluding the already processed 2001 year
echo "Listing all source files..."
ALL_FILES=$(gsutil ls -r "gs://${SOURCE_BUCKET}/${SOURCE_ROOT}/**.tif" | grep -v "/2001/")

# 3. Process Function
process_file() {
    local GCS_PATH="$1"
    
    # Extract relative path from source root (e.g. 2002/91.tif)
    local REL_PATH="${GCS_PATH#gs://${SOURCE_BUCKET}/${SOURCE_ROOT}/}"
    local YEAR_DIR=$(dirname "$REL_PATH")
    local FILENAME=$(basename "$REL_PATH")
    
    local LOCAL_DIR="$TEMP_DIR/$YEAR_DIR"
    mkdir -p "$LOCAL_DIR"
    
    local LOCAL_IN="$TEMP_DIR/$REL_PATH"
    local LOCAL_OUT="${LOCAL_IN%.tif}_cog.tif"
    local DEST_PATH="gs://${DEST_BUCKET}/${DEST_ROOT}/${REL_PATH}"

    # Skip if exists
    if gsutil -q stat "$DEST_PATH"; then
        echo "Skipping $REL_PATH (exists)"
        return
    fi

    echo "Processing $REL_PATH..."
    gsutil -q cp "$GCS_PATH" "$LOCAL_IN"
    
    # COG conversion
    gdal_translate -of COG -co COMPRESS=DEFLATE -co RESAMPLING=AVERAGE "$LOCAL_IN" "$LOCAL_OUT"
    
    # Upload
    gsutil -q cp "$LOCAL_OUT" "$DEST_PATH"
    
    # Cleanup local
    rm "$LOCAL_IN" "$LOCAL_OUT"
}

export -f process_file
export SOURCE_BUCKET SOURCE_ROOT DEST_BUCKET DEST_ROOT TEMP_DIR

# 4. Run Parallel (32 cores for e2-highcpu-32)
echo "$ALL_FILES" | xargs -n 1 -P 32 -I {} bash -c 'process_file "{}"'

echo "FULL Conversion complete at $(date). Uploading logs..."
gsutil -h "Content-Type:text/plain" cp "$LOG_FILE" "gs://${DEST_BUCKET}/${DEST_ROOT}/logs/all_years_conversion_$(date +%Y%m%d_%H%M%S).txt"

# 5. Done - Self Delete
INSTANCE_NAME=$(curl -H "Metadata-Flavor: Google" http://metadata.google.internal/computeMetadata/v1/instance/name)
ZONE=$(curl -H "Metadata-Flavor: Google" http://metadata.google.internal/computeMetadata/v1/instance/zone | cut -d/ -f4)
echo "Self-deleting instance $INSTANCE_NAME in $ZONE..."
gcloud compute instances delete "$INSTANCE_NAME" --zone="$ZONE" --quiet
