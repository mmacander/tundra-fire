# compare_raw_versions.py
#
# Inventories two raw GCS datasets and reports completeness differences.
# Run this before committing to a new COG conversion + EE ingest cycle.
#
# Usage:
#   conda run -n ee python3 qa_utils/compare_raw_versions.py

from google.cloud import storage
from collections import defaultdict

GCS_PROJECT   = 'akveg-map'

# Old dataset (v20260414 source)
OLD_BUCKET = 'smp-ee-files'
OLD_PREFIX = '30m_land_sent/'

# New dataset (v20260430 — multiscale model output)
NEW_BUCKET = 'smp-ee-files'
NEW_PREFIX = '30m_land_sent_multiscale/'

# -----------------------------------------------------------------------

def list_tifs(bucket_name, prefix, label):
    """Returns {year: set(tile_ids)} for all .tif files under prefix."""
    client = storage.Client(project=GCS_PROJECT)
    bucket = client.bucket(bucket_name)
    blobs = bucket.list_blobs(prefix=prefix)

    by_year = defaultdict(set)
    total = 0
    for blob in blobs:
        if not blob.name.endswith('.tif'):
            continue
        parts = blob.name.split('/')
        if len(parts) < 2:
            continue
        year_str = parts[-2]
        tile_id  = parts[-1].replace('.tif', '')
        if year_str.isdigit():
            by_year[year_str].add(tile_id)
            total += 1

    print(f"[{label}] gs://{bucket_name}/{prefix}")
    print(f"  {total} TIFs across {len(by_year)} years: {sorted(by_year)}")
    return by_year, total


def compare(old, new):
    all_years = sorted(set(old) | set(new))

    print("\n--- Per-year tile counts ---")
    print(f"{'Year':>6}  {'Old':>6}  {'New':>6}  {'Diff':>6}  {'Missing (old→new)':>22}  Extra (new only)")
    print("-" * 90)

    total_missing = 0
    total_extra   = 0

    for year in all_years:
        old_tiles = old.get(year, set())
        new_tiles = new.get(year, set())
        missing = old_tiles - new_tiles   # in old but not in new
        extra   = new_tiles - old_tiles   # in new but not in old
        diff    = len(new_tiles) - len(old_tiles)
        diff_str = f"{diff:+d}" if diff else "  0"
        total_missing += len(missing)
        total_extra   += len(extra)
        print(f"{year:>6}  {len(old_tiles):>6}  {len(new_tiles):>6}  {diff_str:>6}  {len(missing):>22}  {len(extra)}")

    print("-" * 90)
    print(f"{'TOTAL':>6}  {sum(len(v) for v in old.values()):>6}  {sum(len(v) for v in new.values()):>6}"
          f"            {total_missing:>22}  {total_extra}")

    # Detail for missing tiles
    if total_missing:
        print(f"\n--- Tiles present in OLD but missing from NEW ({total_missing} total) ---")
        for year in all_years:
            missing = old.get(year, set()) - new.get(year, set())
            if missing:
                print(f"  {year}: {sorted(missing)}")

    # Detail for extra tiles
    if total_extra:
        print(f"\n--- Tiles present in NEW but not in OLD ({total_extra} total) ---")
        for year in all_years:
            extra = new.get(year, set()) - old.get(year, set())
            if extra:
                print(f"  {year}: {sorted(extra)}")

    if total_missing == 0 and total_extra == 0:
        print("\nTile inventories match exactly.")
    else:
        print(f"\nSummary: {total_missing} tiles missing from new dataset, {total_extra} new tiles not in old.")


def main():
    print("=== Raw dataset completeness comparison ===\n")
    old, _ = list_tifs(OLD_BUCKET, OLD_PREFIX, "OLD")
    print()
    new, _ = list_tifs(NEW_BUCKET, NEW_PREFIX, "NEW")
    compare(old, new)


if __name__ == "__main__":
    main()
