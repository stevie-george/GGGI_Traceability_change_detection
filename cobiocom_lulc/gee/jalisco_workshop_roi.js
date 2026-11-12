/**********************************************************************************************
 *  COBIOCOM — Jalisco · Recolección de ROIs de entrenamiento (workshop)
 *  --------------------------------------------------------------------------------------------
 *  Qué hace: construye un mosaico Sentinel-2 sin nubes, multi-año y de dos temporadas
 *  (seca + lluvias), con índices espectrales, y monta un flujo HÍBRIDO de muestreo para
 *  recolectar ROIs (regiones de interés) de entrenamiento sobre JALISCO.
 *
 *    · Clases fáciles (bosque, matorral, pastizal, urbano, suelo, agua)  -> auto (ESA WorldCover)
 *    · Clases difíciles (aguacate, agave, otros cultivos)                -> digitalización manual
 *
 *  El clasificador final corre LOCALMENTE en Python (Planetary Computer). Este script sólo
 *  recolecta y exporta las ROIs etiquetadas (geometría + clase). Dibujar y exportar ROIs en
 *  GEE es gratuito: aquí no se hace el cómputo pesado de clasificación.
 *
 *  Leyenda: 12 clases, idéntica a cobiocom_lulc/legend.csv (class_id 1..12).
 *  Autor: Steph / GGGI México — 2026-08.  Pegar en https://code.earthengine.google.com
 *
 *  PASOS (léelo primero)
 *    1. Sube EntidadesCOBIOCOM (el .zip del shapefile) como asset y ajusta ASSET_ID abajo.
 *    2. Corre el script -> revisa RGB + falso color (seca y lluvias) + dNDVI sobre Jalisco.
 *    3. Crea imports de geometría (engrane -> "Import as FeatureCollection") con los nombres
 *       EXACTOS de la seccion 7: avocado, agave, other_crop, protected_ag, annual_ag.
 *       Dibuja poligonos sobre ejemplos PUROS y confiables (ver SAMPLING_PROTOCOL.md).
 *    4. Descomenta las lineas manualParts.merge(...) conforme crees cada import.
 *    5. Corre el muestreo automatico (clases faciles) y revisa/limpia los puntos.
 *    6. Exporta las ROIs (Drive + asset). Alimentan el muestreador local en Python.
 *********************************************************************************************/


/* =====================================================================================
 * 0.  CONFIG  — edita esto
 * ===================================================================================== */
// 0a. Límite: sube EntidadesCOBIOCOM_shp.zip como asset y pon su ruta aquí.
var ASSET_ID   = 'projects/ee-stephaniegeorge/assets/EntidadesCOBIOCOM';  // <-- EDITA si aplica
var STATE_FIELD = 'CVE_ENT';   // campo INEGI en el asset
var STATE_CODE  = '14';        // Jalisco (procesamos por partes; empezamos aquí)

// Respaldo si aún no subes el asset: deriva Jalisco de FAO GAUL.
var USE_ASSET  = true;
var GAUL_NAME  = 'Jalisco';

// 0b. Ventana temporal y temporadas (varios años apilados = más pixeles limpios).
var YEAR_START = 2023;
var YEAR_END   = 2025;
var DRY_MONTHS = [11, 12, 1, 2, 3, 4];   // seca  (Nov–Abr)
var WET_MONTHS = [6, 7, 8, 9, 10];       // lluvias (Jun–Oct)

// 0c. Enmascarado de nubes (Cloud Score+).
var CS_BAND         = 'cs_cdf';
var CLEAR_THRESHOLD = 0.60;

// 0d. Muestreo.
var SAMPLE_SCALE = 10;
var EXPORT_PREFIX = 'COBIOCOM_Jalisco';
var AUTO_N = {                    // puntos por clase para el muestreo auto (clases fáciles)
  temperate: 300, dry: 300, shrub: 300, grass: 300,
  urban: 250, bare: 200, water: 150, cropland: 400   // cropland -> se re-etiqueta a mano
};


/* =====================================================================================
 * 1.  ÁREA DE ESTUDIO  (Jalisco)
 * ===================================================================================== */
var states;
if (USE_ASSET) {
  states = ee.FeatureCollection(ASSET_ID)
             .filter(ee.Filter.eq(STATE_FIELD, STATE_CODE));
} else {
  states = ee.FeatureCollection('FAO/GAUL/2015/level1')
             .filter(ee.Filter.eq('ADM0_NAME', 'Mexico'))
             .filter(ee.Filter.eq('ADM1_NAME', GAUL_NAME));
}
var aoi = states.geometry();
Map.centerObject(states, 8);
Map.setOptions('SATELLITE');   // fondo VHR (Google satélite) para fotointerpretación
Map.addLayer(states.style({color: 'ffff00', fillColor: '00000000', width: 2}),
             {}, '0 · Límite Jalisco');


/* =====================================================================================
 * 2.  SENTINEL-2 + CLOUD SCORE+
 * ===================================================================================== */
var S2  = ee.ImageCollection('COPERNICUS/S2_SR_HARMONIZED');
var CSP = ee.ImageCollection('GOOGLE/CLOUD_SCORE_PLUS/V1/S2_HARMONIZED');
var OPTICAL = ['B2','B3','B4','B5','B6','B7','B8','B8A','B11','B12'];

function maskAndScale(img) {
  var masked = img.updateMask(img.select(CS_BAND).gte(CLEAR_THRESHOLD));
  return masked.select(OPTICAL).multiply(0.0001)        // HARMONIZED -> reflectancia (0–1)
               .copyProperties(img, ['system:time_start']);
}

function seasonCollection(months) {
  return S2
    .filterBounds(aoi)
    .filter(ee.Filter.calendarRange(YEAR_START, YEAR_END, 'year'))
    .linkCollection(CSP, [CS_BAND])
    .map(function(img) { return img.set('month', img.date().get('month')); })
    .filter(ee.Filter.inList('month', months))
    .map(maskAndScale);
}


/* =====================================================================================
 * 3.  ÍNDICES ESPECTRALES
 * ===================================================================================== */
function addIndices(img) {
  var ndvi  = img.normalizedDifference(['B8','B4']).rename('NDVI');    // verdor
  var ndmi  = img.normalizedDifference(['B8','B11']).rename('NDMI');   // humedad del dosel
  var ndre  = img.normalizedDifference(['B8','B5']).rename('NDRE');    // borde rojo (vigor)
  var mndwi = img.normalizedDifference(['B3','B11']).rename('MNDWI');  // agua
  var evi = img.expression('2.5*((N-R)/(N+6*R-7.5*B+1))',
      {N: img.select('B8'), R: img.select('B4'), B: img.select('B2')}).rename('EVI');
  var bsi = img.expression('((S+R)-(N+B))/((S+R)+(N+B))',
      {S: img.select('B11'), R: img.select('B4'),
       N: img.select('B8'),  B: img.select('B2')}).rename('BSI');      // suelo desnudo
  return img.addBands([ndvi, ndmi, ndre, mndwi, evi, bsi]);
}


/* =====================================================================================
 * 4.  COMPOSICIONES POR TEMPORADA (mediana) + DELTAS + STACK
 * ===================================================================================== */
function buildSeason(months, suffix) {
  var comp = seasonCollection(months).map(addIndices).median().clip(aoi);
  var names = comp.bandNames();
  return comp.rename(names.map(function(n){ return ee.String(n).cat('_').cat(suffix); }));
}
var dry = buildSeason(DRY_MONTHS, 'dry');
var wet = buildSeason(WET_MONTHS, 'wet');

// Amplitud fenológica: alta en cultivos anuales/pastizal; ~0 en perennes (aguacate) / bosque.
var dNDVI = wet.select('NDVI_wet').subtract(dry.select('NDVI_dry')).rename('dNDVI');
var dNDMI = wet.select('NDMI_wet').subtract(dry.select('NDMI_dry')).rename('dNDMI');

var stack = dry.addBands(wet).addBands(dNDVI).addBands(dNDMI);
print('Bandas del stack de clasificación:', stack.bandNames());


/* =====================================================================================
 * 5.  VISUALIZACIÓN  — RGB + falso color + SWIR + dNDVI (para fotointerpretar)
 * ===================================================================================== */
var rgbVis   = {min: 0.02, max: 0.25, gamma: 1.1};
var falseVis = {min: 0.02, max: 0.40, gamma: 1.1};
var swirVis  = {min: 0.02, max: 0.50, gamma: 1.1};

// RGB verdadero (R=B4,G=B3,B=B2)
Map.addLayer(dry.select(['B4_dry','B3_dry','B2_dry']), rgbVis, '1 · RGB seca', true);
Map.addLayer(wet.select(['B4_wet','B3_wet','B2_wet']), rgbVis, '2 · RGB lluvias', false);
// Falso color NIR (R=B8) — vegetación = rojo; aguacate perenne = rojo brillante todo el año
Map.addLayer(dry.select(['B8_dry','B4_dry','B3_dry']), falseVis, '3 · Falso color NIR seca', true);
Map.addLayer(wet.select(['B8_wet','B4_wet','B3_wet']), falseVis, '4 · Falso color NIR lluvias', false);
// Falso color SWIR (R=B12,G=B8A,B=B4) — mejor para aguacate vs agave vs suelo/humedad
Map.addLayer(dry.select(['B12_dry','B8A_dry','B4_dry']), swirVis, '5 · Falso color SWIR seca', false);
// dNDVI (lluvias - seca)
Map.addLayer(dNDVI, {min: -0.3, max: 0.5,
  palette: ['#8c510a','#f6e8c3','#c7eae5','#01665e']}, '6 · dNDVI (lluvias-seca)', false);

// VHR gratis: el fondo Google Satélite ya está activo (Map.setOptions('SATELLITE')).
// NOTA (2026-08): el programa GRATUITO NICFI terminó -> ahora es "Planet Tropical Forest
// Observatory" (de pago, ~180 USD/mes, 1 usuario, sin redistribución). La colección GEE de
// abajo quedó ligada al programa anterior y puede NO estar disponible; descomenta sólo si tu
// cuenta EE tiene acceso vigente:
// var nicfi = ee.ImageCollection('projects/planet-nicfi/assets/basemaps/americas');
// Map.addLayer(nicfi.sort('system:time_start', false).first(),
//              {bands: ['R','G','B'], min: 64, max: 5454, gamma: 1.8}, '7 · Planet NICFI', false);
// VHR adicional (Esri) disponible en QGIS para el set riguroso interno.


/* =====================================================================================
 * 6.  LEYENDA  (12 clases — igual que legend.csv)
 * ===================================================================================== */
var CLASSES = [
  {code: 1,  name: 'Bosque templado',        palette: '1b5e20'},
  {code: 2,  name: 'Selva baja caducifolia', palette: '7cb342'},
  {code: 3,  name: 'Matorral',               palette: 'c0ca33'},
  {code: 4,  name: 'Pastizal',               palette: 'dce775'},
  {code: 5,  name: 'Aguacate',               palette: '004d40'},
  {code: 6,  name: 'Agave',                  palette: '8e24aa'},
  {code: 7,  name: 'Otro cultivo perenne',   palette: 'f9a825'},
  {code: 8,  name: 'Agricultura protegida',  palette: 'e0e0e0'},
  {code: 9,  name: 'Agricultura anual',      palette: 'ffd54f'},
  {code: 10, name: 'Urbano',                 palette: 'b71c1c'},
  {code: 11, name: 'Suelo / desmonte',       palette: 'a1887f'},
  {code: 12, name: 'Agua',                   palette: '1565c0'}
];
var CLASS_VALUES  = CLASSES.map(function(c){ return c.code; });
var CLASS_PALETTE = CLASSES.map(function(c){ return c.palette; });


/* =====================================================================================
 * 7.  DIGITALIZACIÓN MANUAL  (clases difíciles: cultivos)
 * -------------------------------------------------------------------------------------
 *  Crea UN import de geometría por clase (engrane -> Import as FeatureCollection) con
 *  EXACTAMENTE estos nombres, dibuja polígonos puros y descomenta su línea:
 *      avocado (5)   agave (6)   other_crop (7)   protected_ag (8)   annual_ag (9)
 *  (Opcional, para reforzar: forest_manual, bare_manual con label(fc, code).)
 * ===================================================================================== */
function label(fc, code) {
  return fc.map(function(f){ return f.set({'class': code, 'source': 'manual'}); });
}
var manualParts = ee.FeatureCollection([]);   // empieza vacío
// manualParts = manualParts.merge(label(avocado,      5));
// manualParts = manualParts.merge(label(agave,        6));
// manualParts = manualParts.merge(label(other_crop,   7));
// manualParts = manualParts.merge(label(protected_ag, 8));
// manualParts = manualParts.merge(label(annual_ag,    9));


/* =====================================================================================
 * 8.  MUESTREO AUTOMÁTICO  (clases fáciles, desde ESA WorldCover 2021)
 * -------------------------------------------------------------------------------------
 *  WorldCover siembra bosque/matorral/pastizal/urbano/suelo/agua. NO distingue
 *  aguacate/agave -> esos van en la sección 7. El bosque (WC=árbol) se divide en
 *  templado(1)/caducifolia(2) por altitud SRTM (umbral 1500 m). Trata estos puntos
 *  como CANDIDATOS: verifícalos contra el falso color.
 * ===================================================================================== */
var wc   = ee.ImageCollection('ESA/WorldCover/v200').first().clip(aoi);   // banda 'Map'
var elev = ee.Image('USGS/SRTMGL1_003').select('elevation');

//  WC: 10 árbol,20 arbusto,30 pasto,40 cultivo,50 construido,60 desnudo,80 agua
var autoClass = wc.remap([10, 20, 30, 40, 50, 60, 80],
                         [ 1,  3,  4, 99, 10, 11, 12]).rename('class');
// divide el bosque (1) en templado(1, alto) / caducifolia(2, bajo) por altitud
autoClass = autoClass.where(autoClass.eq(1).and(elev.lt(1500)), 2);

var samples = autoClass.addBands(ee.Image.pixelLonLat()).stratifiedSample({
  numPoints: 0, classBand: 'class', region: aoi, scale: SAMPLE_SCALE,
  classValues: [1, 2, 3, 4, 10, 11, 12, 99],
  classPoints: [AUTO_N.temperate, AUTO_N.dry, AUTO_N.shrub, AUTO_N.grass,
                AUTO_N.urban, AUTO_N.bare, AUTO_N.water, AUTO_N.cropland],
  seed: 42, geometries: true, tileScale: 4
});
var croplandCandidates = samples.filter(ee.Filter.eq('class', 99))
      .map(function(f){ return f.set('source', 'auto_candidate'); });
var autoEasy = samples.filter(ee.Filter.neq('class', 99))
      .map(function(f){ return f.set('source', 'auto'); });

Map.addLayer(croplandCandidates, {color: 'orange'}, '8 · cultivos a re-etiquetar', false);
Map.addLayer(autoEasy,           {color: 'cyan'},   '9 · puntos auto (clases fáciles)', false);
print('Puntos auto (fáciles):', autoEasy.size());
print('Candidatos de cultivo a re-etiquetar:', croplandCandidates.size());


/* =====================================================================================
 * 9.  EXPORTES  — geometrías etiquetadas para el clasificador LOCAL
 * -------------------------------------------------------------------------------------
 *  Se exportan las GEOMETRÍAS + clase (no valores de banda de GEE): el muestreador local
 *  en Python vuelve a extraer sobre los compuestos locales (Planetary Computer).
 * ===================================================================================== */
// Polígonos manuales (cultivos) -> SHP a Drive + asset
Export.table.toDrive({collection: manualParts, folder: 'COBIOCOM',
  description: EXPORT_PREFIX + '_manual_polys', fileFormat: 'SHP'});
Export.table.toAsset({collection: manualParts,
  description: EXPORT_PREFIX + '_manual_polys_asset',
  assetId: 'projects/ee-stephaniegeorge/assets/' + EXPORT_PREFIX + '_manual_polys'});

// Puntos auto (clases fáciles) -> SHP a Drive
Export.table.toDrive({collection: autoEasy, folder: 'COBIOCOM',
  description: EXPORT_PREFIX + '_auto_points', fileFormat: 'SHP'});

// Candidatos de cultivo (re-etiquetar en QGIS y reimportar) -> SHP a Drive
Export.table.toDrive({collection: croplandCandidates, folder: 'COBIOCOM',
  description: EXPORT_PREFIX + '_cropland_candidates', fileFormat: 'SHP'});


/* =====================================================================================
 * 10.  VISTA PREVIA OPCIONAL — Random Forest (sólo para ver separabilidad)
 * -------------------------------------------------------------------------------------
 *  NO es el clasificador final (ese corre local). Sirve para ver, en el taller, si las
 *  clases se separan. Pon RUN_PREVIEW = true cuando ya tengas varios polígonos.
 * ===================================================================================== */
var RUN_PREVIEW = false;
if (RUN_PREVIEW) {
  var bands = stack.bandNames();
  var samp = stack.sampleRegions({collection: manualParts, properties: ['class'],
                                  scale: SAMPLE_SCALE, tileScale: 4})
             .merge(stack.sampleRegions({collection: autoEasy, properties: ['class'],
                                  scale: SAMPLE_SCALE, tileScale: 4}));
  var withR = samp.randomColumn('rnd', 42);
  var tr = withR.filter(ee.Filter.lt('rnd', 0.7));
  var te = withR.filter(ee.Filter.gte('rnd', 0.7));
  var rf = ee.Classifier.smileRandomForest(150).train(tr, 'class', bands);
  Map.addLayer(stack.classify(rf),
    {min: 1, max: 12, palette: CLASS_PALETTE}, '10 · RF preview', false);
  var cm = te.classify(rf).errorMatrix('class', 'classification');
  print('Matriz de confusión (preview):', cm);
  print('Exactitud global (preview):', cm.accuracy());
}


/* =====================================================================================
 * 11.  PANEL DE LEYENDA + INSTRUCCIONES (taller)
 * ===================================================================================== */
var panel = ui.Panel({style: {position: 'bottom-left', padding: '8px', width: '260px'}});
panel.add(ui.Label('COBIOCOM · Jalisco — ROIs de entrenamiento',
                   {fontWeight: 'bold', fontSize: '14px'}));
panel.add(ui.Label('Dibuja polígonos PUROS de cultivos (secc. 7). Verifica en falso color ' +
                   'SWIR + dNDVI + NICFI antes de confirmar aguacate/agave.',
                   {fontSize: '11px', color: '555'}));
panel.add(ui.Label('Leyenda', {fontWeight: 'bold', margin: '6px 0 2px 0'}));
CLASSES.forEach(function(c) {
  panel.add(ui.Panel({
    layout: ui.Panel.Layout.Flow('horizontal'),
    widgets: [
      ui.Label('', {backgroundColor: '#' + c.palette, padding: '8px', margin: '1px 6px 1px 0'}),
      ui.Label(c.code + ' · ' + c.name, {margin: '1px', fontSize: '12px'})
    ]
  }));
});
Map.add(panel);

/*********************************  FIN DEL SCRIPT  *******************************************/
