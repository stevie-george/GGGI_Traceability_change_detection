import ee
import geopandas as gpd
from shapely.geometry import mapping
import os
import json

GEE_PROJECT = 'ee-stephaniegeorge'

def initialize_gee():
    try:
        # Intenta leer credenciales desde Streamlit secrets (nube)
        import streamlit as st
        project = st.secrets["gee"]["project"]
        creds_json = st.secrets["earthengine"]["credentials"]

        creds_path = os.path.expanduser("~/.config/earthengine/credentials")
        os.makedirs(os.path.dirname(creds_path), exist_ok=True)
        with open(creds_path, "w") as f:
            f.write(creds_json)

        ee.Initialize(project=project)
        return True
    except Exception as e1:
        # Fallback local
        try:
            ee.Initialize(project=GEE_PROJECT)
            return True
        except Exception as e2:
            try:
                ee.Authenticate()
                ee.Initialize(project=GEE_PROJECT)
                return True
            except Exception as e3:
                return False

def polygon_to_ee(polygon):
    return ee.Geometry(mapping(polygon))

def get_polygon_area_ha(polygon):
    gdf = gpd.GeoDataFrame(geometry=[polygon], crs="EPSG:4326")
    gdf_proj = gdf.to_crs("EPSG:6933")
    return round(gdf_proj.geometry.area.values[0] / 10000, 4)

def analyze_hansen(polygon, start_year=1, end_year=24):
    ee_geom = polygon_to_ee(polygon)
    hansen = ee.Image("UMD/hansen/global_forest_change_2024_v1_12")
    loss_year = hansen.select("lossyear")
    degradation = hansen.select("gain")
    area_img = ee.Image.pixelArea().divide(10000)

    # Pérdida total
    loss_mask = loss_year.gte(start_year).And(loss_year.lte(end_year))
    total_loss = area_img.updateMask(loss_mask).reduceRegion(
        reducer=ee.Reducer.sum(), geometry=ee_geom, scale=30, maxPixels=1e10
    ).getInfo()

    # Por año
    by_year = []
    for y in range(start_year, end_year + 1):
        year_mask = loss_year.eq(y)
        year_area = area_img.updateMask(year_mask).reduceRegion(
            reducer=ee.Reducer.sum(), geometry=ee_geom, scale=30, maxPixels=1e10
        ).getInfo()
        area_ha = year_area.get("area", 0) or 0
        if area_ha > 0:
            by_year.append({"year": 2000 + y, "area_ha": round(area_ha, 4)})

    # Ganancia forestal
    gain_area = area_img.updateMask(degradation).reduceRegion(
        reducer=ee.Reducer.sum(), geometry=ee_geom, scale=30, maxPixels=1e10
    ).getInfo()

    # Imagen de pérdida para visualización en mapa
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
        glad = ee.ImageCollection("projects/glad/alert/UpdResult") \
            .filterBounds(ee_geom) \
            .select("alertDate25") \
            .mosaic()
        area_img = ee.Image.pixelArea().divide(10000)
        alert_mask = glad.gt(0)
        alert_area = area_img.updateMask(alert_mask).reduceRegion(
            reducer=ee.Reducer.sum(), geometry=ee_geom, scale=10, maxPixels=1e10
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
        jrc = ee.ImageCollection("projects/JRC/TMF/v1_2023/AnnualChanges") \
            .filterBounds(ee_geom).mosaic()
        area_img = ee.Image.pixelArea().divide(10000)

        # Por año 1990-2023
        by_year_defor = []
        by_year_degrad = []
        years = list(range(2015, 2024))
        for y in years:
            band = f"Dec{y}"
            b = jrc.select(band)
            defor_mask  = b.eq(3)
            degrad_mask = b.eq(2)
            da = area_img.updateMask(defor_mask).reduceRegion(
                reducer=ee.Reducer.sum(), geometry=ee_geom, scale=30, maxPixels=1e10
            ).getInfo()
            dga = area_img.updateMask(degrad_mask).reduceRegion(
                reducer=ee.Reducer.sum(), geometry=ee_geom, scale=30, maxPixels=1e10
            ).getInfo()
            dv  = list(da.values())[0]  if da  else 0
            dgv = list(dga.values())[0] if dga else 0
            if (dv or 0) > 0:
                by_year_defor.append({"year": y, "area_ha": round(dv or 0, 4)})
            if (dgv or 0) > 0:
                by_year_degrad.append({"year": y, "area_ha": round(dgv or 0, 4)})
            by_year_regrowth = []
            for y in years:
                band = f"Dec{y}"
                b = jrc.select(band)
                # ... código existente ...
                rg_mask = b.eq(4)  # clase 4 = regrowth
                rga = area_img.updateMask(rg_mask).reduceRegion(
                    reducer=ee.Reducer.sum(), geometry=ee_geom, scale=30, maxPixels=1e10
                ).getInfo()
                rgv = list(rga.values())[0] if rga else 0
                if (rgv or 0) > 0:
                    by_year_regrowth.append({"year": y, "area_ha": round(rgv or 0, 4)})

        # Totales con banda más reciente
        band_latest = jrc.select("Dec2023")
        defor_mask  = band_latest.eq(3)
        degrad_mask = band_latest.eq(2)
        defor_total = area_img.updateMask(defor_mask).reduceRegion(
            reducer=ee.Reducer.sum(), geometry=ee_geom, scale=30, maxPixels=1e10
        ).getInfo()
        degrad_total = area_img.updateMask(degrad_mask).reduceRegion(
            reducer=ee.Reducer.sum(), geometry=ee_geom, scale=30, maxPixels=1e10
        ).getInfo()

        return {
            "deforestation_ha": round(list(defor_total.values())[0]  or 0, 4),
            "degradation_ha":   round(list(degrad_total.values())[0] or 0, 4),
            "by_year_defor":    by_year_defor,
            "by_year_degrad":   by_year_degrad,
            "defor_image":  band_latest.updateMask(defor_mask),
            "degrad_image": band_latest.updateMask(degrad_mask),
            "by_year_regrowth": by_year_regrowth,
            "regrowth_ha": round(sum(r["area_ha"] for r in by_year_regrowth), 4),
        }
    except Exception as e:
        return {"deforestation_ha": 0, "degradation_ha": 0,
                "by_year_defor": [], "by_year_degrad": [],
                "defor_image": None, "degrad_image": None, "note": str(e)}

def analyze_jrc_amazon(polygon):
    ee_geom = polygon_to_ee(polygon)
    try:
        jrc = ee.ImageCollection("projects/JRC/TMF/v1_2023/AnnualChanges") \
            .filterBounds(ee_geom) \
            .mosaic()
        area_img = ee.Image.pixelArea().divide(10000)
        band = jrc.select("Dec2023")
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
                reducer=ee.Reducer.sum(), geometry=ee_geom, scale=30, maxPixels=1e10
            ).getInfo()
            val = list(area.values())[0] if area else 0
            results[name] = round(val or 0, 4)
        return results
    except Exception as e:
        return {"undisturbed_ha": 0, "degraded_ha": 0,
                "deforested_ha": 0, "regrowth_ha": 0, "note": str(e)}

def analyze_firms(polygon):
    ee_geom = polygon_to_ee(polygon)
    try:
        area_img = ee.Image.pixelArea().divide(10000)
        by_year = []
        for y in range(2015, 2024):
            firms = ee.ImageCollection("FIRMS") \
                .filterBounds(ee_geom) \
                .filterDate(f"{y}-01-01", f"{y}-12-31") \
                .select("T21").mosaic()
            fire_mask = firms.gt(300)
            fire_area = area_img.updateMask(fire_mask).reduceRegion(
                reducer=ee.Reducer.sum(), geometry=ee_geom, scale=1000, maxPixels=1e10
            ).getInfo()
            val = list(fire_area.values())[0] if fire_area else 0
            if (val or 0) > 0:
                by_year.append({"year": y, "area_ha": round(val or 0, 4)})

        total = sum(r["area_ha"] for r in by_year)
        firms_full = ee.ImageCollection("FIRMS") \
            .filterBounds(ee_geom) \
            .filterDate("2015-01-01", "2024-12-31") \
            .select("T21").mosaic()
        fire_img = firms_full.updateMask(firms_full.gt(300))
        return {"fire_area_ha": round(total, 4), "by_year": by_year, "fire_image": fire_img}
    except Exception as e:
        return {"fire_area_ha": 0, "by_year": [], "fire_image": None, "note": str(e)}

def analyze_modis_burn(polygon):
    ee_geom = polygon_to_ee(polygon)
    try:
        area_img = ee.Image.pixelArea().divide(10000)
        by_year = []
        for y in range(2015, 2024):
            modis = ee.ImageCollection("MODIS/061/MCD64A1") \
                .filterBounds(ee_geom) \
                .filterDate(f"{y}-01-01", f"{y}-12-31") \
                .select("BurnDate").mosaic()
            burn_mask = modis.gt(0)
            burn_area = area_img.updateMask(burn_mask).reduceRegion(
                reducer=ee.Reducer.sum(), geometry=ee_geom, scale=500, maxPixels=1e10
            ).getInfo()
            val = list(burn_area.values())[0] if burn_area else 0
            if (val or 0) > 0:
                by_year.append({"year": y, "area_ha": round(val or 0, 4)})

        total = sum(r["area_ha"] for r in by_year)
        modis_full = ee.ImageCollection("MODIS/061/MCD64A1") \
            .filterBounds(ee_geom) \
            .filterDate("2015-01-01", "2024-12-31") \
            .select("BurnDate").mosaic()
        burn_img = modis_full.updateMask(modis_full.gt(0))
        return {"burn_area_ha": round(total, 4), "by_year": by_year, "burn_image": burn_img}
    except Exception as e:
        return {"burn_area_ha": 0, "by_year": [], "burn_image": None, "note": str(e)}


def get_tile_url(image, vis_params):
    try:
        map_id = image.getMapId(vis_params)
        return map_id['tile_fetcher'].url_format
    except:
        return None