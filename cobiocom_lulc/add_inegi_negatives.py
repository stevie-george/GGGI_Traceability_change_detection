"""
add_inegi_negatives.py — negativos (clases generales) desde INEGI Serie VII (USV),
con los MISMOS 34 predictores del stack. Reemplaza a los negativos de WorldCover:
INEGI trae semántica de fotointérprete (pastizal/matorral/bosque/selva/agricultura
separados de verdad), así el RF sí distingue esas clases y no solo "verde/no-verde".

Crosswalk DESCRIPCIO -> class_id (legend.csv), con dos criterios:
  * la "AGRICULTURA PERMANENTE" (huertos perennes) se EXCLUYE: INEGI no separa
    aguacate de otros perennes, y usarla como negativo inyectaría aguacate real en
    una clase no-aguacate. El aguacate/otro-perenne quedan 100% en los consultores.
  * la "VEGETACIÓN SECUNDARIA ... DE X" se mapea por su formación MADRE (secundaria
    de bosque -> bosque; de selva -> selva), no a matorral (matorral = solo matorral
    xerófilo real), respetando la leyenda.
  * se excluye un búfer alrededor de cualquier aguacate etiquetado.

    run_producer.bat add_inegi_negatives.py
    run_producer.bat add_inegi_negatives.py --per-class 400 --limit 3   # prueba

Vector local (sin STAC) + SSD. Salidas:
    samples_inegi.parquet     (solo negativos INEGI)
    training_table.parquet    (samples.parquet humanas + INEGI -> lo que lee train.py)
"""
import argparse
import csv
import re
import unicodedata
from pathlib import Path

import numpy as np
import pandas as pd
import geopandas as gpd
import rasterio
from rasterio.features import rasterize, geometry_mask

from s2_export import OUT_CRS

HERE = Path(__file__).resolve().parent
OUT = HERE / "out"
LABELS = HERE / "labels_merged.gpkg"
INEGI = (Path(r"C:\Users\StephaniePatriciaGeo\OneDrive - Global Green Growth Institute")
         / "Documents/MX40/Geoespacial_compartida/Shapes_Mau/Shapefiles_Compilados"
         / "02_Cobertura_de_suelo/ID3_usv250s7gw_aoi.gpkg")
BUFFER_M = 150
DEM_BANDS = ["elevation", "slope"]   # se concatenan si existe <tile>_dem.tif

ID2NAME = {}
with open(HERE / "legend.csv", encoding="utf-8") as f:
    for r in csv.DictReader(f):
        ID2NAME[int(r["class_id"])] = r["name_en"]


def _norm(s):
    s = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode().upper()
    return re.sub(r"\s+", " ", s).strip()


def to_class_id(desc):
    """INEGI DESCRIPCIO -> class_id COBIOCOM (None = no usar como negativo)."""
    d = _norm(desc)
    d = re.sub(r"^VEGETACION SECUNDARIA (ARBOREA|ARBUSTIVA|HERBACEA) DE ", "", d)
    if d.startswith("AGRICULTURA"):
        if "SEMIPERMANENTE" in d:       # caña/forraje -> anual
            return 9
        if "PERMANENTE" in d:           # huerto perenne -> EXCLUIR (riesgo aguacate)
            return None
        return 9                        # anual / temporal / riego anual / humedad
    if any(k in d for k in ("CUERPO DE AGUA", "ACUICOLA", "TULAR", "POPAL")):
        return 12
    if any(k in d for k in ("MANGLAR", "DUNA", "GALERIA", "HALOFILA HIDROFILA")):
        return None                     # costero/ripario/humedal -> fuera
    if "ASENTAMIENTOS" in d or "URBAN" in d:
        return 10
    if "DESPROVISTO" in d or "SIN VEGETACION" in d:
        return 11
    if "PASTIZAL" in d or "SABANOIDE" in d or "PRADERA" in d:
        return 4
    if "MATORRAL" in d or "MEZQUITAL" in d or "MEZQUITE" in d or "CHAPARRAL" in d:
        return 3
    if "SELVA" in d:
        return 2
    if "BOSQUE" in d:
        return 1
    return None                         # palmar, halofila xerofila, etc. -> fuera


def band_names(tile):
    f = OUT / tile / f"{tile}_bands.txt"
    return [ln.split("\t")[1] for ln in f.read_text(encoding="utf-8").splitlines() if "\t" in ln]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--per-class", type=int, default=500)
    ap.add_argument("--limit", type=int, default=None)
    args = ap.parse_args()

    lab = gpd.read_file(LABELS, layer="labels").to_crs(OUT_CRS)
    avo = lab[lab["class_name"].str.contains("vocado", case=False, na=False)].copy()
    avo["geometry"] = avo.geometry.buffer(BUFFER_M)
    avo_geoms = list(avo.geometry.values)
    tiles = sorted(lab["tile_id"].dropna().unique())
    if args.limit:
        tiles = tiles[:args.limit]

    print(f"cargando INEGI Serie VII: {INEGI.name} ...")
    usv = gpd.read_file(INEGI).to_crs(OUT_CRS)
    usv["class_id"] = usv["DESCRIPCIO"].map(to_class_id)
    usv = usv[usv["class_id"].notna()].copy()
    usv["class_id"] = usv["class_id"].astype(int)
    print(f"  polígonos INEGI usables: {len(usv):,} | tiles: {len(tiles)} | "
          f"búfer aguacate: {BUFFER_M} m | máx/clase/tile: {args.per_class}")
    print("  crosswalk -> " + ", ".join(f"{ID2NAME[c]}:{n}"
          for c, n in usv["class_id"].value_counts().sort_index().items()))

    rng = np.random.default_rng(0)
    frames, n_no_feat = [], 0

    for i, tid in enumerate(tiles, 1):
        feat = OUT / tid / f"{tid}_features.tif"
        if not feat.exists():
            n_no_feat += 1; continue
        with rasterio.open(feat) as src:
            names = band_names(tid) + DEM_BANDS
            transform, (H, W) = src.transform, (src.height, src.width)
            L, B, R, T = src.bounds
            sub = usv.cx[L:R, B:T]
            if sub.empty:
                continue
            cls = rasterize([(g, c) for g, c in zip(sub.geometry, sub["class_id"])],
                            out_shape=(H, W), transform=transform, fill=0, dtype="uint8")
            avom = geometry_mask(avo_geoms, out_shape=(H, W), transform=transform, invert=True)
            cls[avom] = 0
            if not cls.any():
                continue
            arr = src.read().astype("float32")          # (34, H, W) — una lectura secuencial
            dpath = OUT / tid / f"{tid}_dem.tif"
            if dpath.exists():
                with rasterio.open(dpath) as dsrc:
                    arr = np.concatenate([arr, dsrc.read().astype("float32")], axis=0)
            else:
                arr = np.concatenate([arr, np.full((len(DEM_BANDS), H, W), np.nan, "float32")], axis=0)

        rows_all, cols_all, cids = [], [], []
        for c in np.unique(cls[cls > 0]):
            rr, cc = np.where(cls == c)
            if len(rr) > args.per_class:
                k = rng.choice(len(rr), args.per_class, replace=False); rr, cc = rr[k], cc[k]
            rows_all.append(rr); cols_all.append(cc); cids.append(np.full(len(rr), c))
        rr = np.concatenate(rows_all); cc = np.concatenate(cols_all); cid = np.concatenate(cids)

        df = pd.DataFrame(arr[:, rr, cc].T, columns=names)
        df = df.assign(class_id=cid)
        df = df.dropna(subset=names).reset_index(drop=True)
        if df.empty:
            continue
        df["class_name"] = df["class_id"].map(ID2NAME)
        df["src_file"] = "inegi_svii"
        df["tile_id"] = tid
        df["is_avocado"] = 0
        frames.append(df)
        print(f"  [{i}/{len(tiles)}] {tid}: +{len(df)} px")

    if not frames:
        print("sin negativos generados"); return
    tab = pd.concat(frames, ignore_index=True)
    tab.to_parquet(HERE / "samples_inegi.parquet")

    print(f"\ntiles sin features: {n_no_feat}")
    print(f"NEGATIVOS INEGI: {len(tab):,} px  ->  samples_inegi.parquet")
    print("\npor clase (nuevos negativos):\n" +
          tab.groupby("class_name").size().sort_values(ascending=False).to_string())

    hum = pd.read_parquet(HERE / "samples.parquet")
    full = pd.concat([hum, tab], ignore_index=True)
    full.to_parquet(HERE / "training_table.parquet")
    print(f"\n===== TABLA DE ENTRENAMIENTO -> training_table.parquet ({len(full):,} px) =====")
    print(full.groupby("class_name").size().sort_values(ascending=False).to_string())
    print(f"\nBINARIO -> aguacate: {int(full['is_avocado'].sum()):,} px | "
          f"no-aguacate: {int((full['is_avocado'] == 0).sum()):,} px")


if __name__ == "__main__":
    main()
