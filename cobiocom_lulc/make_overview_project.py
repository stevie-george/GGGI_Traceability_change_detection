"""
make_overview_project.py — proyecto QGIS de PANORAMA (no para etiquetar).

Carga, en una sola vista, el estado del proyecto:
  · Etiquetas de entrenamiento unidas (labels_merged.gpkg), coloreadas por clase
  · Referencia de aguacate (huertas verificadas 2022 + frontera PERSEA)
  · Los tiles Sentinel-2 ya generados (out/  ->  SSD)
  · El AOI y basemaps (Esri / Google)

Usa rutas ABSOLUTAS (es un proyecto local, no portable). Los tiles requieren el SSD
conectado como F:. Correr DENTRO de QGIS (Complementos -> Consola de Python):

    exec(open(r'C:\\Users\\StephaniePatriciaGeo\\Documents\\deforestation_alert\\cobiocom_lulc\\make_overview_project.py').read()); main()
"""
import csv
from pathlib import Path
from qgis.core import (
    QgsProject, QgsRasterLayer, QgsVectorLayer, QgsCoordinateReferenceSystem,
    QgsCategorizedSymbolRenderer, QgsRendererCategory, QgsFillSymbol,
    QgsSingleSymbolRenderer,
)

try:
    BASE = Path(__file__).resolve().parent
except NameError:
    BASE = Path(r"C:\Users\StephaniePatriciaGeo\Documents\deforestation_alert\cobiocom_lulc")

OUT_CRS  = "EPSG:6372"
LEGEND   = BASE / "legend.csv"
LABELS   = BASE / "labels_merged.gpkg"          # capa 'labels'
RENDERS  = BASE / "out"
PROJECT  = BASE / "cobiocom_overview.qgz"
GEO = Path(r"C:\Users\StephaniePatriciaGeo\OneDrive - Global Green Growth "
          r"Institute\Documents\MX40\Geoespacial_compartida")

REFERENCIA = {
    "Aguacate huertas verificadas 2022": GEO / r"Shapes_referencia\Aguacate\Aguacate_Huertas_Verificadas_2022.gpkg",
    "Aguacate huertas completas 2022":   GEO / r"Shapes_referencia\Aguacate\Aguacate_Huertas_Completas_2022.gpkg",
    "PERSEA frontera aguacate 2024":     GEO / r"Descargas_datos_clasificacion\PROYECTO PERSEA frontera_aguacate_shapefiles\frontera_aguacate_2024\aguacate_2024.shp",
}
ESRI = "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}"
GOOGLE = "https://mt1.google.com/vt/lyrs=s&x={x}&y={y}&z={z}"


def _xyz(name, url, zmax=19):
    u = url.replace("&", "%26").replace("=", "%3D").replace("?", "%3F")
    return QgsRasterLayer(f"type=xyz&url={u}&zmin=0&zmax={zmax}", name, "wms")


def _styled_labels():
    v = QgsVectorLayer(f"{LABELS}|layername=labels", "Etiquetas (entrenamiento)", "ogr")
    if not v.isValid():
        return None
    cats = []
    with open(LEGEND, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            cid = int(row["class_id"]); h = row["color_hex"].lstrip("#")
            rgb = f"{int(h[0:2],16)},{int(h[2:4],16)},{int(h[4:6],16)}"
            sym = QgsFillSymbol.createSimple({"color": f"{rgb},150",
                                              "outline_color": "0,0,0,255", "outline_width": "0.2"})
            cats.append(QgsRendererCategory(cid, sym, f'{cid} · {row["name_en"]}'))
    v.setRenderer(QgsCategorizedSymbolRenderer("class_id", cats))
    return v


def _outline(layer, rgb):
    layer.setRenderer(QgsSingleSymbolRenderer(QgsFillSymbol.createSimple(
        {"style": "no", "outline_color": rgb, "outline_width": "0.5"})))
    return layer


def main():
    proj = QgsProject()
    proj.setCrs(QgsCoordinateReferenceSystem(OUT_CRS))
    proj.writeEntry("Paths", "/Absolute", True)
    root = proj.layerTreeRoot()

    if LABELS.exists():
        lab = _styled_labels()
        if lab:
            proj.addMapLayer(lab, False); root.insertLayer(0, lab)

    aoi = BASE / "aoi.gpkg"
    if aoi.exists():
        a = QgsVectorLayer(f"{aoi}|layername=aoi", "AOI", "ogr")
        if a.isValid():
            proj.addMapLayer(_outline(a, "255,255,0,255"), False); root.insertLayer(1, a)

    gref = root.addGroup("Referencia aguacate")
    for name, f in REFERENCIA.items():
        if f.exists():
            r = QgsVectorLayer(str(f), name, "ogr")
            if r.isValid():
                proj.addMapLayer(_outline(r, "255,0,255,255"), False)
                gref.addLayer(r).setItemVisibilityChecked(False)

    n_r = 0
    gt = root.addGroup("Sentinel-2 renders")
    tiles = sorted(d for d in RENDERS.glob("*") if d.is_dir()) if RENDERS.exists() else []
    for td in tiles:
        tg = gt.addGroup(td.name)
        for season in ("dry", "green"):
            for rr in ("SWIR", "CIR", "TRUE"):
                p = td / f"{td.name}_{season}_{rr}.tif"
                if p.exists():
                    lyr = QgsRasterLayer(str(p), f"{season} {rr}")
                    proj.addMapLayer(lyr, False)
                    tg.addLayer(lyr).setItemVisibilityChecked(season == "dry" and rr == "SWIR")
                    n_r += 1

    gb = root.addGroup("Basemaps")
    for nm, url, z in [("Esri World Imagery", ESRI, 19), ("Google Satellite", GOOGLE, 21)]:
        b = _xyz(nm, url, z); proj.addMapLayer(b, False); gb.addLayer(b).setItemVisibilityChecked(False)

    proj.write(str(PROJECT))
    print(f"escrito {PROJECT.name}\n  {len(tiles)} tiles ({n_r} renders) + etiquetas + referencia + basemaps")


if __name__ == "__main__":
    from qgis.core import QgsApplication
    if QgsApplication.instance() is not None:
        main()
    else:
        qgs = QgsApplication([], False); qgs.initQgis()
        try:
            main()
        finally:
            qgs.exitQgis()
