"""
sample.py — MUESTREO (Fase 1). Extrae los 34 predictores del stack (features.tif)
bajo cada polígono etiquetado -> tabla de entrenamiento para el RandomForest.

Una fila por PÍXEL dentro de los polígonos:
    <34 predictores>  class_id  class_name  is_avocado  src_file  tile_id

    run_producer.bat sample.py                          # todas las etiquetas limpias
    run_producer.bat sample.py --consultants tona mau   # excluir Rodrigo (sin verificar)
    run_producer.bat sample.py --max-per-poly 300       # submuestrear píxeles por polígono

Requiere el SSD conectado (features.tif viven en out/ -> SSD). Salida: samples.parquet
"""
import argparse
from contextlib import nullcontext
from pathlib import Path
import numpy as np
import pandas as pd
import geopandas as gpd
import rasterio
from rasterio.features import geometry_mask
from rasterio.windows import from_bounds

HERE = Path(__file__).resolve().parent
OUT = HERE / "out"
LABELS = HERE / "labels_merged.gpkg"
DEM_BANDS = ["elevation", "slope"]   # se concatenan si existe <tile>_dem.tif


def band_names(tile):
    f = OUT / tile / f"{tile}_bands.txt"
    if f.exists():
        return [ln.split("\t")[1] for ln in f.read_text(encoding="utf-8").splitlines() if "\t" in ln]
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--consultants", nargs="*", default=None,
                    help="filtrar por src_file (p. ej. tona mau)")
    ap.add_argument("--max-per-poly", type=int, default=None,
                    help="máximo de píxeles por polígono (submuestreo)")
    args = ap.parse_args()

    lab = gpd.read_file(LABELS, layer="labels")
    if args.consultants:
        lab = lab[lab["src_file"].isin(args.consultants)]
    lab = lab[lab["tile_id"].notna()].reset_index(drop=True)
    print(f"polígonos a muestrear: {len(lab)} en {lab['tile_id'].nunique()} tiles")

    names, frames, n_missing, n_empty = None, [], 0, 0
    for tid, g in lab.groupby("tile_id"):
        fpath = OUT / tid / f"{tid}_features.tif"
        if not fpath.exists():
            n_missing += 1
            continue
        dpath = OUT / tid / f"{tid}_dem.tif"
        with rasterio.open(fpath) as src, \
                (rasterio.open(dpath) if dpath.exists() else nullcontext()) as dsrc:
            if names is None:
                names = (band_names(tid) or [f"b{i+1}" for i in range(src.count)]) + DEM_BANDS
            for _, row in g.iterrows():
                geom = row.geometry
                win = from_bounds(*geom.bounds, transform=src.transform).round_offsets().round_lengths()
                arr = src.read(window=win)
                if arr.size == 0:
                    n_empty += 1; continue
                dem = (dsrc.read(window=win) if dsrc is not None
                       else np.full((len(DEM_BANDS),) + arr.shape[1:], np.nan, "float32"))
                arr = np.concatenate([arr.astype("float32"), dem.astype("float32")], axis=0)
                wt = src.window_transform(win)
                mask = geometry_mask([geom], out_shape=arr.shape[1:], transform=wt, invert=True)
                yy, xx = np.where(mask)
                if len(yy) == 0:
                    n_empty += 1; continue
                if args.max_per_poly and len(yy) > args.max_per_poly:
                    sel = np.random.default_rng(0).choice(len(yy), args.max_per_poly, replace=False)
                    yy, xx = yy[sel], xx[sel]
                df = pd.DataFrame(arr[:, yy, xx].T, columns=names)
                df["class_id"] = int(row["class_id"])
                df["class_name"] = row["class_name"]
                df["src_file"] = row["src_file"]
                df["tile_id"] = tid
                frames.append(df)

    tab = pd.concat(frames, ignore_index=True).dropna(subset=names).reset_index(drop=True)
    tab["is_avocado"] = tab["class_name"].str.contains("vocado", case=False, na=False).astype(int)

    try:
        tab.to_parquet(HERE / "samples.parquet"); out = "samples.parquet"
    except Exception:
        tab.to_csv(HERE / "samples.csv", index=False); out = "samples.csv"

    print(f"\ntiles sin features: {n_missing} | polígonos vacíos: {n_empty}")
    print(f"MUESTRAS (píxeles): {len(tab)}  ->  {out}")
    print("\npor clase:\n" + tab.groupby("class_name").size().sort_values(ascending=False).to_string())
    print("\npor consultor:\n" + tab.groupby("src_file").size().to_string())
    print(f"\nBINARIO -> aguacate: {int(tab['is_avocado'].sum())} px | "
          f"no-aguacate: {int((tab['is_avocado'] == 0).sum())} px")


if __name__ == "__main__":
    main()
