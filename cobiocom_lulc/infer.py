"""
infer.py — aplica el RandomForest (rf_model.pkl) a los tiles y exporta el mapa.

Por cada tile escribe en maps/:
    <tile>_class.tif        clase por píxel (uint8 = class_id), CON tabla de color de
                            legend.csv -> se abre ya coloreado en QGIS
    <tile>_confidence.tif   confianza 0-100 (prob. máxima del RF) -> insumo de las
                            pseudo-etiquetas de la Fase 2 (CNN)
Y un mosaico:
    maps/class_mosaic.vrt   maps/confidence_mosaic.vrt

    run_producer.bat infer.py                 # los 54 tiles etiquetados
    run_producer.bat infer.py --tiles r001c015 r002c005
    run_producer.bat infer.py --limit 3       # prueba

Requiere rf_model.pkl (train.py) + SSD (features.tif).
"""
import argparse
import csv
from pathlib import Path

import numpy as np
import geopandas as gpd
import rasterio
import joblib

HERE = Path(__file__).resolve().parent
OUT = HERE / "out"
MAPS = HERE / "maps"
LABELS = HERE / "labels_merged.gpkg"
CHUNK = 1_000_000   # píxeles por lote en predict_proba (acota la RAM: un tile grande son ~4M)
PRED_JOBS = 8       # árboles en paralelo al inferir (el chunking ya acota la RAM; esto da velocidad)
DEM_BANDS = ["elevation", "slope"]   # se concatenan si existe <tile>_dem.tif (modelos con terreno)

# class_id -> (R,G,B) desde legend.csv
CMAP = {0: (0, 0, 0, 0)}
with open(HERE / "legend.csv", encoding="utf-8") as f:
    for r in csv.DictReader(f):
        h = r["color_hex"].lstrip("#")
        CMAP[int(r["class_id"])] = (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16), 255)


def band_names(tile):
    fp = OUT / tile / f"{tile}_bands.txt"
    return [ln.split("\t")[1] for ln in fp.read_text(encoding="utf-8").splitlines() if "\t" in ln]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tiles", nargs="*", default=None)
    ap.add_argument("--all", action="store_true", help="todos los tiles construidos en out/ (Jalisco completo)")
    ap.add_argument("--skip-existing", action="store_true",
                    help="reanudar: omitir tiles cuyo mapa ya está en maps/ (tras una interrupción)")
    ap.add_argument("--limit", type=int, default=None)
    args = ap.parse_args()

    bundle = joblib.load(HERE / "rf_model.pkl")
    rf, feats, classes = bundle["model"], bundle["features"], np.array(bundle["labels"])
    rf_classes = np.array(rf.classes_)
    rf.n_jobs = PRED_JOBS      # el modelo se entrenó con n_jobs=-1; al inferir lo acotamos por RAM

    if args.all:
        tiles = sorted(d.name for d in OUT.glob("r*c*") if d.is_dir())
    elif args.tiles:
        tiles = list(args.tiles)
    else:
        tiles = sorted(gpd.read_file(LABELS, layer="labels")["tile_id"].dropna().unique())
    if args.limit:
        tiles = tiles[:args.limit]
    MAPS.mkdir(exist_ok=True)
    print(f"infiriendo {len(tiles)} tiles | {len(feats)} predictores | modelo {len(rf_classes)} clases")

    prof_base = {"driver": "GTiff", "count": 1, "dtype": "uint8", "nodata": 0,
                 "compress": "ZSTD", "tiled": True, "blockxsize": 512, "blockysize": 512}
    done, locked = 0, []
    for i, tid in enumerate(tiles, 1):
        if args.skip_existing and (MAPS / f"{tid}_class.tif").exists() and (MAPS / f"{tid}_confidence.tif").exists():
            print(f"  [{i}/{len(tiles)}] {tid}: ya existe, reanudo (omito)"); continue
        feat = OUT / tid / f"{tid}_features.tif"
        if not feat.exists():
            print(f"  [{i}/{len(tiles)}] {tid}: sin features, omito"); continue
        with rasterio.open(feat) as src:
            names = band_names(tid) + DEM_BANDS
            arr = src.read().astype("float32")               # (34,H,W)
            H, W = src.height, src.width
            prof = {**prof_base, "height": H, "width": W, "crs": src.crs, "transform": src.transform}
        dpath = OUT / tid / f"{tid}_dem.tif"
        if dpath.exists():
            with rasterio.open(dpath) as dsrc:
                arr = np.concatenate([arr, dsrc.read().astype("float32")], axis=0)
        else:
            arr = np.concatenate([arr, np.full((len(DEM_BANDS), H, W), np.nan, "float32")], axis=0)
        arr = arr[[names.index(fn) for fn in feats]]         # solo/orden las bandas del modelo

        flat = arr.reshape(len(feats), -1).T
        del arr
        valid = ~np.isnan(flat).any(axis=1)
        cls = np.zeros(H * W, "uint8"); conf = np.zeros(H * W, "uint8")
        vi = np.where(valid)[0]
        for s in range(0, len(vi), CHUNK):          # por bloques: predict_proba nunca ve >CHUNK píxeles
            b = vi[s:s + CHUNK]
            p = rf.predict_proba(flat[b])
            cls[b] = rf_classes[p.argmax(1)].astype("uint8")
            conf[b] = np.clip(p.max(1) * 100, 0, 100).astype("uint8")
            del p

        cpath, qpath = MAPS / f"{tid}_class.tif", MAPS / f"{tid}_confidence.tif"
        try:
            with rasterio.open(cpath, "w", **prof) as dst:
                dst.write(cls.reshape(H, W), 1)
                dst.write_colormap(1, CMAP)
            with rasterio.open(qpath, "w", **prof) as dst:
                dst.write(conf.reshape(H, W), 1)
        except Exception as e:
            # archivo bloqueado (p. ej. abierto en QGIS): NO tira el run, lo salta y avisa
            locked.append(tid)
            print(f"  [{i}/{len(tiles)}] {tid}: BLOQUEADO, lo salto ({type(e).__name__}: "
                  f"¿abierto en QGIS?)")
            continue
        done += 1
        print(f"  [{i}/{len(tiles)}] {tid}: ok  (válidos {100*valid.mean():.0f}%)")

    # mosaicos VRT para cargar todo de una en QGIS
    try:
        from osgeo import gdal
        for kind in ("class", "confidence"):
            fs = sorted(str(p) for p in MAPS.glob(f"*_{kind}.tif"))   # TODOS los mapas, no solo los de esta corrida
            if fs:
                gdal.BuildVRT(str(MAPS / f"{kind}_mosaic.vrt"), fs)
        print("mosaicos: maps/class_mosaic.vrt, maps/confidence_mosaic.vrt")
    except Exception as e:
        print(f"[aviso] no se armó el VRT ({e}); carga los _class.tif directamente")

    print(f"\n{done} tiles -> {MAPS}/  (abre maps/class_mosaic.vrt en QGIS)")
    if locked:
        print(f"\n[!] {len(locked)} tile(s) BLOQUEADOS (quedaron con la versión vieja): "
              f"{' '.join(locked)}")
        print("    Cierra/quita esas capas en QGIS y rehazlos (sin --skip-existing porque el "
              "archivo viejo existe):")
        print(f"    run_producer.bat infer.py --tiles {' '.join(locked)}")


if __name__ == "__main__":
    main()
