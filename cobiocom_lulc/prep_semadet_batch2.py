"""
prep_semadet_batch2.py — consolida el batch SEMADET verificado 2025 (entregado 2026-11-10)
en una sola capa con class_id. Lee directo de los ZIP (reproducible). Usa SOLO los *_2025
(coinciden con el stack de features actual). SALTA aguacate (duplica muestras_aguacate2025
ya en el pipeline). Salida: semadet_verif_2025.gpkg (layer 'labels', EPSG:6372).
"""
import tempfile, zipfile, glob
from pathlib import Path
import pandas as pd, geopandas as gpd
from pyogrio import list_layers

HERE = Path(__file__).resolve().parent
SEM = Path(r"C:\Users\StephaniePatriciaGeo\OneDrive - Global Green Growth "
          r"Institute\Documents\MX40\Geoespacial_compartida\Muestras\SEMADET")

# patrón de ZIP -> (class_id, substring del gpkg 2025 a usar)
JOBS = [
    ("Matorral-*.zip",            3, "matorral_2025"),
    ("Muestras Bosque-*.zip",     1, "Bosque_verd_2025"),
    ("Selva-*.zip",               2, "selva_2025"),
    ("Muestras Pastizal-*.zip",   4, "pastizal_2025"),
    ("Muestras agave-*.zip",      6, "agave 2025"),
    ("Muestras Agricultura-*.zip",9, "TA_2025"),
    # aguacate OMITIDO: duplica muestras_aguacate2025 ya usado por prep_semadet_avocado.py
]

parts = []
for pat, cid, want in JOBS:
    zips = sorted(glob.glob(str(SEM / pat)))
    if not zips:
        print(f"[FALTA] {pat}"); continue
    with tempfile.TemporaryDirectory() as td:
        with zipfile.ZipFile(zips[0]) as zf:
            members = [m for m in zf.namelist() if m.endswith(".gpkg") and want in m]
            if not members:
                print(f"[sin 2025] {pat} (want '{want}')"); continue
            zf.extract(members[0], td)
            fp = Path(td) / members[0]
            lyr = list_layers(str(fp))[0][0]
            g = gpd.read_file(fp, layer=lyr).to_crs("EPSG:6372")
    g = g[["geometry"]].copy()
    g["class_id"] = cid
    g["source"] = "SEMADET_verif_2025"
    print(f"  class {cid}: {len(g):4d} polys  <- {Path(zips[0]).name}")
    parts.append(g)

out = gpd.GeoDataFrame(pd.concat(parts, ignore_index=True), crs="EPSG:6372")
dst = HERE / "semadet_verif_2025.gpkg"
out.to_file(dst, layer="labels", driver="GPKG")
print(f"\n{len(out)} polígonos verificados -> {dst.name}  [EPSG:6372]")
print(out.groupby("class_id").size().to_string())
