// viz_potter_fire_versions.js
// GEE visualization script for comparing Potter CNN burned area probability versions.
// Collections:
//   v20260211 — original baseline
//   v20260414 — previous ingest (wopgams)
//   v20260430 — multiscale model, adds 2024, improves 2018/2024 coverage (partial pending)

var screenTool = require('users/mmacander/hls:hls_quick_fire_screen_module.js');

// --- AOI / fire screening examples (uncomment one) ---

// 2015 SW AK fire
var aoi = screenTool.screenFires({
  targetYear: 2015,
  startDoy: 152,
  endDoy: 273,
  aoi: {
    point: ee.Geometry.Point([-162.8651, 61.2794]),
    radiusKm: 20
  }
});

// View extent
// screenTool.screenFires({
//   targetYear: 2015,
//   startDoy: 152,
//   endDoy: 273,
//   aoi: Map.getBounds(true)
// });

// Point + radius
// screenTool.screenFires({
//   targetYear: 2018,
//   startDoy: 182,
//   endDoy: 232,
//   aoi: { point: ee.Geometry.Point([-161.86186, 61.28738]), radiusKm: 5 }
// });

// Force L4/5/7 for modern year
// screenTool.screenFires({
//   targetYear: 2018,
//   aoi: Map.getBounds(true),
//   useL457: true
// });


var PROB_THRESHOLD = 50;  // probability cutoff for binary layers and MRFY (0–100)

// ============================================================
// Helper: build Most Recent Fire Year image from a collection
// ============================================================
function makeMRFY(ic) {
  return ic.map(function(img) {
    var year = ee.Number(img.get('year'));
    return img.addBands(
      ee.Image.constant(year).uint16().rename('year')
        .updateMask(img.select('Probability').gte(PROB_THRESHOLD))
    );
  }).select('year').max();
}

var mrfyVis   = {min: 2000, max: 2024, palette: ['yellow', 'orange', 'red']};
var probVis   = {min: 0, max: 100, palette: ['green', 'yellow', 'red']};


// ============================================================
// v20260211 — original baseline  (band name: B0)
// ============================================================
var ic_v20260211 = ee.ImageCollection('projects/fisl-tundra-fire/assets/potter_fire_v20260211');
var max_v20260211 = ic_v20260211.max();
Map.addLayer(max_v20260211.select('B0').selfMask(),
             probVis, 'v20260211 prob', false);
Map.addLayer(max_v20260211.select('B0').gte(PROB_THRESHOLD).selfMask(),
             {min:0, max:1, palette: 'yellow', opacity: 0.5}, 'v20260211 binary50 (yellow)', false);


// ============================================================
// v20260414 — previous ingest (wopgams)
// ============================================================
var ic_v20260414 = ee.ImageCollection('projects/fisl-tundra-fire/assets/potter_fire_v20260414');
var max_v20260414 = ic_v20260414.max();
Map.addLayer(max_v20260414.select('Probability').selfMask(),
             probVis, 'v20260414 prob', false);
Map.addLayer(max_v20260414.select('Burn_Mask').selfMask(),
             {min:0, max:1, palette: 'blue', opacity: 0.5}, 'v20260414 Burn_Mask (blue)', false);
Map.addLayer(max_v20260414.select('Probability').gte(PROB_THRESHOLD).selfMask(),
             {min:0, max:1, palette: 'blue', opacity: 0.5}, 'v20260414 binary50 (blue)', false);
Map.addLayer(makeMRFY(ic_v20260414),
             mrfyVis, 'v20260414 MRFY', false);


// ============================================================
// v20260430 — multiscale model (current best)
// ============================================================
var ic_v20260430 = ee.ImageCollection('projects/fisl-tundra-fire/assets/potter_fire_v20260430');
var max_v20260430 = ic_v20260430.max();
Map.addLayer(max_v20260430.select('Probability').selfMask(),
             probVis, 'v20260430 prob');
Map.addLayer(max_v20260430.select('Burn_Mask').selfMask(),
             {min:0, max:1, palette: 'red', opacity: 0.5}, 'v20260430 Burn_Mask (red)');
Map.addLayer(max_v20260430.select('Probability').gte(PROB_THRESHOLD).selfMask(),
             {min:0, max:1, palette: 'red', opacity: 0.5}, 'v20260430 binary50 (red)', false);
Map.addLayer(makeMRFY(ic_v20260430),
             mrfyVis, 'v20260430 MRFY (multiscale)');


// ============================================================
// Reference MRFY layers
// ============================================================
var mrfy_ref = ee.Image('projects/akveg-map/assets/disturbance/mrfy_akcan_above_1917_2024p_30m_3338_v20240912');
Map.addLayer(mrfy_ref.updateMask(mrfy_ref.gte(2000)),
             mrfyVis, 'ref MRFY from 2000', false);
Map.addLayer(mrfy_ref.updateMask(mrfy_ref.gte(2000)),
             {min: 1940, max: 2020}, 'ref MRFY all', false);
