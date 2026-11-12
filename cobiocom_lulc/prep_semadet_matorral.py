"""
prep_semadet_matorral.py — une los 3 KMZ de matorral de SEMADET en un gpkg con class_id=3,
listo para agregarse a SOURCES en merge_labels.py (matorral xerófilo limpio, validado).
Salida: semadet_matorral.gpkg (capa 'labels', EPSG:6372).
"""
from pathlib import Path
import pandas as pd
import geopandas as gpd

HERE = Path(__file__).resolve().parent
SEM = Path(r"C:\Users\StephaniePatriciaGeo\OneDrive - Global Green Growth Institute\Documents\MX40\Geoespacial_compartida\Muestras\SEMADET")
KMZ = ["Muestra-matorral.kmz", "muestras Matorral Mariela.kmz", "MuestrasMatorral.kmz"]

parts = [gpd.read_file(SEM / k)[["geometry"]].to_crs("EPSG:6372") for k in KMZ]
g = gpd.GeoDataFrame(pd.concat(parts, ignore_index=True), geometry="geometry", crs="EPSG:6372")
g["class_id"] = 3                       # Matorral xerófilo (leyenda)
g["source"] = "SEMADET_KMZ"
out = HERE / "semadet_matorral.gpkg"
g.to_file(out, layer="labels", driver="GPKG")
print(f"{len(g)} polígonos de matorral (SEMADET) -> {out.name}  [class_id=3, EPSG:6372]")
