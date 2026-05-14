#!/home/mmacander/miniconda3/envs/ee/bin/python3
"""
pft_timeseries.py — Extract annual PFT cover percentiles within fire scars,
stratified by pre-fire land cover, across PFT years 1985–2020.

Ports and optimizes fire_x_pft/pft_timeseries_ko.ipynb:
  - Collapses 36-year inner PFT loop into ONE 432-band reduceRegion per fire
    year (~36x fewer pixel reads vs. original 36-call design)
  - Precomputes fire IC, LC stack, and PFT mega-stack once; reused per fire year
  - Applies per-band fire-history masks (same logic as original, vectorized)
  - Adds tileScale and realistic maxPixels cap
  - Submits all export tasks asynchronously; logs task IDs

Usage:
    ~/miniconda3/bin/conda run -n ee python3 fire_x_pft/pft_timeseries.py [options]

    --fire-years  Comma-separated years (e.g. "1988,1989") or "all" (default)
    --version     Output version tag (default v20260513)
    --tile-scale  EE tileScale for reduceRegion (default 4; raise to 8/16 if OOM)
    --no-reburn   Skip prev/next-fire masking (larger N, but reburn-contaminated
                  trajectories). Output filenames get a "_noreburn" suffix.
    --dry-run     Build and describe tasks without calling task.start()
"""

import argparse
import json
import logging
import os
import sys
import ee

# ─── CONFIG ──────────────────────────────────────────────────────────────────

EE_PROJECT     = 'fisl-tundra-fire'
VERSION        = 'v20260513'
DRIVE_FOLDER   = 'pft_trajectories'
SCALE          = 30
TILE_SCALE     = 4
MAX_PIXELS     = 3e11   # ROI has ~251B pixels at 30m; 3e11 gives headroom
FIRE_START_YR  = 1940
FIRE_END_YR    = 2025

PFT_YEARS = list(range(1985, 2021))          # 36 years
PFT_NAMES = [                                # 12 PFT types (order matters for index arithmetic)
    'cTree', 'bTree', 'allDecShrub', 'decshrabs', 'alnshr', 'betshr',
    'salshr', 'allEvShrub', 'graminoid', 'allForb', 'tmlichenLight2', 'talshr',
]
PERCENTILE_LABELS = ['p2', 'p3', 'p50', 'p97', 'p98']

N_PFT_NAMES = len(PFT_NAMES)                # 12
N_PFT_YEARS = len(PFT_YEARS)                # 36
N_BANDS     = N_PFT_NAMES * N_PFT_YEARS     # 432

LOG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'logs')

# ─── INIT ─────────────────────────────────────────────────────────────────────

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
log = logging.getLogger(__name__)

try:
    ee.Initialize(project=EE_PROJECT)
except Exception:
    ee.Authenticate()
    ee.Initialize(project=EE_PROJECT)

# ─── ASSET LOADERS (called once at startup) ───────────────────────────────────

def load_roi():
    return ee.FeatureCollection('projects/fisl-tundra-fire/assets/rois/above_arctic_simple')

def load_roi_mask():
    return ee.Image(
        'projects/foreststructure/ABoVE/CCDC/'
        'CCDC_ABoVE_L4578SR_1984_2020_J091_273_v20201203_mappedArea_na_beringia_westCan'
    )

def load_fire_ic():
    """
    Merge historic (akca) and modern (Potter v20260430) fire ICs.
    Returns (fires_ic, fire_years_all) where fire_years_all is a sorted Python list
    of all years present in the merged IC.
    """
    fires_historic = ee.ImageCollection(
        'projects/fisl-tundra-fire/assets/fires_raster/akca_fires_30m_3338_arctic'
    )
    fires_modern_raw = ee.ImageCollection(
        'projects/fisl-tundra-fire/assets/potter_fire_v20260430_ingested'
    )

    # Tidy historic: parse year from string property; keep pre-2001 and 2025
    fires_historic = fires_historic.map(
        lambda img: img.set('year', ee.Number.parse(img.get('year')))
    ).filter(ee.Filter.Or(
        ee.Filter.lt('year', 2001),
        ee.Filter.eq('year', 2025)
    ))

    # Tidy modern: collapse multi-image years to single max Burn_Mask, encode year as pixel value
    fires_modern_raw = fires_modern_raw.select('Burn_Mask')
    fires_modern_years = fires_modern_raw.aggregate_array('year').distinct()

    def process_modern_year(yr):
        coll = fires_modern_raw.filter(ee.Filter.eq('year', yr))
        return (coll.max()
                .selfMask()
                .multiply(ee.Image.constant(yr))
                .uint16()
                .copyProperties(coll.first()))

    fires_modern = ee.ImageCollection(fires_modern_years.map(process_modern_year))
    fires_all = fires_historic.merge(fires_modern)

    fire_years_all = fires_all.aggregate_array('year').distinct().sort().getInfo()

    def add_date_info(yr):
        img = fires_all.filter(ee.Filter.eq('year', yr)).first()
        next_yr = ee.Number(yr).add(1)
        return img.set({
            'system:time_start': ee.Date.fromYMD(yr, 1, 1).millis(),
            'system:time_end':   ee.Date.fromYMD(next_yr, 1, 1).millis(),
        }).rename('fire_year')

    fires = ee.ImageCollection(ee.List(fire_years_all).map(add_date_info))
    return fires, fire_years_all

def load_lc_stack():
    """
    Build single multi-band LC image with bands y1972..y2020.
    Three sources stitched together:
      1972–1984: MSS CCDC experimental (Macander)
      1985–2014: Wang et al. ABoVE LandCover v01
      2015–2020: CCDC BiomeShift
    """
    lc_1972_1984 = (
        ee.ImageCollection('projects/foreststructure/Alaska/MSS/above_lc_mss_v20220619_tests')
        .filter(ee.Filter.calendarRange(1972, 1984, 'year'))
        .toBands()
        .regexpRename(
            '_bootstrap_20220619_mss_ccdc_1985_1986_n5000_2000_500_seed6_rf100_ml2_above_lc_co', ''
        )
        .regexpRename('above_lc_', 'y')
    )
    lc_1985_2014 = ee.Image('projects/foreststructure/ABoVE/ORNL_DAAC/ABoVE_LandCover_v01')
    lc_2015_2020 = (
        ee.ImageCollection('projects/foreststructure/ABoVE/BiomeShift/ABoVE_LC_2020')
        .select('y2015', 'y2016', 'y2017', 'y2018', 'y2019', 'y2020')
        .mosaic()
    )
    return lc_1972_1984.addBands(lc_1985_2014).addBands(lc_2015_2020)

def load_pft_stack():
    """
    Build 432-band PFT image (36 years × 12 PFTs) named y{yr}_{name}.
    No fire-history masking here — that is applied per fire year in
    apply_fire_history_masks(). Only the within-year data-validity mask is kept.
    """
    pft_ic = ee.ImageCollection(
        'projects/foreststructure/ABoVE/BiomeShift/Alaska_Yukon_PFT_202207_Filled'
    )
    result = None
    for yr in PFT_YEARS:
        yr_coll = pft_ic.filter(ee.Filter.calendarRange(yr, yr, 'year')).select('cover')
        yr_bands = None
        for name in PFT_NAMES:
            band = (yr_coll
                    .filterMetadata('response', 'equals', name)
                    .first()
                    .rename(f'y{yr}_{name}'))
            yr_bands = band if yr_bands is None else yr_bands.addBands(band)
        yr_bands = yr_bands.clamp(0, 100)
        # Mask to pixels valid in all PFT bands for this year
        yr_bands = yr_bands.updateMask(yr_bands.mask().reduce(ee.Reducer.min()))
        result = yr_bands if result is None else result.addBands(yr_bands)
    return result

# ─── PER-FIRE-YEAR HELPERS ────────────────────────────────────────────────────

def build_prev_next_mosaics(fires_ic, fire_year):
    """
    Per-pixel 'most recent previous fire year' and 'closest next fire year'
    images, used to build fire-history masks that exclude reburned pixels.
    Unburned pixels get sentinel values (1900 / 2030).
    """
    if fire_year != FIRE_START_YR:
        prev_img = (fires_ic
                    .filter(ee.Filter.calendarRange(1900, fire_year - 1, 'year'))
                    .max()
                    .unmask(1900)
                    .rename('year'))
    else:
        prev_img = ee.Image(1900).rename('year')

    if fire_year != FIRE_END_YR:
        next_img = (fires_ic
                    .filter(ee.Filter.calendarRange(fire_year + 1, 2030, 'year'))
                    .min()
                    .unmask(2030)
                    .rename('year'))
    else:
        next_img = ee.Image(2030).rename('year')

    return prev_img, next_img

def apply_fire_history_masks(pft_stack, prevfire_img, nextfire_img):
    """
    Apply per-band fire-history masks to the 432-band PFT mega-stack.
    Band y{yr}_{name} is masked at pixels where:
        pft_year <= prevfire_year  (burned again before pft observation)
        pft_year >= nextfire_year  (burned again after pft observation)
    This preserves clean pre→post-fire recovery trajectories.
    Equivalent to the per-iteration fire_history_mask in the original notebook,
    but computed once for all 36 years rather than 36 times separately.
    """
    result = None
    for yr in PFT_YEARS:
        fh_mask = (ee.Image.constant(yr).gt(prevfire_img)
                   .And(ee.Image.constant(yr).lt(nextfire_img)))
        yr_bands = (pft_stack
                    .select([f'y{yr}_{n}' for n in PFT_NAMES])
                    .updateMask(fh_mask))
        result = yr_bands if result is None else result.addBands(yr_bands)
    return result

def get_prefire_lc(lc_stack, fire_year):
    """
    Pre-fire land cover = LC one year before the fire.
    Multiplied by 10 so class codes don't collide with the nodata sentinel (0).
    Out-of-range years (before 1972 or after 2020) return a constant 0 image.
    """
    prefire_year = fire_year - 1
    if prefire_year < 1972 or prefire_year > 2020:
        return ee.Image(0).rename('lc')
    return (lc_stack
            .select(f'y{prefire_year}')
            .unmask(0)
            .multiply(10)
            .rename('lc'))

# ─── REDUCTION ────────────────────────────────────────────────────────────────

def make_flatten_logic(fire_year):
    """
    Returns an EE-mappable function that unpacks one LC-group result dictionary
    (from the grouped 432-band percentile reduceRegion) into a flat list of
    ee.Features with schema:
        land_cover, pft_year, pft_type, percentile, cover_value, fire_year

    Band ordering in the 432-element percentile list:
        index = pft_year_idx * N_PFT_NAMES + pft_name_idx
    where pft_year_idx indexes into PFT_YEARS (0=1985) and
          pft_name_idx indexes into PFT_NAMES (0=cTree).
    """
    pft_years_ee       = ee.List(PFT_YEARS)
    pft_names_ee       = ee.List(PFT_NAMES)
    percentile_labels_ee = ee.List(PERCENTILE_LABELS)
    n_pft_names        = N_PFT_NAMES   # Python int baked into expression
    n_bands            = N_BANDS       # Python int baked into expression

    def flatten_logic(group_obj):
        group_obj = ee.Dictionary(group_obj)
        lc_code   = group_obj.get('group')
        indices   = ee.List.sequence(0, n_bands - 1)

        def map_idx(idx):
            idx     = ee.Number(idx)
            yr_idx  = idx.divide(n_pft_names).floor().toInt()
            pft_idx = idx.mod(n_pft_names).toInt()
            yr      = pft_years_ee.get(yr_idx)
            name    = pft_names_ee.get(pft_idx)

            def map_pct(p_label):
                val = ee.List(group_obj.get(p_label)).get(idx)
                return ee.Feature(None, {
                    'land_cover':  lc_code,
                    'pft_year':    yr,
                    'pft_type':    name,
                    'percentile':  p_label,
                    'cover_value': val,
                    'fire_year':   fire_year,   # Python int, baked in
                })
            return percentile_labels_ee.map(map_pct)

        return indices.map(map_idx).flatten()

    return flatten_logic


def build_fire_year_fc(fire_year, fires_ic, roi, roi_mask, lc_stack, pft_stack,
                       no_reburn=False):
    """
    Build the ee.FeatureCollection for one fire year (NOT evaluated yet).
    One grouped 432-band percentile reduceRegion replaces the original 36-call
    inner loop, cutting pixel reads by ~36x.

    no_reburn=True skips the prev/next-fire masking; pixels that reburned in
    another year still contribute to the trajectory (larger N, but contaminated).
    """
    fire_year_img = (fires_ic
                     .filter(ee.Filter.calendarRange(fire_year, fire_year, 'year'))
                     .first())

    prefire_lc = get_prefire_lc(lc_stack, fire_year)
    if no_reburn:
        masked_pft = pft_stack
    else:
        prev_img, next_img = build_prev_next_mosaics(fires_ic, fire_year)
        masked_pft         = apply_fire_history_masks(pft_stack, prev_img, next_img)

    # Band 0 = prefire_lc (grouping key); bands 1..432 = masked PFT values
    stack = (prefire_lc
             .addBands(masked_pft)
             .updateMask(fire_year_img)   # restrict to this year's fire scar
             .updateMask(roi_mask))

    reducer = (ee.Reducer.percentile([2, 3, 50, 97, 98])
               .unweighted()
               .repeat(N_BANDS)
               .group(0))

    crosstab = stack.reduceRegion(
        reducer=reducer,
        geometry=roi.geometry(),
        scale=SCALE,
        tileScale=TILE_SCALE,
        maxPixels=MAX_PIXELS,
    )

    groups = ee.List(crosstab.get('groups'))
    return ee.FeatureCollection(groups.map(make_flatten_logic(fire_year)).flatten())

# ─── MAIN ─────────────────────────────────────────────────────────────────────

def parse_args():
    p = argparse.ArgumentParser(
        description='Extract PFT time-series within annual fire scars.',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    p.add_argument('--fire-years', default='all',
                   help='Comma-separated fire years or "all" (default: all)')
    p.add_argument('--version', default=VERSION,
                   help=f'Output version tag (default: {VERSION})')
    p.add_argument('--tile-scale', type=int, default=TILE_SCALE,
                   help=f'EE tileScale (default: {TILE_SCALE}; raise to 8/16 if OOM)')
    p.add_argument('--no-reburn', action='store_true',
                   help='Skip reburn masking (larger N, contaminated trajectories); '
                        'adds "_noreburn" suffix to output filenames')
    p.add_argument('--dry-run', action='store_true',
                   help='Describe tasks without starting them')
    return p.parse_args()


def main():
    args = parse_args()
    global TILE_SCALE
    TILE_SCALE = args.tile_scale

    log.info('Loading EE assets (fire IC, LC stack, PFT mega-stack)...')
    fires_ic, fire_years_all = load_fire_ic()
    roi      = load_roi()
    roi_mask = load_roi_mask()
    lc_stack = load_lc_stack()
    pft_stack = load_pft_stack()
    log.info('Asset expressions built (%d fire years in IC, %d PFT bands in stack)',
             len(fire_years_all), N_BANDS)

    # Determine target fire years
    valid_years = sorted(set(fire_years_all) & set(range(FIRE_START_YR, FIRE_END_YR + 1)))
    if args.fire_years == 'all':
        target_years = valid_years
    else:
        requested = [int(y.strip()) for y in args.fire_years.split(',')]
        missing = sorted(set(requested) - set(valid_years))
        if missing:
            log.warning('Requested years not found in fire IC: %s', missing)
        target_years = sorted(set(requested) & set(valid_years))

    if not target_years:
        log.error('No valid fire years to process. Exiting.')
        sys.exit(1)
    reburn_suffix = '_noreburn' if args.no_reburn else ''
    log.info('Reburn masking: %s', 'disabled' if args.no_reburn else 'enabled')
    log.info('Processing %d fire year(s): %s%s',
             len(target_years),
             target_years[:8],
             ' ...' if len(target_years) > 8 else '')

    os.makedirs(LOG_DIR, exist_ok=True)
    task_log_path = os.path.join(LOG_DIR, f'{args.version}{reburn_suffix}_tasks.json')
    tasks = {}

    for fire_year in target_years:
        log.info('  fire_year=%d: building FC expression...', fire_year)
        fc = build_fire_year_fc(fire_year, fires_ic, roi, roi_mask, lc_stack, pft_stack,
                                no_reburn=args.no_reburn)
        desc = f'lc_pft_fire{fire_year}_{args.version}{reburn_suffix}'
        task = ee.batch.Export.table.toDrive(
            collection=fc,
            description=desc,
            folder=DRIVE_FOLDER,
            fileFormat='CSV',
        )
        if args.dry_run:
            log.info('    → DRY RUN: task "%s" not started', desc)
        else:
            task.start()
            tasks[str(fire_year)] = task.id
            log.info('    → started task "%s" (id=%s)', desc, task.id)

    if not args.dry_run:
        if tasks:
            with open(task_log_path, 'w') as f:
                json.dump(tasks, f, indent=2)
            log.info('Task IDs saved to %s', task_log_path)
        log.info('Submitted %d task(s). Monitor: https://code.earthengine.google.com/tasks',
                 len(tasks))
    else:
        log.info('Dry run complete — %d task(s) described, none started', len(target_years))


if __name__ == '__main__':
    main()
