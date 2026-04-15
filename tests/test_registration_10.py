# test_registration_10.py
import ee
import os
import json
from google.cloud import storage
from google.auth.transport.requests import AuthorizedSession
from datetime import datetime, timezone

EE_PROJECT = 'akveg-map'
GCS_BUCKET = 'akveg-data'
GCS_PREFIX = 'disturbance/potter_cnn/v20260414/'
EE_COLLECTION = 'projects/fisl-tundra-fire/assets/potter_fire_v20260414_test'

try:
    ee.Initialize(project=EE_PROJECT)
except Exception:
    ee.Authenticate()
    ee.Initialize(project=EE_PROJECT)

session = AuthorizedSession(ee.data.get_persistent_credentials().with_quota_project(EE_PROJECT))

def create_collection_if_not_exists(collection_id):
    try:
        ee.data.getAsset(collection_id)
        print(f"Collection {collection_id} already exists.")
    except ee.EEException:
        print(f"Creating collection {collection_id}...")
        ee.data.createAsset({'type': 'IMAGE_COLLECTION'}, collection_id)

def register_cog(cog_uri, collection_path):
    parts = cog_uri.split('/')
    filename = parts[-1]
    year_str = parts[-2]
    
    tile_id = filename.replace('.tif', '')
    year = int(year_str)
    
    asset_name = f"y{year}_t{tile_id}"
    asset_id = f"{collection_path}/{asset_name}"
    
    dt_start = datetime(year, 1, 1, tzinfo=timezone.utc)
    dt_end = datetime(year + 1, 1, 1, tzinfo=timezone.utc)
    
    properties = {
        'year': year,
        'tile_id': tile_id,
        'source_uri': cog_uri
    }

    request = {
        'type': 'IMAGE',
        'gcs_location': {'uris': [cog_uri]},
        'properties': properties,
        'startTime': dt_start.isoformat(),
        'endTime': dt_end.isoformat()
    }

    project_part = asset_id.split('/assets/')[0]
    prefix = f"{project_part}/assets/"
    relative_asset_id = asset_id[len(prefix):]
    url = f'https://earthengine.googleapis.com/v1alpha/{project_part}/assets?assetId={relative_asset_id}'
    
    print(f"Registering {asset_name}...")
    response = session.post(url=url, data=json.dumps(request))
    if response.status_code == 200:
        print(f"  -> Success.")
    elif response.status_code == 409:
        print(f"  -> Already exists.")
    else:
        print(f"  -> Error {response.status_code}: {response.text}")

def main():
    create_collection_if_not_exists(EE_COLLECTION)
    
    # List the files we just uploaded
    storage_client = storage.Client(project=EE_PROJECT)
    bucket = storage_client.bucket(GCS_BUCKET)
    blobs = bucket.list_blobs(prefix=GCS_PREFIX + "2001/")
    
    count = 0
    for blob in blobs:
        if blob.name.endswith('.tif'):
            register_cog(f"gs://{GCS_BUCKET}/{blob.name}", EE_COLLECTION)
            count += 1
            if count >= 10:
                break

if __name__ == "__main__":
    main()
