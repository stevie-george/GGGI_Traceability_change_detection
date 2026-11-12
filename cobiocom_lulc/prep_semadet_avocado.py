"""
prep_semadet_avocado.py — une el aguacate de SEMADET (Aguacate.gpkg) + muestras 2025
en un gpkg con class_id=5, listo para SOURCES en merge_labels.py.
NO incluye Aguacate_Huertas_Verificadas_2022 (se reserva como TEST independiente).
Salida: semadet_avocado.gpkg (capa 'labels', EPSG:6372).
"""
from pathlib import Path
import pandas as pd
import geopandas as gpd

HERE = Path(__file__).resolve().parent
MU = Path(r"C:\Users\StephaniePatriciaGeo\OneDrive - Global Green Growth Institute\Documents\MX40\Geoespacial_compartida\Muestras")
MIN_YEAR = 2018       # solo huertas recientes (las viejas pudieron cambiar -> bajaban la precisión)
N_SEM = 1500          # submuestreo de SEMADET para no aplastar al aguacate de consultores

# SEMADET: filtrar por año reciente + submuestrear
sem = gpd.read_file(MU / "SEMADET" / "Aguacate.gpkg")
sem["yr"] = pd.to_numeric(sem["Anio"], errors="coerce")
sem = sem[sem["yr"] >= MIN_YEAR].to_crs("EPSG:6372")[["geometry"]]
print(f"SEMADET Aguacate (año >= {MIN_YEAR}): {len(sem)} polígonos")
if len(sem) > N_SEM:
    sem = sem.sample(n=N_SEM, random_state=0)
sem["source"] = f"SEMADET_>={MIN_YEAR}"

# muestras 2025: todas (lo más reciente)
m25 = gpd.read_file(MU / "muestras_aguacate2025.gpkg").to_crs("EPSG:6372")[["geometry"]]
m25["source"] = "muestras_2025"
print(f"muestras 2025: {len(m25)} polígonos")

g = gpd.GeoDataFrame(pd.concat([sem, m25], ignore_index=True), geometry="geometry", crs="EPSG:6372")
g["class_id"] = 5                       # Aguacate
out = HERE / "semadet_avocado.gpkg"
g.to_file(out, layer="labels", driver="GPKG")
print(f"\n{len(g)} polígonos de aguacate (SEMADET reciente + 2025) -> {out.name}  [class_id=5, EPSG:6372]")
print("(Verificadas_2022 NO incluido: es el test independiente)")
