"""
build_qgis_project.py — arma el proyecto QGIS de paisajes agrícolas semiáridos.
CÓMO USARLO: abre QGIS -> menú Complementos -> Consola de Python -> "Mostrar editor" ->
abre este archivo -> Ejecutar (▶). Genera 'mapa_semiarido.qgz' en esta carpeta, con:
basemap satelital + WorldCover + Frontera Agrícola (temporal/riego) + municipios + cuenca + ríos.
"""
import os
from qgis.core import (QgsProject, QgsVectorLayer, QgsRasterLayer, QgsCoordinateReferenceSystem,
                       QgsPalettedRasterRenderer, QgsRasterShader, QgsColorRampShader,
                       QgsCategorizedSymbolRenderer, QgsRendererCategory, QgsSymbol,
                       QgsSimpleFillSymbolLayer, QgsLineSymbol)
from qgis.PyQt.QtGui import QColor

HERE = r"C:\Users\StephaniePatriciaGeo\Documents\deforestation_alert\cobiocom_lulc"
proj = QgsProject.instance()
proj.clear()
proj.setCrs(QgsCoordinateReferenceSystem("EPSG:6372"))


def add_vec(gpkg, layer, name):
    v = QgsVectorLayer(f"{os.path.join(HERE, gpkg)}|layername={layer}", name, "ogr")
    if v.isValid():
        proj.addMapLayer(v)
    return v


# 1) basemap satelital (ESRI World Imagery, XYZ)
esri = ("type=xyz&zmin=0&zmax=19&url="
        "https://services.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/%7Bz%7D/%7By%7D/%7Bx%7D")
sat = QgsRasterLayer(esri, "Satélite (ESRI)", "wms")
if sat.isValid():
    proj.addMapLayer(sat)

# 2) WorldCover (paletteado)
wc = QgsRasterLayer(os.path.join(HERE, "worldcover_region.tif"), "WorldCover 2021")
WC = {10: ("#006400", "Bosque/árbol"), 20: ("#dec082", "Matorral"), 30: ("#fff096", "Pastizal"),
      40: ("#f096ff", "Agricultura (WorldCover)"), 50: ("#fa3c3c", "Urbano"),
      60: ("#beb4a5", "Suelo desnudo"), 80: ("#006ec8", "Agua"), 90: ("#0096a0", "Humedal")}
if wc.isValid():
    classes = [QgsPalettedRasterRenderer.Class(v, QColor(c), lab) for v, (c, lab) in WC.items()]
    wc.setRenderer(QgsPalettedRasterRenderer(wc.dataProvider(), 1, classes))
    wc.setOpacity(0.75)
    proj.addMapLayer(wc)

# 3) Frontera Agrícola (categorizado temporal/riego)
fa = QgsVectorLayer(f"{os.path.join(HERE, 'map_base.gpkg')}|layername=frontera_ag", "Frontera Agrícola", "ogr")
if fa.isValid():
    cats = []
    for val, col in [("Temporal", "#1b7a1b"), ("Riego", "#1b4dbf")]:
        sym = QgsSymbol.defaultSymbol(fa.geometryType())
        sym.setColor(QColor(col)); sym.setOpacity(0.55)
        cats.append(QgsRendererCategory(val, sym, val))
    fa.setRenderer(QgsCategorizedSymbolRenderer("tipo", cats))
    proj.addMapLayer(fa)

# 4) límites y contexto
for gpkg, lyr, name, color, width in [
    ("map_base.gpkg", "cuenca_laja", "Cuenca Río Laja", "#00695c", 0.8),
    ("map_base.gpkg", "rios", "Ríos", "#1565c0", 0.5),
    ("map_base.gpkg", "munis_altiplano", "Municipios (altiplano)", "#555555", 0.3),
    ("map_base.gpkg", "munis_named", "Regiones nombradas", "#d81b60", 0.8),
    ("map_base.gpkg", "estados", "Estados", "#000000", 0.8),
]:
    v = add_vec(gpkg, lyr, name)
    if v and v.isValid() and v.geometryType() != 0:
        sym = v.renderer().symbol()
        if "rios" in lyr:
            sym.setColor(QColor(color))
        else:  # polígonos -> solo contorno
            sym.changeSymbolLayer(0, QgsSimpleFillSymbolLayer(QColor(0, 0, 0, 0),
                                  strokeColor=QColor(color), strokeWidth=width))
        v.triggerRepaint()

out = os.path.join(HERE, "mapa_semiarido.qgz")
proj.write(out)
print("Proyecto guardado ->", out)
