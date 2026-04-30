# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Purpose

Pipeline for ingesting burned area probability rasters (Potter CNN model) into Google Earth Engine. Source TIFFs live in GCS, get converted to Cloud Optimized GeoTIFFs (COGs), then registered as an EE ImageCollection.

## GCP Projects

Two GCP projects are involved — this is a deliberate split, not an inconsistency:

- **`akveg-map`** — billing/quota project. Used for `ee.Initialize()`, `storage.Client()`, and `with_quota_project()`. All API costs land here.
- **`fisl-tundra-fire`** — asset owner project. The EE ImageCollection and all image assets live under `projects/fisl-tundra-fire/assets/...`. HTTP requests to the EE REST API target this project as the resource path, but quota is charged to `akveg-map`.

The COG conversion startup scripts run on GCP VMs; those VMs must have IAM access to both `smp-ee-files` and `akveg-data` buckets, typically via the VM's service account (whichever project the VM is created in).

## Data Locations

- Raw source TIFFs: `gs://smp-ee-files/30m_land_sent/{year}/{tile_id}.tif`
- Raw archive (versioned copy): `gs://akveg-data/disturbance/potter_cnn/{version}/smp-ee-files/30m_land_sent/`
- COGs: `gs://akveg-data/disturbance/potter_cnn/{version}/{year}/{tile_id}.tif`
- EE collection: `projects/fisl-tundra-fire/assets/potter_fire_{version}`
- EE asset IDs: `y{year}_t{tile_id}` (e.g., `y2001_t91`)

## Versioning

Each ingest version gets its own date-stamped suffix (e.g., `v20260430`). The version appears in:
- The GCS COG path under `akveg-data`
- The raw archive path under `akveg-data` (preserving source data since `smp-ee-files` overwrites in place)
- The EE collection name

**Do not reuse or overwrite an existing version prefix.** Old versions remain intact in `akveg-data` and EE.

When starting a new version, create versioned copies of the relevant scripts rather than modifying the old ones:
- `cog_conversion/startup_all_years_cog_{version}.sh`
- `ee_registration/register_full_collection_{version}.py`
- `qa_utils/compare_ee_gcs_{version}.py`

Current versions in repo: `v20260414` (original, source: `30m_land_sent/`), `v20260430` (multiscale model output, source: `30m_land_sent_multiscale/`, adds 2024).

## Workflow Order

Before starting a new ingest, create the EE collection manually:
```bash
earthengine create collection projects/fisl-tundra-fire/assets/potter_fire_v20260430
```

Then:
1. Deploy `cog_conversion/startup_all_years_cog_{version}.sh` as a GCP e2-highcpu-32 VM startup script — it archives raw TIFFs into the versioned prefix, converts to COGs, then self-deletes the VM
2. Register COGs to EE: `conda run -n ee python3 ee_registration/register_full_collection_{version}.py`
3. Audit: `conda run -n ee python3 qa_utils/compare_ee_gcs_{version}.py`
4. Fix gaps: hardcode missing tiles in `ee_registration/register_missing.py` and re-run

Quick tests (10 tiles, safe to run locally):
```bash
bash tests/test_conversion_10.sh
~/miniconda3/bin/conda run -n ee python3 tests/test_registration_10.py
```

## Architecture

**cog_conversion/** — GDAL conversion startup scripts. Step 1 within each script does a `gsutil rsync` to archive the raw source into the versioned prefix in `akveg-data` (this is how version history is preserved). Step 2 converts archived TIFs to COGs in parallel (32 processes). Scripts self-delete the VM on completion.

**ee_registration/** — EE asset ingestion. `register_full_collection_{version}.py` uses `ThreadPoolExecutor(max_workers=5)` with exponential backoff (`2^attempt + random()`, max 5 retries) for HTTP 429 rate limits. All scripts skip already-registered assets (idempotent). `register_missing.py` is for manually hardcoded stragglers after audit.

**qa_utils/** — Auditing. `compare_ee_gcs_{version}.py` diffs EE collection vs. GCS COG bucket. `compare_raw_versions.py` compares two raw GCS inventories by year/tile. `delete_collection.py` destroys an EE collection and all children — use only to start over on a specific version.

**tests/** — 10-tile subsets for validating conversion and registration without full processing.

## Asset Metadata Convention

Each EE image asset carries: `year` (int), `tile_id` (string), `source_uri` (GCS path). Time range spans the full calendar year (UTC midnight Jan 1 → Jan 1 of next year).
