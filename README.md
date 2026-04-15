# Wopgams Ingest Workflow

This repository contains the workflow for processing burned area raster data, converting it to Cloud Optimized GeoTIFFs (COGs), and registering the results to a Google Earth Engine (EE) ImageCollection.

The files have been organized by task into the following subfolders:

## 1. `cog_conversion/`
**Goal:** Convert original unoptimized TIFFs stored in Google Cloud Storage (GCS) into Cloud Optimized GeoTIFFs (COGs) and upload them to a destination GCS bucket.
* `convert_to_cog.sh`: Base script that uses GDAL to convert TIFFs into COGs with average resampling and deflate compression.
* `startup_all_years_cog.sh` / `startup_2001_cog.sh`: Startup scripts to run on GCP instances to handle bulk conversions for all years or a single year. These scripts often self-terminate the instance upon completion.

## 2. `ee_registration/`
**Goal:** Scan the GCS bucket for processed COGs and register them as Earth Engine Assets within an ImageCollection.
* `cog_to_ic_burned_area.py`: Standard script to create the `ImageCollection` and register COGs.
* `register_full_collection.py`: An optimized version of the registration script that uses concurrent threads to speed up the ingestion process while managing API rate limits.
* `register_2001_fast.py`: Registration script specific to processing the 2001 data subset quickly.
* `register_missing.py`: Registers specific missing assets manually identified.

## 3. `qa_utils/`
**Goal:** Quality assurance, auditing, and collection management.
* `compare_ee_gcs.py`: Compares what is successfully registered in Earth Engine against what exists in the GCS bucket to identify missing tiles.
* `delete_collection.py`: Utility to delete the ImageCollection and all its assets if you need to start the ingestion over from scratch.

## 4. `tests/`
**Goal:** Testing scripts and older cruft useful for debugging without running the full dataset.
* `test_conversion_10.sh`: Tests the conversion process on a small batch of 10 tiles.
* `test_registration_10.py`: Tests the EE registration process on a small subset of tiles.

---

### Workflow Execution

1. **Convert Data:** Provision a GCP VM and run `cog_conversion/startup_all_years_cog.sh` (or `convert_to_cog.sh` locally/in batch) to get all raw data formatted as COGs in GCS.
2. **Register Assets:** Run `ee_registration/register_full_collection.py` to create the ImageCollection and register all COGs.
3. **Audit Results:** Run `qa_utils/compare_ee_gcs.py` to identify any files that failed to register due to API rate limits or errors.
4. **Fix Missing:** If the audit identifies missing files, update and run `ee_registration/register_missing.py` to resolve them.
