"""
ingest_full_collection_v20260430.py

Submits native GEE ingestion tasks for all v20260430 COG tiles.

COG-backed approach (register_full_collection_v20260430.py):
  Creates an external asset with gcs_location — pixels served from GCS at
  query time. Requires ongoing bucket read access for every user query.

Native ingestion (this script):
  Submits image:import tasks — GEE copies pixels into its own internal storage.
  After each task completes, the asset has no GCS dependency; end-user access
  is controlled by EE asset ACLs only, eliminating the bucket-permission
  failure mode that affects the COG-backed collection.

Tasks are async (fire-and-forget). Each tile takes seconds to minutes.
Re-running is safe: existing assets are skipped. See RERUN NOTE below.

GCP project
-----------
  fisl-tundra-fire is used for both quota/billing and asset ownership.
  The Earth Engine API is enabled on this project. API costs for ingestion
  land here rather than on akveg-map.

GCS access during ingestion
---------------------------
  GEE's ingestion pipeline reads source COGs using its own service account,
  not the user's credentials. That service account must have at minimum
  roles/storage.objectViewer on gs://akveg-data for the import to succeed.

  To find the GEE service account for fisl-tundra-fire:
    gcloud projects get-iam-policy fisl-tundra-fire \\
      --flatten='bindings[].members' \\
      --filter='bindings.role:roles/earthengine.serviceAgent' \\
      --format='value(bindings.members)'

  Grant it object read access if imports fail with permission errors:
    gsutil iam ch serviceAccount:<SA>:roles/storage.objectViewer \\
      gs://akveg-data

  NOTE: the COG-backed collection already works (intermittently) from this
  bucket, which suggests the EE service account has some access. Verify
  before assuming a grant is needed.

Per-band pyramiding
-------------------
  Probability (Band 1, Byte, continuous 0-255) : MEAN
  Burn_Mask   (Band 2, Byte, binary 0/1)        : MODE

Collection
----------
  This script targets a NEW collection separate from the COG-backed one.
  Create it before running:
    ~/miniconda3/bin/conda run -n ee earthengine create collection \\
      projects/fisl-tundra-fire/assets/potter_fire_v20260430_ingested

RERUN NOTE
----------
  asset_exists() checks for a completed asset. A tile whose ingestion task
  is still running returns 404 and will be re-submitted. To avoid duplicate
  tasks, wait for all tasks to complete before re-running, or filter the
  input list to only tiles known to have failed.
  Monitor task progress at: https://code.earthengine.google.com/tasks
"""

import ee
import json
import time
import random
from google.cloud import storage
from google.auth.transport.requests import AuthorizedSession
from datetime import datetime, timezone
import concurrent.futures

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
PROJECT = 'fisl-tundra-fire'   # quota/billing and asset owner
GCS_BUCKET = 'akveg-data'
GCS_PREFIX = 'disturbance/potter_cnn/v20260430/'
EE_COLLECTION = f'projects/{PROJECT}/assets/potter_fire_v20260430_ingested'

MAX_WORKERS = 5   # concurrent task submissions
MAX_RETRIES = 5   # retries on 429 rate-limit responses

INGEST_URL = (
    f'https://earthengine.googleapis.com/v1alpha'
    f'/projects/{PROJECT}/image:import'
)

# ---------------------------------------------------------------------------
# Setup
# ---------------------------------------------------------------------------
try:
    ee.Initialize(project=PROJECT)
except Exception:
    ee.Authenticate()
    ee.Initialize(project=PROJECT)

session = AuthorizedSession(
    ee.data.get_persistent_credentials().with_quota_project(PROJECT)
)


def get_tif_list():
    """List all year/tile COGs, skipping the smp-ee-files archive copy."""
    print(f'Listing COGs in gs://{GCS_BUCKET}/{GCS_PREFIX}...')
    client = storage.Client(project=PROJECT)
    blobs = client.bucket(GCS_BUCKET).list_blobs(prefix=GCS_PREFIX)
    tifs = []
    for blob in blobs:
        if 'smp-ee-files' in blob.name or 'logs/' in blob.name:
            continue
        if blob.name.endswith('.tif'):
            tifs.append(f'gs://{GCS_BUCKET}/{blob.name}')
    return tifs


def asset_exists(asset_id):
    """Return True if a completed asset already exists at asset_id."""
    try:
        ee.data.getAsset(asset_id)
        return True
    except ee.EEException:
        return False


def submit_ingestion(cog_uri):
    """
    Submit one native ingestion task for cog_uri.

    Returns (asset_name, status) where status is one of:
      'exists'    — completed asset already present, skipped
      'submitted' — ingestion task accepted, operation name logged
      int         — HTTP error code
    """
    parts = cog_uri.split('/')
    filename = parts[-1]
    year_str = parts[-2]
    if not year_str.isdigit():
        return None

    year = int(year_str)
    tile_id = filename.replace('.tif', '')
    asset_name = f'y{year}_t{tile_id}'
    asset_id = f'{EE_COLLECTION}/{asset_name}'

    if asset_exists(asset_id):
        return (asset_name, 'exists')

    dt_start = datetime(year, 1, 1, tzinfo=timezone.utc)
    dt_end = datetime(year + 1, 1, 1, tzinfo=timezone.utc)

    manifest = {
        'imageManifest': {
            'name': asset_id,
            'tilesets': [
                {'sources': [{'uris': [cog_uri]}]}
            ],
            # Explicit band specs set pyramiding per band. Band order matches
            # the COG (Band 1 = Probability, Band 2 = Burn_Mask).
            'bands': [
                {'id': 'Probability', 'tilesetBandIndex': 0, 'pyramidingPolicy': 'MEAN'},
                {'id': 'Burn_Mask',   'tilesetBandIndex': 1, 'pyramidingPolicy': 'MODE'},
            ],
            'properties': {
                'year':       year,
                'tile_id':    tile_id,
                'source_uri': cog_uri,
            },
            'startTime': dt_start.isoformat(),
            'endTime':   dt_end.isoformat(),
        }
    }

    for attempt in range(MAX_RETRIES):
        resp = session.post(url=INGEST_URL, data=json.dumps(manifest))

        if resp.status_code == 200:
            op_name = resp.json().get('name', 'unknown-operation')
            print(f'  submitted {asset_name} → {op_name}')
            return (asset_name, 'submitted')

        if resp.status_code == 429:
            time.sleep((2 ** attempt) + random.random())
            continue

        # 400 "already exists" can appear if a prior run's task is still
        # ingesting (the manifest was accepted but the asset isn't queryable
        # yet via getAsset). Treat as effectively in-flight.
        if resp.status_code == 400 and 'already exists' in resp.text.lower():
            print(f'  in-flight {asset_name} (task already submitted)')
            return (asset_name, 'exists')

        print(f'  ERROR {asset_name}: HTTP {resp.status_code} — {resp.text[:300]}')
        return (asset_name, resp.status_code)

    print(f'  ERROR {asset_name}: exhausted retries on 429')
    return (asset_name, 429)


def main():
    tifs = get_tif_list()
    print(f'Found {len(tifs)} COG tiles.\n')

    counts = {'submitted': 0, 'exists': 0, 'error': 0}
    errors = []

    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        future_to_uri = {executor.submit(submit_ingestion, uri): uri for uri in tifs}
        for i, future in enumerate(concurrent.futures.as_completed(future_to_uri), 1):
            result = future.result()
            if result is None:
                continue
            asset_name, status = result
            if status == 'submitted':
                counts['submitted'] += 1
            elif status == 'exists':
                counts['exists'] += 1
            else:
                counts['error'] += 1
                errors.append((asset_name, status))

            if i % 500 == 0:
                print(f'Progress {i}/{len(tifs)}: {counts}')

    print(f'\nDone.')
    print(f'  Submitted : {counts["submitted"]}')
    print(f'  Skipped   : {counts["exists"]}')
    print(f'  Errors    : {counts["error"]}')

    if errors:
        print('\nFailed tiles (re-run to retry):')
        for name, code in errors:
            print(f'  {name}: {code}')

    print('\nMonitor ingestion tasks:')
    print('  https://code.earthengine.google.com/tasks')


if __name__ == '__main__':
    main()
