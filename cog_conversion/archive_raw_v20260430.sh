#!/bin/bash
# archive_raw_v20260430.sh
# Run locally on mason BEFORE deploying the COG conversion VM.
# Copies raw TIFFs from smp-ee-files into the versioned akveg-data prefix.

set -euo pipefail

SRC="gs://smp-ee-files/30m_land_sent_multiscale/"
DST="gs://akveg-data/disturbance/potter_cnn/v20260430/smp-ee-files/30m_land_sent_multiscale/"

echo "Archiving raw TIFFs to versioned prefix..."
echo "  src: $SRC"
echo "  dst: $DST"
echo "Starting at $(date)"

gsutil -m rsync -r "$SRC" "$DST"

echo "Archive complete at $(date)"
echo "Verify with: gsutil ls -r ${DST} | wc -l"
