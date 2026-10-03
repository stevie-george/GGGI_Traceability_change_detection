"""
generate_validation.py — puntos de validación (muestreo aleatorio ESTRATIFICADO por
la clase del mapa RF) para subir a Collect Earth Online (CEO). El consultor
fotointerpreta cada punto SIN ver la predicción del modelo -> validación insesgada
estilo Olofsson et al. (2014).

Diseño:
  * estratos = las clases del mapa (maps/<tile>_class.tif).
  * asignación: piso mínimo por clase (para poder estimar la exactitud de clases
    raras) + el resto proporcional al área de cada clase.
  * un punto por parcela (PLOTID), aleatorio dentro del píxel, en EPSG:4326.

Salidas (validation/):
  ceo_plots.csv         LON,LAT,PLOTID  -> esto se sube a CEO (sin la clase, para no sesgar)
  validation_points.gpkg  puntos con PLOTID + clase del mapa (para QGIS / respaldo)
  strata_key.csv        PLOTID -> clase del mapa (LLAVE oculta; para la matriz de error)
  strata_weights.csv    peso Wi (proporción de área) por clase -> estimación por área
  README_validacion.md  pasos de subida a CEO + qué hará el consultor

    run_producer.bat generate_validation.py                 # 500 puntos, piso 30
    run_producer.bat generate_validation.py --n 800 --min-per-class 40
    run_producer.bat generate_validation.py --classes 5     # solo aguacate vs resto
"""
import argparse
import csv
from pathlib import Path

import numpy as np
import pandas as pd
import geopandas as gpd
import rasterio
from rasterio.warp import transform as warp_transform

HERE = Path(__file__).resolve().parent
MAPS = HERE / "maps"
VAL = HERE / "validation"

NAME = {}
with open(HERE / "legend.csv", encoding="utf-8") as f:
    for r in csv.DictReader(f):
        NAME[int(r["class_id"])] = r["name_es"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=130,
                    help="número de CENTROS de parcela (cada uno lleva grilla 5x5 en CEO)")
    ap.add_argument("--min-per-class", type=int, default=8, help="piso de parcelas por clase presente")
    ap.add_argument("--priority", nargs="*", type=int, default=[5, 6],
                    help="clases prioritarias con piso reforzado (default 5=aguacate 6=agave)")
    ap.add_argument("--priority-min", type=int, default=20, help="piso de parcelas para las prioritarias")
    ap.add_argument("--classes", nargs="*", type=int, default=None,
                    help="restringir a estos class_id (default: todas las presentes)")
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()
    rng = np.random.default_rng(args.seed)

    tiles = sorted(p.stem.replace("_class", "") for p in MAPS.glob("*_class.tif"))
    if not tiles:
        raise SystemExit("no hay maps/*_class.tif — corre infer.py primero")

    # --- pass 1: conteo de píxeles por clase + metadatos por tile ---
    counts = {}                      # class_id -> total px
    per_tile = {}                    # tile -> {class_id: px}
    meta = {}                        # tile -> (transform, crs)
    for t in tiles:
        with rasterio.open(MAPS / f"{t}_class.tif") as s:
            a = s.read(1); meta[t] = (s.transform, s.crs)
        bc = np.bincount(a.ravel())
        d = {int(c): int(bc[c]) for c in np.nonzero(bc)[0] if c != 0}
        per_tile[t] = d
        for c, n in d.items():
            counts[c] = counts.get(c, 0) + n

    present = sorted(counts)
    if args.classes:
        present = [c for c in present if c in args.classes]
    total_px = sum(counts[c] for c in present)

    # --- asignación: piso (reforzado en prioritarias) + proporcional al área ---
    prio = set(args.priority or [])
    floor = lambda c: min(args.priority_min if c in prio else args.min_per_class, counts[c])
    alloc = {c: floor(c) for c in present}
    remaining = args.n - sum(alloc.values())
    if remaining > 0:
        W = {c: counts[c] / total_px for c in present}
        extra = {c: remaining * W[c] for c in present}
        base = {c: int(np.floor(extra[c])) for c in present}
        for c in present:
            alloc[c] = min(alloc[c] + base[c], counts[c])
        # repartir el residuo por mayor parte fraccionaria
        left = args.n - sum(alloc.values())
        for c in sorted(present, key=lambda c: extra[c] - base[c], reverse=True):
            if left <= 0:
                break
            if alloc[c] < counts[c]:
                alloc[c] += 1; left -= 1

    # --- pass 2: muestreo por reservorio (uniforme dentro de cada estrato) ---
    ti = {t: i for i, t in enumerate(tiles)}
    res = {c: {"key": np.empty(0), "tile": np.empty(0, int),
               "row": np.empty(0, int), "col": np.empty(0, int)} for c in present}
    for t in tiles:
        want = [c for c in present if per_tile[t].get(c) and alloc[c] > 0]
        if not want:
            continue
        with rasterio.open(MAPS / f"{t}_class.tif") as s:
            a = s.read(1)
        for c in want:
            rr, cc = np.where(a == c)
            keys = rng.random(len(rr))
            R = res[c]
            k = np.concatenate([R["key"], keys])
            tt = np.concatenate([R["tile"], np.full(len(rr), ti[t])])
            ro = np.concatenate([R["row"], rr]); co = np.concatenate([R["col"], cc])
            if len(k) > alloc[c]:
                idx = np.argpartition(k, alloc[c])[:alloc[c]]
                k, tt, ro, co = k[idx], tt[idx], ro[idx], co[idx]
            res[c] = {"key": k, "tile": tt, "row": ro, "col": co}

    # --- coords -> lon/lat (aleatorio dentro del píxel) ---
    rows = []
    for c in present:
        R = res[c]
        for tix in np.unique(R["tile"]):
            m = R["tile"] == tix
            tr, crs = meta[tiles[tix]]
            xs = tr.c + (R["col"][m] + rng.random(m.sum())) * tr.a
            ys = tr.f + (R["row"][m] + rng.random(m.sum())) * tr.e
            lon, lat = warp_transform(crs, "EPSG:4326", xs.tolist(), ys.tolist())
            for lo, la in zip(lon, lat):
                rows.append({"lon": lo, "lat": la, "map_class_id": c,
                             "map_class": NAME[c], "tile_id": tiles[tix]})

    df = pd.DataFrame(rows).sample(frac=1, random_state=args.seed).reset_index(drop=True)
    df.insert(0, "PLOTID", np.arange(1, len(df) + 1))

    VAL.mkdir(exist_ok=True)
    df[["lon", "lat", "PLOTID"]].rename(columns={"lon": "LON", "lat": "LAT"}) \
        .to_csv(VAL / "ceo_plots.csv", index=False)
    df[["PLOTID", "map_class_id", "map_class", "tile_id"]] \
        .to_csv(VAL / "strata_key.csv", index=False)
    gpd.GeoDataFrame(df, geometry=gpd.points_from_xy(df.lon, df.lat), crs="EPSG:4326") \
        .to_file(VAL / "validation_points.gpkg", layer="validation", driver="GPKG")

    wdf = pd.DataFrame({"map_class_id": present,
                        "map_class": [NAME[c] for c in present],
                        "map_pixels": [counts[c] for c in present],
                        "Wi_area_prop": [counts[c] / total_px for c in present],
                        "n_muestra": [alloc[c] for c in present]})
    wdf.to_csv(VAL / "strata_weights.csv", index=False)

    (VAL / "README_validacion.md").write_text(
        "# Validación — Collect Earth Online (diseño de parcela 100×100 m, grilla 5×5)\n\n"
        f"- **{len(df)} CENTROS de parcela**, aleatorio estratificado por la clase del mapa RF. "
        "Cada centro se convierte en una parcela de 100×100 m con **25 puntos (grilla 5×5, ~25 m)** "
        "en CEO → muestreo por conglomerado (cluster).\n"
        "- `ceo_plots.csv` (LON,LAT,PLOTID) = los centros que se SUBEN a CEO — sin la clase, "
        "para que el fotointérprete no se sesgue.\n"
        "- `strata_key.csv` = LLAVE (PLOTID→clase del mapa en el centro); NO se comparte. El "
        "estrato definitivo de cada uno de los 25 puntos se re-extrae del ráster en el análisis.\n"
        "- `strata_weights.csv` = peso de área Wi por clase (Olofsson et al. 2014).\n\n"
        "## Subir a CEO\n"
        "1. Crear institución/proyecto en https://app.collect.earth\n"
        "2. Plot Design → **CSV** → `ceo_plots.csv`; **Plot shape = Square, 100 m**.\n"
        "3. Sample Design → **Gridded**, **5×5 (25 puntos)**.\n"
        "4. Survey Question: opción única con las **12 clases** de la leyenda (colores de "
        "legend.csv) + una opción **'Mixto/No seguro'**. Opcional: 2ª pregunta de confianza.\n"
        "5. Imágenes: alta resolución (Planet/Mapbox/Bing) **+ Sentinel-2 verde y secas** "
        "(fenología). El intérprete clasifica los 25 puntos de cada parcela. Exportar CSV al final.\n\n"
        "## Al terminar\n"
        "`olofsson_assess.py` cruza el CSV de CEO con la clase del mapa por punto → matriz de "
        "error + exactitud usuario/productor + área ajustada, con **varianza cluster-robusta** "
        "(las 25 muestras de una parcela están correlacionadas). Composición por parcela = % de "
        "cada clase en sus 25 puntos.\n",
        encoding="utf-8")

    print(f"MUESTRA: {len(df)} centros de parcela en {df['tile_id'].nunique()} tiles -> {VAL}/  "
          f"(cada uno = 100x100 m con grilla 5x5 = {len(df)*25} puntos a interpretar)")
    print("\nasignación de PARCELAS por clase:")
    print(wdf.assign(Wi_area_prop=wdf["Wi_area_prop"].round(3)).to_string(index=False))
    print("\narchivos: ceo_plots.csv (subir a CEO), strata_key.csv (llave), "
          "validation_points.gpkg, strata_weights.csv, README_validacion.md")


if __name__ == "__main__":
    main()
