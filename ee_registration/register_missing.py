# register_missing.py
import ee
import json
from google.auth.transport.requests import AuthorizedSession
from datetime import datetime, timezone

EE_PROJECT = 'akveg-map'
EE_COLLECTION = 'projects/fisl-tundra-fire/assets/potter_fire_v20260414'

missing = [
    ("y2006_t440", "gs://akveg-data/disturbance/potter_cnn/v20260414/2006/440.tif"),
    ("y2006_t528", "gs://akveg-data/disturbance/potter_cnn/v20260414/2006/528.tif"),
    ("y2008_t509", "gs://akveg-data/disturbance/potter_cnn/v20260414/2008/509.tif"),
    ("y2013_t49", "gs://akveg-data/disturbance/potter_cnn/v20260414/2013/49.tif"),
]

try:
    ee.Initialize(project=EE_PROJECT)
except Exception:
    ee.Authenticate()
    ee.Initialize(project=EE_PROJECT)

session = AuthorizedSession(ee.data.get_persistent_credentials().with_quota_project(EE_PROJECT))

for asset_name, cog_uri in missing:
    year = int(asset_name.split('_')[0][1:])
    tile_id = asset_name.split('_')[1][1:]
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
    
    print(f"Registering {asset_name}...")
    response = session.post(url=url, data=json.dumps(request))
    if response.status_code == 200:
        print(f"  -> Success.")
    else:
        print(f"  -> Error {response.status_code}: {response.text}")
