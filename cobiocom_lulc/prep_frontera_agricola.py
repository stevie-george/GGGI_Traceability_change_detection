"""
prep_frontera_agricola.py — Frontera Agrícola (SIAP/INEGI Serie IV, Jalisco) como fuente
de AGRICULTURA (class_id=9 -> grupo 13), EXCLUYENDO un buffer alrededor de todo el
aguacate y agave (para no contaminar esas clases estrella). Captura parcelas pelonas/en
barbecho que hoy caen en urbano/agave.
Salida: frontera_agricola.gpkg (capa 'labels', EPSG:6372).
"""
import io
import zipfile
from pathlib import Path
import pandas as pd
import geopandas as gpd

HERE = Path(__file__).resolve().parent
GEO = Path(r"C:\Users\StephaniePatriciaGeo\OneDrive - Global Green Growth Institute\Documents\MX40\Geoespacial_compartida")
SCR = Path(r"C:\Users\STEPHA~1\AppData\Local\Temp\claude\C--Users-StephaniePatriciaGeo-Documents-deforestation-alert\0bc1a772-ac32-430d-94f8-b72814ba6d9c\scratchpad\frontera_jal")
CRS = "EPSG:6372"
BUFFER_M = 200
N_SUB = 2000      # menos polígonos -> menos sobre-predicción de agricultura

# --- extraer el shp de Jalisco del zip anidado ---
SCR.mkdir(parents=True, exist_ok=True)
with zipfile.ZipFile(GEO / "Descargas_datos_clasificacion/FronteraAgricola_SIV.zip") as zf:
    data = zf.read("Jalisco_Serie_IV.zip")
with zipfile.ZipFile(io.BytesIO(data)) as iz:
    iz.extractall(SCR)
shp = list(SCR.rglob("*.shp"))[0]
fa = gpd.read_file(shp).to_crs(CRS)
print(f"Frontera Agrícola Jalisco SIV: {len(fa):,} polígonos")

# --- exclusión: buffer de aguacate + agave (de labels_merged) + verificadas 2022 ---
lab = gpd.read_file(HERE / "labels_merged.gpkg", layer="labels")
avoag = lab[lab["class_id"].isin([5, 6])][["geometry"]].to_crs(CRS)
ver = gpd.read_file(GEO / "Shapes_referencia/Aguacate/Aguacate_Huertas_Verificadas_2022.gpkg")[["geometry"]].to_crs(CRS)
excl = gpd.GeoDataFrame(geometry=pd.concat([avoag.geometry, ver.geometry], ignore_index=True).buffer(BUFFER_M), crs=CRS)
print(f"máscara de exclusión: {len(excl):,} polígonos de aguacate/agave con buffer {BUFFER_M} m")

reps = gpd.GeoDataFrame(geometry=fa.representative_point(), crs=CRS)
reps["ix"] = range(len(fa))
hit = gpd.sjoin(reps, excl, predicate="within", how="inner")["ix"].unique()
fa_keep = fa.iloc[[i for i in range(len(fa)) if i not in set(hit)]]
print(f"excluidos por buffer aguacate/agave: {len(hit):,} | quedan: {len(fa_keep):,}")

# --- submuestreo y guardado ---
fa_keep = fa_keep.sample(n=min(N_SUB, len(fa_keep)), random_state=0)[["geometry"]].reset_index(drop=True)
fa_keep["class_id"] = 9                       # Agricultura anual -> grupo 13
fa_keep["source"] = "FronteraAgricola_SIV"
out = HERE / "frontera_agricola.gpkg"
fa_keep.to_file(out, layer="labels", driver="GPKG")
print(f"\n{len(fa_keep):,} polígonos de agricultura (Frontera, submuestreo) -> {out.name}  [class_id=9]")
