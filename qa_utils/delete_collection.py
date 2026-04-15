# delete_collection.py
import ee
import time

EE_PROJECT = 'akveg-map'
EE_COLLECTION = 'projects/fisl-tundra-fire/assets/potter_fire_v20260414'

try:
    ee.Initialize(project=EE_PROJECT)
except Exception:
    ee.Authenticate()
    ee.Initialize(project=EE_PROJECT)

def delete_collection(collection_id):
    try:
        # Check if collection exists
        print(f"Checking collection: {collection_id}")
        assets = ee.data.listAssets({'parent': collection_id})['assets']
        
        if not assets:
            print("Collection is already empty.")
        else:
            print(f"Found {len(assets)} assets to delete.")
            for asset in assets:
                asset_id = asset['name']
                print(f"Deleting child: {asset_id}")
                try:
                    ee.data.deleteAsset(asset_id)
                except Exception as e:
                    print(f"  -> Failed to delete {asset_id}: {e}")
        
        print(f"Deleting parent collection: {collection_id}")
        ee.data.deleteAsset(collection_id)
        print("Success.")
        
    except ee.EEException as e:
        if 'not found' in str(e).lower():
            print("Collection does not exist.")
        else:
            print(f"Error: {e}")

if __name__ == "__main__":
    delete_collection(EE_COLLECTION)
