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


// ============================================================
// Helper: build Most Recent Fire Year image from a collection
// ============================================================
function makeMRFY(ic) {
  return ic.map(function(img) {
    var year = ee.Number(img.get('year'));
    return img.addBands(
      ee.Image.constant(year).uint16().rename('year')
        .updateMask(img.select('Probability').gt(0))
    );
  }).select('year').max();
}

var mrfyVis   = {min: 2000, max: 2024, palette: ['yellow', 'orange', 'red']};
var probVis   = {min: 0, max: 100, palette: ['green', 'yellow', 'red']};
var binaryVis = {min: 0, max: 1, palette: 'red', opacity: 0.5};


// ============================================================
// v20260211 — original baseline
// ============================================================
var ic_v20260211 = ee.ImageCollection('projects/fisl-tundra-fire/assets/potter_fire_v20260211');
Map.addLayer(ic_v20260211.max().select('B0').selfMask(),
             probVis, 'v20260211 prob', false);
Map.addLayer(ic_v20260211.max().select('B0').gte(50).selfMask(),
             {min:0, max:1, palette: 'blue', opacity: 0.5}, 'v20260211 binary 50', false);


// ============================================================
// v20260414 — previous ingest (wopgams)
// ============================================================
var ic_v20260414 = ee.ImageCollection('projects/fisl-tundra-fire/assets/potter_fire_v20260414');
Map.addLayer(ic_v20260414.max().select('Probability').selfMask(),
             probVis, 'v20260414 prob', false);
Map.addLayer(ic_v20260414.max().selfMask(),
             {bands: 'Burn_Mask', min:0, max:1, palette: 'red', opacity: 0.5}, 'v20260414 binary', false);
Map.addLayer(makeMRFY(ic_v20260414),
             mrfyVis, 'v20260414 MRFY', false);


// ============================================================
// v20260430 — multiscale model (current best)
// ============================================================
var ic_v20260430 = ee.ImageCollection('projects/fisl-tundra-fire/assets/potter_fire_v20260430');
Map.addLayer(ic_v20260430.max().select('Probability').selfMask(),
             probVis, 'v20260430 prob');
Map.addLayer(ic_v20260430.max().selfMask(),
             {bands: 'Burn_Mask', min:0, max:1, palette: 'red', opacity: 0.5}, 'v20260430 binary', false);
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
