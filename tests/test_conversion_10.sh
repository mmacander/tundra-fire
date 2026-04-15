#!/bin/bash
# test_conversion_10.sh
# Tests conversion of 10 tiles from 2001.

SOURCE_BUCKET="smp-ee-files"
SOURCE_PREFIX="30m_land_sent/"
DEST_BUCKET="akveg-data"
DEST_PREFIX="disturbance/potter_cnn/v20260414/"
TEMP_DIR="tmp_test_cog"

mkdir -p "$TEMP_DIR"

# Get 10 tiles from 2001
FILES=$(gsutil ls "gs://${SOURCE_BUCKET}/${SOURCE_PREFIX}2001/*.tif" | head -n 10)

process_file() {
    local GCS_PATH="$1"
    local REL_PATH="${GCS_PATH#gs://${SOURCE_BUCKET}/${SOURCE_PREFIX}}"
    local LOCAL_DIR=$(dirname "$REL_PATH")
    mkdir -p "$TEMP_DIR/$LOCAL_DIR"
    local LOCAL_IN="$TEMP_DIR/$REL_PATH"
    local LOCAL_OUT="${LOCAL_IN%.tif}_cog.tif"
    local DEST_PATH="gs://${DEST_BUCKET}/${DEST_PREFIX}${REL_PATH}"

    echo "Converting $REL_PATH -> $DEST_PATH"
    gsutil -q cp "$GCS_PATH" "$LOCAL_IN"
    gdal_translate -of COG -co COMPRESS=DEFLATE -co RESAMPLING=AVERAGE "$LOCAL_IN" "$LOCAL_OUT"
    gsutil -q cp "$LOCAL_OUT" "$DEST_PATH"
    rm "$LOCAL_IN" "$LOCAL_OUT"
}

export -f process_file
export SOURCE_BUCKET SOURCE_PREFIX DEST_BUCKET DEST_PREFIX TEMP_DIR

echo "$FILES" | xargs -n 1 -P 4 -I {} bash -c 'process_file "{}"'

echo "Test conversion of 10 tiles complete."
rm -rf "$TEMP_DIR"
