# register_2001_fast.py
import ee
import json
from google.cloud import storage
from google.auth.transport.requests import AuthorizedSession
from datetime import datetime, timezone

# CONFIG
EE_PROJECT = 'akveg-map'
GCS_BUCKET = 'akveg-data'
GCS_PREFIX = 'disturbance/potter_cnn/v20260414/2001/'
EE_COLLECTION = 'projects/fisl-tundra-fire/assets/potter_fire_v20260414'

# SETUP
try:
    ee.Initialize(project=EE_PROJECT)
except Exception:
    ee.Authenticate()
    ee.Initialize(project=EE_PROJECT)

session = AuthorizedSession(ee.data.get_persistent_credentials().with_quota_project(EE_PROJECT))

def create_collection():
    try:
        ee.data.createAsset({'type': 'IMAGE_COLLECTION'}, EE_COLLECTION)
        print(f"Created collection: {EE_COLLECTION}")
    except ee.EEException as e:
        if 'already exists' in str(e).lower():
            print(f"Collection {EE_COLLECTION} exists.")
        else:
            raise

def register_cogs():
    storage_client = storage.Client(project=EE_PROJECT)
    bucket = storage_client.bucket(GCS_BUCKET)
    blobs = bucket.list_blobs(prefix=GCS_PREFIX)
    
    print(f"Listing COGs in gs://{GCS_BUCKET}/{GCS_PREFIX}...")
    
    count = 0
    for blob in blobs:
        if not blob.name.endswith('.tif'):
            continue
            
        cog_uri = f"gs://{GCS_BUCKET}/{blob.name}"
        parts = blob.name.split('/')
        filename = parts[-1]
        year = 2001 # We are targeting the 2001 prefix
        tile_id = filename.replace('.tif', '')
        
        asset_id = f"{EE_COLLECTION}/y{year}_t{tile_id}"
        
        dt_start = datetime(year, 1, 1, tzinfo=timezone.utc)
        dt_end = datetime(year + 1, 1, 1, tzinfo=timezone.utc)
        
        request = {
            'type': 'IMAGE',
            'gcs_location': {'uris': [cog_uri]},
            'properties': {
                'year': year,
                'tile_id': tile_id,
                'source_uri': cog_uri
            },
            'startTime': dt_start.isoformat(),
            'endTime': dt_end.isoformat()
        }

        # Construct V1 Alpha URL
        project_part = EE_COLLECTION.split('/assets/')[0]
        relative_asset_id = asset_id.split('/assets/')[1]
        url = f'https://earthengine.googleapis.com/v1alpha/{project_part}/assets?assetId={relative_asset_id}'
        
        print(f"[{count+1}] Registering {year}_{tile_id}...")
        response = session.post(url=url, data=json.dumps(request))
        
        if response.status_code != 200:
            print(f"  -> Error {response.status_code}: {response.text}")
        
        count += 1

    print(f"Finished. Registered {count} assets.")

if __name__ == "__main__":
    create_collection()
    register_cogs()
