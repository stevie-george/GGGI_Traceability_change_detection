"""
validate_2016.py — valida la PoC del mapa 2016 y adelanta la detección de cambio.

(1) RECALL del aguacate 2016: de los polígonos de aguacate verificados de 2016
    (muestra_aguacate_2016 + SEMADET año 2016), ¿qué fracción clasifica el mapa 2016
    como aguacate (clase 5)? -> dice si el modelo 2025 transfiere a 2016.
(2) Cambio 2016 vs 2025: hectáreas de aguacate en los mismos tiles (esperado: 2016 < 2025).

    run_producer.bat validate_2016.py
Lee maps_2016/ (clase 2016) y maps_manual_sin_inegi/ (clase 2025). No necesita F:.
"""
from pathlib import Path
import numpy as np
import pandas as pd
import geopandas as gpd
import rasterio
from rasterio.features import rasterize

HERE = Path(__file__).resolve().parent
GEO = Path(r"C:\Users\StephaniePatriciaGeo\OneDrive - Global Green Growth Institute\Documents\MX40\Geoespacial_compartida")
MAPS_2016 = HERE / "maps_2016"
MAPS_2025 = HERE / "maps_manual_sin_inegi"
TILES = ["r004c011", "r003c011", "r004c010", "r005c013"]
AVO = 5                       # id agrupado del aguacate
HA_PER_PX = (10 * 10) / 1e4   # 10 m -> 0.01 ha/píxel


def load_ref_2016():
    m16 = gpd.read_file(GEO / "Muestras/muestra_aguacate_2016.gpkg")[["geometry"]]
    sem = gpd.read_file(GEO / "Muestras/SEMADET/Aguacate.gpkg")
    sem16 = sem[sem["Anio"].astype(str).str.strip() == "2016"][["geometry"]].to_crs(m16.crs)
    ref = pd.concat([m16, sem16], ignore_index=True)
    return gpd.GeoDataFrame(ref, geometry="geometry", crs=m16.crs)


def main():
    if not MAPS_2016.exists():
        raise SystemExit("no existe maps_2016/ — corre primero: infer.py --in-dir out_2016 --version 2016 ...")
    ref = load_ref_2016()
    tot_hit = tot_ref = 0
    print(f"{'tile':10s} {'px_ref':>8} {'recall_avo_2016':>16} {'ha_avo_2016':>12} {'ha_avo_2025':>12}")
    print("-" * 64)
    for t in TILES:
        c16p = MAPS_2016 / f"{t}_class.tif"
        if not c16p.exists():
            print(f"{t:10s}  (sin mapa 2016, omito)"); continue
        with rasterio.open(c16p) as s:
            cls16 = s.read(1); crs, tr, H, W = s.crs, s.transform, s.height, s.width
        g = ref.to_crs(crs)
        mask = rasterize([(geom, 1) for geom in g.geometry], out_shape=(H, W),
                         transform=tr, fill=0, dtype="uint8").astype(bool)
        nref = int(mask.sum())
        hit = int((cls16[mask] == AVO).sum()) if nref else 0
        tot_hit += hit; tot_ref += nref
        ha16 = float((cls16 == AVO).sum()) * HA_PER_PX
        ha25 = float("nan")
        c25p = MAPS_2025 / f"{t}_class.tif"
        if c25p.exists():
            with rasterio.open(c25p) as s:
                ha25 = float((s.read(1) == AVO).sum()) * HA_PER_PX
        rec = f"{hit/nref:.3f}" if nref else "s/ref"
        print(f"{t:10s} {nref:>8} {rec:>16} {ha16:>12.1f} {ha25:>12.1f}")
    print("-" * 64)
    if tot_ref:
        print(f"\nRECALL GLOBAL del aguacate 2016 (vs referencia verificada): "
              f"{tot_hit/tot_ref:.3f}  ({tot_hit:,}/{tot_ref:,} px)")
        print("(= de las huertas de aguacate confirmadas en 2016, qué fracción detecta el mapa 2016)")


if __name__ == "__main__":
    main()
