# compare_ee_gcs_v20260430.py
import ee
from google.cloud import storage

EE_PROJECT = 'akveg-map'
GCS_BUCKET = 'akveg-data'
GCS_PREFIX = 'disturbance/potter_cnn/v20260430/'
EE_COLLECTION = 'projects/fisl-tundra-fire/assets/potter_fire_v20260430'

try:
    ee.Initialize(project=EE_PROJECT)
except Exception:
    ee.Authenticate()
    ee.Initialize(project=EE_PROJECT)

def get_ee_assets():
    print(f"Listing assets in EE collection: {EE_COLLECTION}...")
    assets = []
    try:
        # Use listAssets to get all children
        parent_assets = ee.data.listAssets({'parent': EE_COLLECTION})['assets']
        for asset in parent_assets:
            # name is projects/fisl-tundra-fire/assets/potter_fire_v20260430/y2001_t0
            asset_id = asset['name'].split('/')[-1]
            assets.append(asset_id)
    except Exception as e:
        print(f"Error listing EE assets: {e}")
    return set(assets)

def get_gcs_tifs():
    print(f"Listing TIFs in GCS: gs://{GCS_BUCKET}/{GCS_PREFIX}...")
    storage_client = storage.Client(project=EE_PROJECT)
    bucket = storage_client.bucket(GCS_BUCKET)
    blobs = bucket.list_blobs(prefix=GCS_PREFIX)
    
    tifs = {}
    for blob in blobs:
        if 'smp-ee-files' in blob.name or 'logs/' in blob.name or not blob.name.endswith('.tif'):
            continue
            
        parts = blob.name.split('/')
        filename = parts[-1]
        year_str = parts[-2]
        
        if year_str.isdigit():
            tile_id = filename.replace('.tif', '')
            asset_name = f"y{year_str}_t{tile_id}"
            tifs[asset_name] = f"gs://{GCS_BUCKET}/{blob.name}"
            
    return tifs

def main():
    ee_set = get_ee_assets()
    gcs_map = get_gcs_tifs()
    
    gcs_set = set(gcs_map.keys())
    
    missing_in_ee = gcs_set - ee_set
    extra_in_ee = ee_set - gcs_set
    
    print(f"\nResults:")
    print(f"EE Assets: {len(ee_set)}")
    print(f"GCS COGs:  {len(gcs_set)}")
    print(f"Missing from EE: {len(missing_in_ee)}")
    print(f"Extra in EE:     {len(extra_in_ee)}")
    
    if missing_in_ee:
        print("\nFirst 20 missing assets:")
        for name in sorted(list(missing_in_ee))[:20]:
            print(f"  {name} ({gcs_map[name]})")

if __name__ == "__main__":
    main()
