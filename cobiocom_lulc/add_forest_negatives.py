"""
add_forest_negatives.py — completa la tabla de entrenamiento con las clases que a
las etiquetas de los consultores les faltan (bosque, matorral, pastizal, cultivo
anual), muestreadas de ESA WorldCover 2021 (10 m) desde Planetary Computer y con
los MISMOS 34 predictores del stack.

Por qué: el aguacate es dosel perenne verde; su confusión #1 es el bosque, también
verde y perenne. Si no hay negativos "verdes", el RF marca aguacate en todo dosel.

Cuidados incorporados:
  * se EXCLUYE un búfer (BUFFER_M) alrededor de CUALQUIER aguacate etiquetado, para
    no rotular huertas como bosque/cultivo.
  * el dosel arbóreo (WorldCover=10) se SEPARA con la banda dNDVI en:
      - bosque templado perennifolio  (dNDVI bajo  -> id 1)
      - selva baja caducifolia        (dNDVI alto  -> id 2)
    tal como lo define legend.csv ("selva baja: verde en lluvias, café en secas").
  * los negativos se toman de los MISMOS tiles que ya tienen aguacate etiquetado,
    para que compartan atmósfera/fenología con los positivos.

Caveat: WorldCover puede mapear huertas de aguacate no etiquetadas como "tree cover"
o "cropland"; el búfer reduce pero no elimina esa fuga. La validación independiente
(Collect Earth/Olofsson) la vigila; si el RF confunde, subir BUFFER_M o afinar.

    run_producer.bat add_forest_negatives.py
    run_producer.bat add_forest_negatives.py --per-class 400 --limit 3   # prueba rápida

Requiere internet (STAC) + SSD (features.tif). Salidas:
    samples_worldcover.parquet   (solo los negativos auto de WorldCover)
    training_table.parquet       (samples.parquet + worldcover -> lo que lee train.py)
"""
import argparse
import csv
from pathlib import Path

import numpy as np
import pandas as pd
import geopandas as gpd
import rasterio
from rasterio.warp import transform_bounds
from rasterio.features import geometry_mask
import pystac_client
import planetary_computer as pc
from odc.stac import load as odc_load

from s2_export import CATALOG, OUT_CRS, RES

HERE = Path(__file__).resolve().parent
OUT = HERE / "out"
LABELS = HERE / "labels_merged.gpkg"
WC_COLLECTION = "esa-worldcover"

# --- mapeo ESA WorldCover -> class_id COBIOCOM --------------------------------
WC_TREE = 10                       # dosel arbóreo: se separa por dNDVI (ver abajo)
WC_MAP = {20: 3, 30: 4, 40: 9}     # matorral->3, pastizal->4, cultivo anual->9
TREE_EVERGREEN_ID = 1              # bosque templado perennifolio  (dNDVI bajo)
TREE_DECIDUOUS_ID = 2              # selva baja caducifolia         (dNDVI alto)
DNDVI_SPLIT = 0.15                 # umbral de caducifolia
BUFFER_M = 150                     # excluir a esta distancia de cualquier aguacate

# class_id -> name_en (legend.csv)
ID2NAME = {}
with open(HERE / "legend.csv", encoding="utf-8") as f:
    for r in csv.DictReader(f):
        ID2NAME[int(r["class_id"])] = r["name_en"]


def band_names(tile):
    f = OUT / tile / f"{tile}_bands.txt"
    return [ln.split("\t")[1] for ln in f.read_text(encoding="utf-8").splitlines() if "\t" in ln]


def worldcover_map(catalog, b4326):
    """Mapa WorldCover (uint8) reproyectado a EPSG:6372, 10 m, para el bbox del tile."""
    items = list(catalog.search(collections=[WC_COLLECTION], bbox=b4326).items())
    if not items:
        return None
    # los items de WorldCover traen datetime=None (usan start_datetime); rellenar
    for it in items:
        if it.datetime is None:
            sd = it.properties.get("start_datetime")
            it.datetime = (pd.Timestamp(sd) if sd else pd.Timestamp("2021-01-01")).to_pydatetime()
    y21 = [it for it in items if it.datetime.year == 2021]   # 2021 v200 (no 2020 v100)
    items = y21 or items
    ds = odc_load(items, bands=["map"], crs=OUT_CRS, resolution=RES, bbox=b4326,
                  resampling="nearest", dtype="uint8", nodata=0, fail_on_error=False)
    wc = ds["map"]
    if "time" in wc.dims:              # mosaicar sub-teselas espaciales (nodata=0 -> max recupera la clase)
        wc = wc.max("time")
    return wc


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--per-class", type=int, default=500,
                    help="máx. píxeles por clase y por tile (default 500)")
    ap.add_argument("--limit", type=int, default=None,
                    help="procesar solo los primeros N tiles (prueba)")
    args = ap.parse_args()

    lab = gpd.read_file(LABELS, layer="labels").to_crs(OUT_CRS)
    avo = lab[lab["class_name"].str.contains("vocado", case=False, na=False)].copy()
    avo["geometry"] = avo.geometry.buffer(BUFFER_M)
    avo_geoms = list(avo.geometry.values)
    tiles = sorted(lab["tile_id"].dropna().unique())
    if args.limit:
        tiles = tiles[:args.limit]
    print(f"tiles a muestrear: {len(tiles)} | búfer aguacate: {BUFFER_M} m | "
          f"máx/clase/tile: {args.per_class}")

    catalog = pystac_client.Client.open(CATALOG, modifier=pc.sign_inplace)
    rng = np.random.default_rng(0)
    frames, n_no_feat, n_no_wc = [], 0, 0

    for i, tid in enumerate(tiles, 1):
        feat = OUT / tid / f"{tid}_features.tif"
        if not feat.exists():
            n_no_feat += 1; continue
        with rasterio.open(feat) as src:
            b4326 = list(transform_bounds(src.crs, "EPSG:4326", *src.bounds))
            L, B, R, T = src.bounds
            names = band_names(tid)
            di = names.index("dNDVI")

            wc = worldcover_map(catalog, b4326)
            if wc is None:
                n_no_wc += 1; continue
            wcv = np.asarray(wc.values)
            xs, ys = wc["x"].values, wc["y"].values
            transform = wc.rio.transform()
            avomask = geometry_mask(avo_geoms, out_shape=wcv.shape,
                                    transform=transform, invert=True)  # True = aguacate

            # picks: lista de (x, y, tag)  tag = class_id fijo o "TREE"
            picks = []
            def take(val, tag, n):
                sel = (wcv == val) & (~avomask)
                rr, cc = np.where(sel)
                if len(rr) == 0:
                    return
                if len(rr) > n:
                    k = rng.choice(len(rr), n, replace=False); rr, cc = rr[k], cc[k]
                picks.extend((xs[c], ys[r], tag) for r, c in zip(rr, cc))

            take(WC_TREE, "TREE", args.per_class)
            for val, cid in WC_MAP.items():
                take(val, cid, args.per_class)

            inb = [(x, y, t) for (x, y, t) in picks if L <= x <= R and B <= y <= T]
            if not inb:
                continue
            vals = np.array(list(src.sample([(x, y) for (x, y, _) in inb])), dtype="float32")

        df = pd.DataFrame(vals, columns=names)
        df["tag"] = [t for (_, _, t) in inb]
        df = df.dropna(subset=names).reset_index(drop=True)     # descartar huecos
        if df.empty:
            continue
        is_tree = df["tag"] == "TREE"
        df["class_id"] = df["tag"]
        df.loc[is_tree, "class_id"] = np.where(
            df.loc[is_tree, "dNDVI"] > DNDVI_SPLIT, TREE_DECIDUOUS_ID, TREE_EVERGREEN_ID)
        df["class_id"] = df["class_id"].astype(int)
        df["class_name"] = df["class_id"].map(ID2NAME)
        df["src_file"] = "esa_worldcover"
        df["tile_id"] = tid
        df["is_avocado"] = 0
        frames.append(df.drop(columns="tag"))
        print(f"  [{i}/{len(tiles)}] {tid}: +{len(df)} px")

    if not frames:
        print("sin negativos generados (¿STAC/SSD?)"); return
    wc_tab = pd.concat(frames, ignore_index=True)
    wc_tab.to_parquet(HERE / "samples_worldcover.parquet")

    print(f"\ntiles sin features: {n_no_feat} | sin WorldCover: {n_no_wc}")
    print(f"NEGATIVOS WorldCover: {len(wc_tab)} px  ->  samples_worldcover.parquet")
    print("\npor clase (nuevos negativos):\n" +
          wc_tab.groupby("class_name").size().sort_values(ascending=False).to_string())

    # tabla combinada = etiquetas humanas + negativos WorldCover
    hum = pd.read_parquet(HERE / "samples.parquet")
    full = pd.concat([hum, wc_tab], ignore_index=True)
    full.to_parquet(HERE / "training_table.parquet")
    print(f"\n===== TABLA DE ENTRENAMIENTO -> training_table.parquet ({len(full)} px) =====")
    print(full.groupby("class_name").size().sort_values(ascending=False).to_string())
    print(f"\nBINARIO -> aguacate: {int(full['is_avocado'].sum())} px | "
          f"no-aguacate: {int((full['is_avocado'] == 0).sum())} px")


if __name__ == "__main__":
    main()
