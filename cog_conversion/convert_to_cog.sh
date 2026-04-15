#!/bin/bash
# convert_to_cog.sh
# Downloads TIFs from GCS, converts to COG with average resampling, and uploads to a new bucket.
# Requires: gsutil, gdal_translate

SOURCE_BUCKET="smp-ee-files"
SOURCE_PREFIX="30m_land_sent/"

DEST_BUCKET="akveg-data"
DEST_PREFIX="disturbance/potter_cnn/v20260414/"

# Create a temporary directory
TEMP_DIR="tmp_cog_convert"
mkdir -p "$TEMP_DIR"

# List all .tif files in the source bucket
echo "Listing files in gs://${SOURCE_BUCKET}/${SOURCE_PREFIX}..."
FILES=$(gsutil ls -r "gs://${SOURCE_BUCKET}/${SOURCE_PREFIX}**.tif")

# Count files
FILE_COUNT=$(echo "$FILES" | wc -l)
echo "Found $FILE_COUNT files."

# Function to process a single file
process_file() {
    local GCS_PATH="$1"
    
    # Extract relative path (e.g., 2001/91.tif)
    local REL_PATH="${GCS_PATH#gs://${SOURCE_BUCKET}/${SOURCE_PREFIX}}"
    local LOCAL_DIR=$(dirname "$REL_PATH")
    local FILENAME=$(basename "$REL_PATH")
    
    mkdir -p "$TEMP_DIR/$LOCAL_DIR"
    local LOCAL_IN="$TEMP_DIR/$REL_PATH"
    local LOCAL_OUT="$TEMP_DIR/${REL_PATH%.tif}_cog.tif"
    local DEST_PATH="gs://${DEST_BUCKET}/${DEST_PREFIX}${REL_PATH}"

    # Check if file already exists in destination to avoid redundant processing
    if gsutil -q stat "$DEST_PATH"; then
        echo "Skipping $GCS_PATH (already exists in $DEST_PATH)"
        return
    fi

    echo "Processing $REL_PATH..."
    
    # Download
    gsutil -q cp "$GCS_PATH" "$LOCAL_IN"
    
    # Convert to COG with average resampling
    # We use DEFLATE compression for efficiency; AVERAGE for overviews.
    gdal_translate -of COG -co COMPRESS=DEFLATE -co RESAMPLING=AVERAGE "$LOCAL_IN" "$LOCAL_OUT"
    
    # Upload
    gsutil -q cp "$LOCAL_OUT" "$DEST_PATH"
    
    # Cleanup
    rm "$LOCAL_IN" "$LOCAL_OUT"
    echo "Done $REL_PATH"
}

export -f process_file
export SOURCE_BUCKET SOURCE_PREFIX DEST_BUCKET DEST_PREFIX TEMP_DIR

# Run in parallel using xargs (e.g., 4 processes)
echo "$FILES" | xargs -n 1 -P 4 -I {} bash -c 'process_file "{}"'

echo "All conversions complete."
rmdir "$TEMP_DIR"
