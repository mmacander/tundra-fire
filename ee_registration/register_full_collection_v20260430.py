# register_full_collection_v20260430.py
import ee
import json
import pandas as pd
from google.cloud import storage
from google.auth.transport.requests import AuthorizedSession
from datetime import datetime, timezone
import concurrent.futures

# --- CONFIGURATION ---
EE_PROJECT = 'akveg-map'
GCS_BUCKET = 'akveg-data'
GCS_PREFIX = 'disturbance/potter_cnn/v20260430/'
EE_COLLECTION = 'projects/fisl-tundra-fire/assets/potter_fire_v20260430'

# --- SETUP ---
try:
    ee.Initialize(project=EE_PROJECT)
except Exception:
    ee.Authenticate()
    ee.Initialize(project=EE_PROJECT)

session = AuthorizedSession(ee.data.get_persistent_credentials().with_quota_project(EE_PROJECT))

def get_tif_list():
    """Lists all processed COGs, excluding backup files."""
    print(f"Listing COGs in gs://{GCS_BUCKET}/{GCS_PREFIX}...")
    storage_client = storage.Client(project=EE_PROJECT)
    bucket = storage_client.bucket(GCS_BUCKET)
    blobs = bucket.list_blobs(prefix=GCS_PREFIX)
    
    tif_list = []
    for blob in blobs:
        if 'smp-ee-files' in blob.name or 'logs/' in blob.name or not blob.name.endswith('.tif'):
            continue
        tif_list.append(f"gs://{GCS_BUCKET}/{blob.name}")
    return tif_list

import time
import random

def register_asset(cog_uri):
    # Parse path
    parts = cog_uri.split('/')
    filename = parts[-1]
    year_str = parts[-2]
    
    if not year_str.isdigit():
        return None
        
    year = int(year_str)
    tile_id = filename.replace('.tif', '')
    asset_name = f"y{year}_t{tile_id}"
    asset_id = f"{EE_COLLECTION}/{asset_name}"
    
    dt_start = datetime(year, 1, 1, tzinfo=timezone.utc)
    dt_end = datetime(year + 1, 1, 1, tzinfo=timezone.utc)
    
    request = {
        'type': 'IMAGE',
        'gcs_location': {'uris': [cog_uri]},
        'properties': {'year': year, 'tile_id': tile_id, 'source_uri': cog_uri},
        'startTime': dt_start.isoformat(),
        'endTime': dt_end.isoformat()
    }

    project_part = EE_COLLECTION.split('/assets/')[0]
    relative_asset_id = asset_id.split('/assets/')[1]
    url = f'https://earthengine.googleapis.com/v1alpha/{project_part}/assets?assetId={relative_asset_id}'
    
    max_retries = 5
    for attempt in range(max_retries):
        response = session.post(url=url, data=json.dumps(request))
        
        if response.status_code == 200:
            return (asset_name, 200)
        
        # Earth Engine V1 Alpha often returns 400 for 'already exists' instead of 409
        if response.status_code == 400 and 'cannot overwrite' in response.text.lower():
            return (asset_name, 409) 
            
        if response.status_code == 429:
            # Rate limit backoff
            sleep_time = (2 ** attempt) + random.random()
            time.sleep(sleep_time)
            continue
            
        print(f"  -> Error registering {asset_name}: {response.status_code} - {response.text}")
        return (asset_name, response.status_code)
    
    return (asset_name, 429)

def main():
    tifs = get_tif_list()
    print(f"Found {len(tifs)} total tiles to register.")
    
    count = 0
    success = 0
    exists = 0
    errors = 0
    
    print("Starting batch registration (reduced concurrency with backoff)...")
    # Reducing workers to 5 to be gentler on the API
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        future_to_cog = {executor.submit(register_asset, uri): uri for uri in tifs}
        for future in concurrent.futures.as_completed(future_to_cog):
            res = future.result()
            if res:
                name, code = res
                if code == 200:
                    success += 1
                elif code == 409:
                    exists += 1
                else:
                    errors += 1
                    print(f"  -> Error registering {name}: {code}")
            
            count += 1
            if count % 500 == 0:
                print(f"Progress: {count}/{len(tifs)} (Success: {success}, Already Exists: {exists}, Errors: {errors})")

    print(f"\nFinal Status: {success} newly registered, {exists} already existed, {errors} errors.")

if __name__ == "__main__":
    main()
