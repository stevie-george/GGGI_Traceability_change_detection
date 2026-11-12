"""
infer.py — aplica el RandomForest (rf_model.pkl) a los tiles y exporta el mapa.

Por cada tile escribe en maps/:
    <tile>_class.tif        clase por píxel (uint8 = class_id), CON tabla de color de
                            legend.csv -> se abre ya coloreado en QGIS
    <tile>_confidence.tif   confianza 0-100 (prob. máxima del RF) -> insumo de las
                            pseudo-etiquetas de la Fase 2 (CNN)
Y un mosaico:
    maps/class_mosaic.vrt   maps/confidence_mosaic.vrt

    run_producer.bat infer.py                 # los tiles etiquetados -> maps/
    run_producer.bat infer.py --tiles r001c015 r002c005
    run_producer.bat infer.py --version manual_sin_inegi --all   # -> maps_manual_sin_inegi/
    run_producer.bat infer.py --limit 3       # prueba

Versionado: --version NAME escribe en maps_<NAME>/ (no pisa inferencias previas).
Requiere rf_model.pkl (train.py) + SSD (features.tif).
"""
import argparse
import csv
from pathlib import Path

import numpy as np
import geopandas as gpd
import rasterio
from rasterio.warp import reproject, Resampling
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
# clase AGRUPADA 13 (Agricultura) no está en legend.csv -> color de cultivo anual (sin esto sale negra)
CMAP.setdefault(13, CMAP.get(9, (255, 213, 79, 255)))


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
    ap.add_argument("--version", default=None,
                    help="escribe en maps_<version>/ en vez de maps/ (no pisa inferencias previas)")
    ap.add_argument("--in-dir", default=None,
                    help="carpeta de tiles de entrada (default: out/). P.ej. out_2016 para el mapa 2016; "
                         "el DEM (estático) se reutiliza de out/ si no está en esta carpeta")
    args = ap.parse_args()

    global OUT
    if args.in_dir:
        OUT = Path(args.in_dir)
        print(f"[entrada: {OUT}]  (DEM se reutiliza de {HERE / 'out'} si falta aquí)")
    maps_dir = HERE / (f"maps_{args.version}" if args.version else "maps")
    bundle = joblib.load(HERE / "rf_model.pkl")
    rf, feats, classes = bundle["model"], bundle["features"], np.array(bundle["labels"])
    rf_classes = np.array(rf.classes_)
    rf.n_jobs = PRED_JOBS      # el modelo se entrenó con n_jobs=-1; al inferir lo acotamos por RAM

    if args.all:
        tiles = sorted(d.name for d in OUT.iterdir()                      # cualquier prefijo (r… o 16_r…)
                       if d.is_dir() and (d / f"{d.name}_features.tif").exists())
    elif args.tiles:
        tiles = list(args.tiles)
    else:
        tiles = sorted(gpd.read_file(LABELS, layer="labels")["tile_id"].dropna().unique())
    if args.limit:
        tiles = tiles[:args.limit]
    maps_dir.mkdir(exist_ok=True)
    print(f"infiriendo {len(tiles)} tiles -> {maps_dir.name}/ | {len(feats)} predictores | "
          f"modelo {len(rf_classes)} clases")

    prof_base = {"driver": "GTiff", "count": 1, "dtype": "uint8", "nodata": 0,
                 "compress": "ZSTD", "tiled": True, "blockxsize": 512, "blockysize": 512}
    done, locked = 0, []
    for i, tid in enumerate(tiles, 1):
        if args.skip_existing and (maps_dir / f"{tid}_class.tif").exists() and (maps_dir / f"{tid}_confidence.tif").exists():
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
        if not dpath.exists():
            dpath = HERE / "out" / tid / f"{tid}_dem.tif"    # DEM estático: reutiliza el de 2025
        dem = np.full((len(DEM_BANDS), H, W), np.nan, "float32")
        if dpath.exists():
            with rasterio.open(dpath) as dsrc:
                if (dsrc.height, dsrc.width) == (H, W) and dsrc.transform == prof["transform"]:
                    dem = dsrc.read().astype("float32")        # mismo grid: lectura directa
                else:                                           # mismo CRS (6372), grid distinto -> resamplear
                    reproject(dsrc.read().astype("float32"), dem,
                              src_transform=dsrc.transform, src_crs=dsrc.crs,
                              dst_transform=prof["transform"], dst_crs=prof["crs"],
                              resampling=Resampling.bilinear,
                              src_nodata=dsrc.nodata, dst_nodata=np.nan)
                    print(f"  [{i}/{len(tiles)}] {tid}: DEM resampleado al grid del features "
                          f"({dsrc.height}x{dsrc.width} -> {H}x{W})", flush=True)
        arr = np.concatenate([arr, dem], axis=0)
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

        cpath, qpath = maps_dir / f"{tid}_class.tif", maps_dir / f"{tid}_confidence.tif"
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
            fs = sorted(str(p) for p in maps_dir.glob(f"*_{kind}.tif"))   # TODOS los mapas de esta versión
            if fs:
                gdal.BuildVRT(str(maps_dir / f"{kind}_mosaic.vrt"), fs)
        print(f"mosaicos: {maps_dir.name}/class_mosaic.vrt, {maps_dir.name}/confidence_mosaic.vrt")
    except Exception as e:
        print(f"[aviso] no se armó el VRT ({e}); carga los _class.tif directamente")

    print(f"\n{done} tiles -> {maps_dir}/  (abre {maps_dir.name}/class_mosaic.vrt en QGIS)")
    if locked:
        print(f"\n[!] {len(locked)} tile(s) BLOQUEADOS (quedaron con la versión vieja): "
              f"{' '.join(locked)}")
        print("    Cierra/quita esas capas en QGIS y rehazlos (sin --skip-existing porque el "
              "archivo viejo existe):")
        vflag = f" --version {args.version}" if args.version else ""
        print(f"    run_producer.bat infer.py{vflag} --tiles {' '.join(locked)}")


if __name__ == "__main__":
    main()
