# deploy-rev 2026-11-18b — fuerza re-sync del módulo en Streamlit Cloud
# (incluye analyze_defor_lulc; un deploy a medias dejó este archivo viejo).
import ee
import geopandas as gpd
from shapely.geometry import mapping
import os
import json
import datetime
import streamlit as st

GEE_PROJECT = 'lulcc-traceability-mx40'

# ── Versiones de datasets (actualizadas por el workflow update-datasets) ──────
_VERSIONS_PATH = os.path.join(os.path.dirname(__file__), "dataset_versions.json")

def _load_versions():
    try:
        with open(_VERSIONS_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

_VERSIONS = _load_versions()
HANSEN_ASSET = _VERSIONS.get("hansen_asset", "UMD/hansen/global_forest_change_2025_v1_13")
JRC_TMF_YEAR = int(_VERSIONS.get("jrc_tmf_year", 2023))
JRC_TMF_COLLECTION = f"projects/JRC/TMF/v1_{JRC_TMF_YEAR}/AnnualChanges"

# Año de la versión de Hansen (p. ej. ..._2025_v1_13 → 2025); define el máximo
# de la rampa de color "por año" en el mapa.
try:
    HANSEN_YEAR = int(HANSEN_ASSET.split("global_forest_change_")[1].split("_")[0])
except (IndexError, ValueError):
    HANSEN_YEAR = datetime.date.today().year

# Primer año con datos consistentes para las series casi-en-tiempo-real.
NRT_START_YEAR = 2015

# ── Capas LULC COBIOCOM (clasificación propia, modelo RF v6 2025) ────────────
# Un asset por estado (1 banda uint8 = class_id). La app mosaica los que EXISTAN,
# así que agregar un estado = subir su COG a este id (y añadirlo aquí). Reemplazar
# un estado por una versión nueva del modelo = volver a subir su COG al MISMO id.
# Carpeta raíz de los assets LULC por estado. Convención de cada capa:
#   <folder>/<estado>/<estado>_lulc_<año>_class   (1 banda uint8 = class_id)
# La app DESCUBRE dinámicamente los que existan bajo esta carpeta, así subir un
# estado nuevo lo hace aparecer sin tocar código (ver _discover_lulc_ids).
LULC_ASSET_FOLDER = f"projects/{GEE_PROJECT}/assets/cobiocom"
# Fallback explícito por si no se puede LISTAR la carpeta (permisos/transitorio).
LULC_ASSETS = {
    "Jalisco":   f"{LULC_ASSET_FOLDER}/jalisco/jalisco_lulc_2025_class",
    "Michoacán": f"{LULC_ASSET_FOLDER}/michoacan/michoacan_lulc_2025_class",
}
# Alias de compatibilidad (referencias que esperaban un solo asset).
LULC_ASSET = LULC_ASSETS["Jalisco"]
# (class_id, nombre) en el mismo orden que la paleta de colores.
LULC_CLASSES = [
    (1,  "Bosque templado"),
    (2,  "Selva seca"),
    (3,  "Matorral"),
    (4,  "Pastizal"),
    (5,  "Aguacate"),
    (6,  "Agave"),
    (8,  "Agricultura protegida"),
    (10, "Urbano / Suelo"),
    (12, "Agua"),
    (13, "Agricultura (cultivos)"),
]
LULC_IDS = [cid for cid, _ in LULC_CLASSES]
LULC_PALETTE = ["1b5e20", "7cb342", "c0ca33", "dce775", "004d40",
                "8e24aa", "e0e0e0", "757575", "1565c0", "ffd54f"]
#   Urbano (idx 7) = gris "757575" (antes rojo "b71c1c"): el rojo se reserva para
#   la deforestación, para poder superponerla sobre la cobertura sin confusión.
LULC_AGUACATE_ID = 5
LULC_AGAVE_ID = 6
LULC_SCALE = 10  # resolución nativa en metros
# Clases que se EXCLUYEN de la "deforestación neta": agrícolas y urbanas. La
# pérdida ahí no es tala de bosque sino ruido/reclasificación sobre suelo que ya
# no era forestal. Aguacate(5)/Agave(6) NO se excluyen: ahí sí interesa la pérdida.
LULC_EXCLUDE_DEFOR_IDS = [8, 10, 13]   # Ag. protegida, Urbano, Agricultura
# Rampa temporal para la pérdida por año (igual que el mapa de la app): años
# antiguos en frío (azul) -> recientes en cálido (rojo).
HANSEN_YEAR_PALETTE = ["4575b4", "74add1", "abd9e9", "e0f3f8", "fee090",
                       "fdae61", "f46d43", "d73027", "a50026"]

def current_year():
    """Año actual, calculado en cada ejecución (no fijado a mano)."""
    return datetime.date.today().year

def _exclusive_end():
    """Fin de rango exclusivo = mañana, para incluir todo lo disponible hasta hoy."""
    return (datetime.date.today() + datetime.timedelta(days=1)).isoformat()

@st.cache_resource(show_spinner="Conectando a Google Earth Engine...")
def initialize_gee():
    try:
        project = st.secrets["gee"]["project"]
        creds_json = st.secrets["earthengine"]["credentials"]
        service_account = st.secrets["earthengine"]["service_account"]
        credentials = ee.ServiceAccountCredentials(service_account, key_data=creds_json)
        ee.Initialize(credentials=credentials, project=project)
        return True
    except Exception as e1:
        try:
            ee.Initialize(project=GEE_PROJECT)
            return True
        except Exception as e2:
            try:
                ee.Authenticate()
                ee.Initialize(project=GEE_PROJECT)
                return True
            except:
                # No cachear un fallo: permite reintentar en el siguiente rerun.
                initialize_gee.clear()
                return False


def polygon_to_ee(polygon):
    from shapely.geometry import mapping, MultiPolygon
    from shapely.ops import unary_union

    # Maneja MultiPolygon
    if polygon.geom_type == "MultiPolygon":
        polygon = max(polygon.geoms, key=lambda p: p.area)
    elif polygon.geom_type == "GeometryCollection":
        polys = [g for g in polygon.geoms if g.geom_type in ("Polygon", "MultiPolygon")]
        if not polys:
            raise ValueError("No se encontraron polígonos en la geometría")
        polygon = max(polys, key=lambda p: p.area)
        if polygon.geom_type == "MultiPolygon":
            polygon = max(polygon.geoms, key=lambda p: p.area)

    # Repara geometría inválida
    if not polygon.is_valid:
        polygon = polygon.buffer(0)
        if polygon.geom_type == "MultiPolygon":
            polygon = max(polygon.geoms, key=lambda p: p.area)

    # Simplifica si tiene muchos vértices
    try:
        n_coords = len(list(polygon.exterior.coords))
        if n_coords > 500:
            polygon = polygon.simplify(0.01, preserve_topology=True)
            if polygon.geom_type == "MultiPolygon":
                polygon = max(polygon.geoms, key=lambda p: p.area)
    except AttributeError:
        polygon = polygon.convex_hull

    # Simplifica si es muy grande
    gdf = gpd.GeoDataFrame(geometry=[polygon], crs="EPSG:4326")
    area_ha = gdf.to_crs("EPSG:6933").geometry.area.values[0] / 10000
    if area_ha > 500000:
        polygon = polygon.simplify(0.05, preserve_topology=True)
        if polygon.geom_type == "MultiPolygon":
            polygon = max(polygon.geoms, key=lambda p: p.area)

    # Asegura un Polígono simple antes de construir la geometría.
    if polygon.geom_type == "MultiPolygon":
        polygon = max(polygon.geoms, key=lambda p: p.area)

    # earthengine-api (validación estricta) rechaza como "Invalid GeoJSON":
    #   - tuplas (las que devuelve shapely.mapping)
    #   - coordenadas con componente Z, p. ej. [x, y, z] (longitud impar)
    # Por eso construimos los anillos manualmente forzando cada punto a
    # exactamente [x, y] con floats nativos: 2D, sin tuplas, sin numpy.
    def _ring_2d(coords):
        return [[float(pt[0]), float(pt[1])] for pt in coords]

    rings = [_ring_2d(polygon.exterior.coords)]
    for interior in polygon.interiors:
        rings.append(_ring_2d(interior.coords))

    return ee.Geometry({"type": "Polygon", "coordinates": rings})


def get_polygon_area_ha(polygon):
    gdf = gpd.GeoDataFrame(geometry=[polygon], crs="EPSG:4326")
    gdf_proj = gdf.to_crs("EPSG:6933")
    return round(gdf_proj.geometry.area.values[0] / 10000, 4)


def analyze_hansen(polygon, start_year=1, end_year=25):
    ee_geom = polygon_to_ee(polygon)
    hansen = ee.Image(HANSEN_ASSET)
    loss_year = hansen.select("lossyear")
    gain = hansen.select("gain")
    area_img = ee.Image.pixelArea().divide(10000)

    # Pérdida total
    loss_mask = loss_year.gte(start_year).And(loss_year.lte(end_year))
    total_loss = area_img.updateMask(loss_mask).reduceRegion(
        reducer=ee.Reducer.sum(), geometry=ee_geom,
        scale=30, maxPixels=1e13, bestEffort=True
    ).getInfo()

    # Por año
    by_year = []
    for y in range(start_year, end_year + 1):
        year_mask = loss_year.eq(y)
        year_area = area_img.updateMask(year_mask).reduceRegion(
            reducer=ee.Reducer.sum(), geometry=ee_geom,
            scale=30, maxPixels=1e13, bestEffort=True
        ).getInfo()
        area_ha = year_area.get("area", 0) or 0
        if area_ha > 0:
            by_year.append({"year": 2000 + y, "area_ha": round(area_ha, 4)})

    # Ganancia forestal
    gain_area = area_img.updateMask(gain).reduceRegion(
        reducer=ee.Reducer.sum(), geometry=ee_geom,
        scale=30, maxPixels=1e13, bestEffort=True
    ).getInfo()

    loss_image = loss_year.updateMask(loss_mask)

    return {
        "total_loss_ha": round(total_loss.get("area", 0) or 0, 4),
        "gain_ha": round(gain_area.get("area", 0) or 0, 4),
        "by_year": by_year,
        "loss_image": loss_image
    }


def analyze_glad(polygon):
    ee_geom = polygon_to_ee(polygon)
    try:
        mosaic = ee.ImageCollection("projects/glad/alert/UpdResult") \
            .filterBounds(ee_geom) \
            .mosaic()
        # La banda de alertas lleva el año en el nombre (alertDate25, alertDate26…)
        # y cambia cada año. En vez de fijarla, descubrimos la más reciente que
        # exista para esta zona; así no se rompe al cambiar de año.
        band_names = mosaic.bandNames().getInfo()
        alert_bands = sorted([b for b in band_names if b.startswith("alertDate")])
        if not alert_bands:
            return {"alert_area_ha": 0, "alert_image": None, "by_year": [],
                    "note": "Sin alertas GLAD para esta zona (cobertura enfocada en trópicos)."}
        glad = mosaic.select(alert_bands[-1])
        area_img = ee.Image.pixelArea().divide(10000)
        alert_mask = glad.gt(0)
        alert_area = area_img.updateMask(alert_mask).reduceRegion(
            reducer=ee.Reducer.sum(), geometry=ee_geom,
            scale=10, maxPixels=1e13, bestEffort=True
        ).getInfo()
        area_val = list(alert_area.values())[0] if alert_area else 0
        return {
            "alert_area_ha": round(area_val or 0, 4),
            "alert_image": glad.updateMask(alert_mask),
            "by_year": []
        }
    except Exception as e:
        return {"alert_area_ha": 0, "alert_image": None, "by_year": [], "note": str(e)}


def analyze_jrc_deforestation(polygon):
    ee_geom = polygon_to_ee(polygon)
    try:
        jrc = ee.ImageCollection(JRC_TMF_COLLECTION) \
            .filterBounds(ee_geom).mosaic()
        area_img = ee.Image.pixelArea().divide(10000)

        years = list(range(2015, JRC_TMF_YEAR + 1))
        by_year_defor   = []
        by_year_degrad  = []
        by_year_regrowth = []

        for y in years:
            band = f"Dec{y}"
            b = jrc.select(band)

            # Deforestación
            defor_mask = b.eq(3)
            da = area_img.updateMask(defor_mask).reduceRegion(
                reducer=ee.Reducer.sum(), geometry=ee_geom,
                scale=30, maxPixels=1e13, bestEffort=True
            ).getInfo()
            dv = list(da.values())[0] if da else 0
            if (dv or 0) > 0:
                by_year_defor.append({"year": y, "area_ha": round(dv or 0, 4)})

            # Degradación
            degrad_mask = b.eq(2)
            dga = area_img.updateMask(degrad_mask).reduceRegion(
                reducer=ee.Reducer.sum(), geometry=ee_geom,
                scale=30, maxPixels=1e13, bestEffort=True
            ).getInfo()
            dgv = list(dga.values())[0] if dga else 0
            if (dgv or 0) > 0:
                by_year_degrad.append({"year": y, "area_ha": round(dgv or 0, 4)})

            # Regrowth
            rg_mask = b.eq(4)
            rga = area_img.updateMask(rg_mask).reduceRegion(
                reducer=ee.Reducer.sum(), geometry=ee_geom,
                scale=30, maxPixels=1e13, bestEffort=True
            ).getInfo()
            rgv = list(rga.values())[0] if rga else 0
            if (rgv or 0) > 0:
                by_year_regrowth.append({"year": y, "area_ha": round(rgv or 0, 4)})

        # Totales banda más reciente
        band_latest = jrc.select(f"Dec{JRC_TMF_YEAR}")
        defor_mask  = band_latest.eq(3)
        degrad_mask = band_latest.eq(2)
        defor_total = area_img.updateMask(defor_mask).reduceRegion(
            reducer=ee.Reducer.sum(), geometry=ee_geom,
            scale=30, maxPixels=1e13, bestEffort=True
        ).getInfo()
        degrad_total = area_img.updateMask(degrad_mask).reduceRegion(
            reducer=ee.Reducer.sum(), geometry=ee_geom,
            scale=30, maxPixels=1e13, bestEffort=True
        ).getInfo()

        return {
            "deforestation_ha":  round(list(defor_total.values())[0]  or 0, 4),
            "degradation_ha":    round(list(degrad_total.values())[0] or 0, 4),
            "by_year_defor":     by_year_defor,
            "by_year_degrad":    by_year_degrad,
            "by_year_regrowth":  by_year_regrowth,
            "regrowth_ha":       round(sum(r["area_ha"] for r in by_year_regrowth), 4),
            "defor_image":  band_latest.updateMask(defor_mask),
            "degrad_image": band_latest.updateMask(degrad_mask),
        }
    except Exception as e:
        return {
            "deforestation_ha": 0, "degradation_ha": 0,
            "by_year_defor": [], "by_year_degrad": [], "by_year_regrowth": [],
            "regrowth_ha": 0, "defor_image": None, "degrad_image": None,
            "note": str(e)
        }


def analyze_jrc_amazon(polygon):
    ee_geom = polygon_to_ee(polygon)
    try:
        jrc = ee.ImageCollection(JRC_TMF_COLLECTION) \
            .filterBounds(ee_geom).mosaic()
        area_img = ee.Image.pixelArea().divide(10000)
        band = jrc.select(f"Dec{JRC_TMF_YEAR}")
        results = {}
        labels = {
            "undisturbed_ha": 1,
            "degraded_ha":    2,
            "deforested_ha":  3,
            "regrowth_ha":    4,
        }
        for name, cls in labels.items():
            mask = band.eq(cls)
            area = area_img.updateMask(mask).reduceRegion(
                reducer=ee.Reducer.sum(), geometry=ee_geom,
                scale=30, maxPixels=1e13, bestEffort=True
            ).getInfo()
            val = list(area.values())[0] if area else 0
            results[name] = round(val or 0, 4)
        return results
    except Exception as e:
        return {"undisturbed_ha": 0, "degraded_ha": 0,
                "deforested_ha": 0, "regrowth_ha": 0, "note": str(e)}


def analyze_modis_burn(polygon):
    ee_geom = polygon_to_ee(polygon)
    try:
        area_img = ee.Image.pixelArea().divide(10000)
        by_year = []
        for y in range(NRT_START_YEAR, current_year() + 1):
            modis = ee.ImageCollection("MODIS/061/MCD64A1") \
                .filterBounds(ee_geom) \
                .filterDate(f"{y}-01-01", f"{y + 1}-01-01") \
                .select("BurnDate").mosaic()
            burn_mask = modis.gt(0)
            burn_area = area_img.updateMask(burn_mask).reduceRegion(
                reducer=ee.Reducer.sum(), geometry=ee_geom,
                scale=500, maxPixels=1e13, bestEffort=True
            ).getInfo()
            val = list(burn_area.values())[0] if burn_area else 0
            if (val or 0) > 0:
                by_year.append({"year": y, "area_ha": round(val or 0, 4)})

        total = sum(r["area_ha"] for r in by_year)
        modis_full = ee.ImageCollection("MODIS/061/MCD64A1") \
            .filterBounds(ee_geom) \
            .filterDate(f"{NRT_START_YEAR}-01-01", _exclusive_end()) \
            .select("BurnDate").mosaic()
        burn_img = modis_full.updateMask(modis_full.gt(0))
        return {"burn_area_ha": round(total, 4), "by_year": by_year, "burn_image": burn_img}
    except Exception as e:
        return {"burn_area_ha": 0, "by_year": [], "burn_image": None, "note": str(e)}


def _discover_lulc_ids():
    """Lista dinámicamente los assets de clasificación por estado bajo
    LULC_ASSET_FOLDER (…/cobiocom/<estado>/<...>_class). Así, subir un estado
    nuevo lo hace aparecer en la app SIN tocar código. Si la carpeta no se puede
    listar (permisos/transitorio), cae al dict LULC_ASSETS."""
    ids = []
    try:
        for folder in ee.data.listAssets({"parent": LULC_ASSET_FOLDER}).get("assets", []):
            if folder.get("type") != "FOLDER":
                continue
            for a in ee.data.listAssets({"parent": folder["name"]}).get("assets", []):
                if a.get("type") == "IMAGE" and a.get("id", "").endswith("_class"):
                    ids.append(a["id"])
    except Exception:
        pass
    return ids or list(LULC_ASSETS.values())


@st.cache_resource(show_spinner=False, ttl=3600)
def _lulc_image():
    """Mosaico de TODAS las clasificaciones LULC por estado disponibles (mismo
    esquema de clases). Descubre los estados dinámicamente (_discover_lulc_ids) y
    es robusto a assets aún no subidos: incluye solo los legibles. Devuelve None si
    no hay ninguno (sin cachear ese vacío). Cache de 1 h -> un estado recién subido
    aparece en <=1 h, o de inmediato si se reinicia la app."""
    imgs = []
    for aid in _discover_lulc_ids():
        try:
            ee.data.getAsset(aid)                       # existe + permiso de lectura
            imgs.append(ee.Image(aid).select(0).rename("class"))  # banda homogénea p/ mosaicar
        except Exception:
            pass                                         # asset aún no subido -> se omite
    if not imgs:
        _lulc_image.clear()
        return None
    return ee.ImageCollection(imgs).mosaic()


def analyze_lulc(polygon):
    """Clasificación LULC COBIOCOM: área por clase dentro del polígono (en una
    sola consulta con reductor agrupado) + imágenes para el mapa: clasificación
    completa, aguacate y agave por separado (sobreponibles). Cubre todos los
    estados con asset disponible (Jalisco + Michoacán)."""
    ee_geom = polygon_to_ee(polygon)
    try:
        img = _lulc_image()
        if img is None:
            return {"aguacate_ha": 0, "agave_ha": 0, "by_class": [],
                    "class_image": None, "aguacate_image": None, "agave_image": None,
                    "note": "Sin assets LULC disponibles en GEE (¿aún no subidos?)."}
        area_img = ee.Image.pixelArea().divide(10000)
        # Área por clase en UNA sola llamada: suma del área agrupada por class_id.
        grouped = area_img.addBands(img).reduceRegion(
            reducer=ee.Reducer.sum().group(groupField=1, groupName="class"),
            geometry=ee_geom, scale=LULC_SCALE, maxPixels=1e13, bestEffort=True
        ).getInfo()
        areas = {int(g["class"]): round(g["sum"], 4)
                 for g in grouped.get("groups", [])}
        by_class = [{"class_id": cid, "name": name, "area_ha": areas.get(cid, 0.0)}
                    for cid, name in LULC_CLASSES]
        # Imágenes para el mapa. La clasificación completa se remapea a 0..N-1
        # para alinear con la paleta; aguacate/agave quedan como máscaras 1/0.
        class_img = img.remap(LULC_IDS, list(range(len(LULC_IDS))))
        return {
            "aguacate_ha": areas.get(LULC_AGUACATE_ID, 0.0),
            "agave_ha":    areas.get(LULC_AGAVE_ID, 0.0),
            "by_class":    by_class,
            "class_image":    class_img,
            "aguacate_image": img.eq(LULC_AGUACATE_ID).selfMask(),
            "agave_image":    img.eq(LULC_AGAVE_ID).selfMask(),
        }
    except Exception as e:
        return {"aguacate_ha": 0, "agave_ha": 0, "by_class": [],
                "class_image": None, "aguacate_image": None,
                "agave_image": None, "note": str(e)}


def analyze_defor_lulc(polygon, start_year=1, end_year=25, exclude_ids=None):
    """Intersección deforestación × clasificación LULC, en una sola consulta.

    Usa la pérdida de Hansen (lossyear) dentro de la ventana [start_year, end_year]
    (formato Hansen: 1..25 = 2001..2025) y la agrupa por clase LULC. Devuelve:
      - by_class: área de pérdida por clase (¿cuánta en bosque/aguacate/agave/agricultura…?)
      - total_ha: pérdida total sobre área CLASIFICADA
      - excluded_ha: pérdida en clases agrícolas/urbanas (exclude_ids)
      - net_ha: deforestación NETA = total - excluida
      - net_image: la pérdida fuera de esas clases (para el mapa)
    """
    if exclude_ids is None:
        exclude_ids = LULC_EXCLUDE_DEFOR_IDS
    ee_geom = polygon_to_ee(polygon)
    excl_names = [name for cid, name in LULC_CLASSES if cid in exclude_ids]
    empty = {"by_class": [], "total_ha": 0.0, "excluded_ha": 0.0, "net_ha": 0.0,
             "net_image": None, "exclude_ids": list(exclude_ids), "exclude_names": excl_names}
    try:
        lulc = _lulc_image()
        if lulc is None:
            return {**empty, "note": "Sin capa LULC disponible para intersectar."}
        loss_year = ee.Image(HANSEN_ASSET).select("lossyear")
        loss_mask = loss_year.gte(start_year).And(loss_year.lte(end_year))
        area_img = ee.Image.pixelArea().divide(10000)
        # suma del área de pérdida AGRUPADA por class_id (banda 1 = lulc)
        grouped = area_img.updateMask(loss_mask).addBands(lulc).reduceRegion(
            reducer=ee.Reducer.sum().group(groupField=1, groupName="class"),
            geometry=ee_geom, scale=30, maxPixels=1e13, bestEffort=True
        ).getInfo()
        areas = {int(g["class"]): round(g.get("sum", 0) or 0, 4)
                 for g in grouped.get("groups", [])}
        by_class = [{"class_id": cid, "name": name, "area_ha": areas.get(cid, 0.0)}
                    for cid, name in LULC_CLASSES]
        total = round(sum(areas.values()), 4)
        excluded = round(sum(areas.get(c, 0.0) for c in exclude_ids), 4)
        net = round(max(total - excluded, 0.0), 4)
        # imagen para el mapa: pérdida SOLO fuera de agrícola/urbano (keep==1)
        keep = lulc.remap(list(exclude_ids), [0] * len(exclude_ids), 1)
        net_image = loss_year.updateMask(loss_mask).updateMask(keep)
        return {"by_class": by_class, "total_ha": total, "excluded_ha": excluded,
                "net_ha": net, "net_image": net_image,
                "exclude_ids": list(exclude_ids), "exclude_names": excl_names}
    except Exception as e:
        return {**empty, "note": str(e)}


def report_map_png(polygon, start_year=1, end_year=25, dim=640):
    """PNG (bytes) de 2 paneles para el reporte, con el polígono dibujado:
       a) Clasificación LULC (paleta de clases)
       b) Deforestación por AÑO (Hansen, rampa temporal) sobre satélite S2
    Devuelve None si algo falla (el reporte sigue sin el mapa). start/end en
    formato Hansen (1..25 = 2001..2025)."""
    try:
        import io as _io
        import urllib.request
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        from matplotlib.colors import LinearSegmentedColormap, Normalize
        from matplotlib.cm import ScalarMappable

        ee_geom = polygon_to_ee(polygon)
        fc = ee.FeatureCollection([ee.Feature(ee_geom)])
        minx, miny, maxx, maxy = polygon.bounds
        bx = (maxx - minx) * 0.08 or 0.01
        by = (maxy - miny) * 0.08 or 0.01
        region = ee.Geometry.Rectangle([minx - bx, miny - by, maxx + bx, maxy + by])
        outline = ee.Image().byte().paint(fc, 1, 3).selfMask()

        # Base satelital Sentinel-2 (mediana reciente, sin nubes); fallback gris
        try:
            base = (ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED")
                    .filterBounds(region).filterDate("2024-01-01", "2026-01-01")
                    .filter(ee.Filter.lt("CLOUDY_PIXEL_PERCENTAGE", 40)).median()
                    .visualize(bands=["B4", "B3", "B2"], min=200, max=3000))
        except Exception:
            base = ee.Image.constant(90).visualize(min=0, max=255)

        # Panel a) LULC
        lulc = _lulc_image()
        if lulc is not None:
            lulc_vis = lulc.remap(LULC_IDS, list(range(len(LULC_IDS)))).visualize(
                min=0, max=len(LULC_IDS) - 1, palette=LULC_PALETTE)
        else:
            lulc_vis = base
        panel_a = lulc_vis.blend(outline.visualize(min=0, max=1, palette=["ffffff"]))

        # Panel b) deforestación por año sobre satélite
        loss_year = ee.Image(HANSEN_ASSET).select("lossyear")
        lm = loss_year.gte(start_year).And(loss_year.lte(end_year))
        ymax = max(end_year, start_year + 1)
        loss_vis = loss_year.updateMask(lm).visualize(
            min=start_year, max=ymax, palette=HANSEN_YEAR_PALETTE)
        panel_b = base.blend(loss_vis).blend(
            outline.visualize(min=0, max=1, palette=["00e5ff"]))

        # Panel c) SUPERPUESTO: deforestación (rojo sólido) sobre la clasificación
        # -> se ve en qué clase cae cada pérdida.
        loss_red = loss_year.updateMask(lm).visualize(min=start_year, max=ymax,
                                                      palette=["ff1744"])
        panel_c = lulc_vis.blend(loss_red).blend(
            outline.visualize(min=0, max=1, palette=["00e5ff"]))

        def thumb(img):
            url = img.getThumbURL({"region": region, "dimensions": dim, "format": "png"})
            with urllib.request.urlopen(url, timeout=90) as r:
                return plt.imread(_io.BytesIO(r.read()))

        imgs = [thumb(panel_a), thumb(panel_b), thumb(panel_c)]
        titles = ["a) Clasificación LULC (RF v6)",
                  "b) Deforestación por año (Hansen)",
                  "c) Deforestación sobre cobertura"]
        fig, axs = plt.subplots(1, 3, figsize=(10.6, 3.5))
        for ax, im, t in zip(axs, imgs, titles):
            ax.imshow(im); ax.set_title(t, fontsize=9, loc="left")
            ax.set_xticks([]); ax.set_yticks([])
            for s in ax.spines.values():
                s.set_edgecolor("#888888"); s.set_linewidth(0.6)
        cmap = LinearSegmentedColormap.from_list("yr", ["#" + c for c in HANSEN_YEAR_PALETTE])
        sm = ScalarMappable(norm=Normalize(2000 + start_year, 2000 + ymax), cmap=cmap)
        sm.set_array([])
        cb = fig.colorbar(sm, ax=axs[1], fraction=0.05, pad=0.03, orientation="horizontal")
        cb.ax.tick_params(labelsize=6.5); cb.set_label("Año de pérdida", fontsize=7)
        axs[2].text(0.5, -0.045, "rojo = deforestación", transform=axs[2].transAxes,
                    ha="center", va="top", fontsize=7, color="#c00000")
        fig.tight_layout()
        buf = _io.BytesIO()
        fig.savefig(buf, format="png", dpi=185, bbox_inches="tight", facecolor="white")
        plt.close(fig); buf.seek(0)
        return buf.getvalue()
    except Exception:
        return None


def get_tile_url(image, vis_params):
    try:
        map_id = image.getMapId(vis_params)
        return map_id['tile_fetcher'].url_format
    except:
        return None


@st.cache_data(show_spinner=False, ttl=3600)
def get_lulc_tile_urls():
    """URLs de tiles (GEE) de las capas LULC para mostrarlas como overlays en
    cualquier mapa (p. ej. el mapa de inicio): clasificación completa, aguacate
    y agave. El asset es estático → se cachea 1 h. Si falla (asset no subido o
    GEE sin iniciar) devuelve None y no cachea el fallo."""
    try:
        img = _lulc_image()
        if img is None:
            get_lulc_tile_urls.clear()
            return {"class": None, "aguacate": None, "agave": None}
        class_img = img.remap(LULC_IDS, list(range(len(LULC_IDS))))
        urls = {
            "class":    get_tile_url(class_img,
                        {"min": 0, "max": len(LULC_PALETTE) - 1, "palette": LULC_PALETTE}),
            "aguacate": get_tile_url(img.eq(LULC_AGUACATE_ID).selfMask(),
                        {"min": 1, "max": 1, "palette": ["004d40"]}),
            "agave":    get_tile_url(img.eq(LULC_AGAVE_ID).selfMask(),
                        {"min": 1, "max": 1, "palette": ["8e24aa"]}),
        }
    except Exception:
        urls = {"class": None, "aguacate": None, "agave": None}
    if not urls.get("class"):
        get_lulc_tile_urls.clear()   # no cachear un fallo transitorio
    return urls