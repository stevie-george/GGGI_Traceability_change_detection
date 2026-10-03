"""
make_qgis_project.py — assemble the QGIS labeling project (cobiocom_labeling.qgz).

Builds a ready-to-digitize project:
  · Basemaps      : Esri + Google Satellite/Hybrid + Esri Wayback (dated), all no-key;
                    plus optional Planet NICFI (needs PLANET_API_KEY)
  · S2 renders    : the per-tile TRUE/CIR/SWIR/NDVI/dNDVI COGs from s2_export.py (out/)
  · labels layer  : labels.gpkg, styled by legend.csv with a class-name dropdown

This uses PyQGIS, so run it INSIDE QGIS:
  · QGIS → Plugins → Python Console → paste this file (or `exec(open(r'.../make_qgis_project.py').read())`)
    then call  main()
  · or run standalone with the QGIS-bundled python (the __main__ block inits QgsApplication).

Re-run after generating more tiles with s2_export.py to fold them in (layers are baked
into the .qgz at build time). Set PLANET_API_KEY (and optionally NICFI_MOSAIC) to include NICFI.
"""
import os
import csv
from pathlib import Path

from qgis.core import (
    QgsProject, QgsRasterLayer, QgsVectorLayer, QgsCoordinateReferenceSystem,
    QgsCategorizedSymbolRenderer, QgsRendererCategory, QgsFillSymbol,
    QgsSingleSymbolRenderer, QgsEditorWidgetSetup, QgsDefaultValue,
)

# ------------------------------------------------------------------ config --
try:
    BASE = Path(__file__).resolve().parent
except NameError:                                    # pasted into the QGIS console
    BASE = Path(r"C:\Users\StephaniePatriciaGeo\Documents\deforestation_alert\cobiocom_lulc")

OUT_CRS   = "EPSG:6372"
LEGEND    = BASE / "legend.csv"
LABELS    = BASE / "labels.gpkg"
RENDERS   = BASE / "out"                              # s2_export.py output
PROJECT   = BASE / "cobiocom_labeling.qgz"
AOI_GPKG  = (r"C:\Users\StephaniePatriciaGeo\OneDrive - Global Green Growth "
             r"Institute\Documents\MX40\Geoespacial_compartida\Shapes_COBIOCOM\RecortesCOBIOCOM\EntidadesCOBIOCOM.gpkg")

ESRI_URL  = ("https://server.arcgisonline.com/ArcGIS/rest/services/"
             "World_Imagery/MapServer/tile/{z}/{y}/{x}")
GOOGLE_SAT = "https://mt1.google.com/vt/lyrs=s&x={x}&y={y}&z={z}"   # satellite
GOOGLE_HYB = "https://mt1.google.com/vt/lyrs=y&x={x}&y={y}&z={z}"   # satellite + labels/roads
# Esri Wayback: dated World Imagery snapshots (World Imagery as PUBLISHED on each date).
# A 2024 baseline + the S2 composite windows (green ~2025-11, dry ~2026-05) + latest.
WAYBACK = {"2024-12-12": "16453", "2025-11-20": "51127", "2026-05-28": "10842", "2026-08-05": "26334"}
NICFI_MOSAIC = os.environ.get("NICFI_MOSAIC", "planet_medres_visual_2024-06_mosaic")


# --------------------------------------------------------------- functions --
def _xyz(name, url, zmax=19):
    # Encode ONLY the chars that would break the "type=xyz&url=...&zmax=" URI (& = ?).
    # Keep ://, /, and {z}/{x}/{y} literal — this matches QGIS's own XYZ connections.
    u = url.replace("&", "%26").replace("=", "%3D").replace("?", "%3F")
    return QgsRasterLayer(f"type=xyz&url={u}&zmin=0&zmax={zmax}", name, "wms")


def _styled_labels():
    """labels.gpkg with a categorised style + class-name dropdown, from legend.csv."""
    v = QgsVectorLayer(f"{LABELS}|layername=labels", "labels (ROIs)", "ogr")
    if not v.isValid():
        raise RuntimeError(f"could not open {LABELS} — run make_qgis_assets.py first")

    cats, value_map = [], []
    with open(LEGEND, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            cid = int(row["class_id"])
            h = row["color_hex"].lstrip("#")
            rgb = f"{int(h[0:2],16)},{int(h[2:4],16)},{int(h[4:6],16)}"
            sym = QgsFillSymbol.createSimple({
                "color": f"{rgb},110",          # semi-transparent so imagery shows through
                "outline_color": "0,0,0,255",
                "outline_width": "0.3",
                "style": "solid",
            })
            lbl = f'{cid} · {row["name_en"]}'
            cats.append(QgsRendererCategory(cid, sym, lbl))
            value_map.append({lbl: str(cid)})

    v.setRenderer(QgsCategorizedSymbolRenderer("class_id", cats))
    fields = v.fields()
    v.setEditorWidgetSetup(fields.indexOf("class_id"),
                           QgsEditorWidgetSetup("ValueMap", {"map": value_map}))
    # defaults that speed up digitising
    for name, expr in [("set", "'train'"), ("source", "'basemap'"),
                       ("confidence", "2"),
                       ("date_labeled", "format_date(now(),'yyyy-MM-dd')")]:
        i = fields.indexOf(name)
        if i >= 0:
            v.setDefaultValueDefinition(i, QgsDefaultValue(expr))
    return v


def _add(proj, group, layer, visible=False):
    proj.addMapLayer(layer, False)
    node = group.addLayer(layer)
    node.setItemVisibilityChecked(visible)
    return node


def main():
    proj = QgsProject()                              # fresh project — don't touch open session
    proj.setCrs(QgsCoordinateReferenceSystem(OUT_CRS))
    proj.writeEntry("Paths", "/Absolute", False)     # relative paths -> portable / bundleable
    root = proj.layerTreeRoot()

    # 1) labels on top
    labels = _styled_labels()
    proj.addMapLayer(labels, False)
    root.insertLayer(0, labels)

    # 2) AOI outline for context (prefer the LOCAL copy so the project stays portable)
    aoi_local = BASE / "aoi.gpkg"
    aoi_path, aoi_layer = ((aoi_local, "aoi") if aoi_local.exists()
                           else (Path(AOI_GPKG), "EntidadesCOBIOCOM"))
    if aoi_path.exists():
        aoi = QgsVectorLayer(f"{aoi_path}|layername={aoi_layer}", "AOI", "ogr")
        if aoi.isValid():
            outline = QgsFillSymbol.createSimple({    # outline-only so imagery shows through
                "style": "no", "outline_color": "255,255,0,255", "outline_width": "0.5"})
            aoi.setRenderer(QgsSingleSymbolRenderer(outline))
            proj.addMapLayer(aoi, False)
            root.insertLayer(1, aoi)

    # 3) Sentinel-2 renders, grouped by tile
    n_rasters = 0
    rgroup = root.addGroup("Sentinel-2 renders")
    tiles = sorted(d for d in RENDERS.glob("*") if d.is_dir()) if RENDERS.exists() else []
    for td in tiles:
        tg = rgroup.addGroup(td.name)
        for season in ("dry", "green"):
            for r in ("SWIR", "CIR", "TRUE", "NDVI"):
                p = td / f"{td.name}_{season}_{r}.tif"
                if p.exists():
                    lyr = QgsRasterLayer(str(p), f"{season} {r}")
                    _add(proj, tg, lyr, visible=(season == "dry" and r == "SWIR"))
                    n_rasters += 1
        dd = td / f"{td.name}_dNDVI.tif"
        if dd.exists():
            _add(proj, tg, QgsRasterLayer(str(dd), "dNDVI"), visible=False)
            n_rasters += 1
    if n_rasters == 0:
        print("  [note] no render COGs found in out/ yet — run "
              "`python s2_export.py --states 14` then re-run this to fold them in.")

    # 4) basemaps at the bottom
    bgroup = root.addGroup("Basemaps")
    _add(proj, bgroup, _xyz("Esri World Imagery", ESRI_URL, 19), visible=False)  # off by default; tick when online
    _add(proj, bgroup, _xyz("Google Satellite", GOOGLE_SAT, 21), visible=False)
    _add(proj, bgroup, _xyz("Google Hybrid (labels)", GOOGLE_HYB, 21), visible=False)
    wb = bgroup.addGroup("Esri Wayback (dated)")     # World Imagery as published on each date
    for wdate, wver in WAYBACK.items():
        wurl = ("https://wayback.maptiles.arcgis.com/arcgis/rest/services/World_Imagery/"
                f"WMTS/1.0.0/default028mm/MapServer/tile/{wver}/{{z}}/{{y}}/{{x}}")
        _add(proj, wb, _xyz(f"Wayback {wdate}", wurl, 19), visible=False)
    key = os.environ.get("PLANET_API_KEY", "")
    if key:
        nicfi_url = (f"https://tiles.planet.com/basemaps/v1/planet-tiles/"
                     f"{NICFI_MOSAIC}/gmap/{{z}}/{{x}}/{{y}}.png?api_key={key}")
        _add(proj, bgroup, _xyz(f"Planet NICFI ({NICFI_MOSAIC})", nicfi_url, 18), visible=False)
    else:
        print("  [note] PLANET_API_KEY not set — NICFI basemap skipped "
              "(set it + optional NICFI_MOSAIC, then re-run).")

    proj.write(str(PROJECT))
    print(f"wrote {PROJECT}\n  {len(tiles)} tile group(s), {n_rasters} render layer(s), "
          f"labels styled from {LEGEND.name}")


if __name__ == "__main__":
    from qgis.core import QgsApplication
    if QgsApplication.instance() is not None:
        # already inside QGIS (e.g. exec'd in the Python Console) — just build
        main()
    else:
        # standalone execution with the QGIS-bundled python
        qgs = QgsApplication([], False)
        qgs.initQgis()
        try:
            main()
        finally:
            qgs.exitQgis()
