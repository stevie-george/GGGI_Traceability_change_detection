"""
add_dem.py — capa estática de terreno (elevación + pendiente) por tile, desde el
Copernicus DEM GLO-30 (Planetary Computer). Se guarda como `<tile>_dem.tif` (2 bandas)
ALINEADO al grid de features.tif, para que sample/infer lo concatenen a los 34
predictores Sentinel-2.

Por qué aparte: es estático — no cambia con las temporadas, así que sobrevive a la
re-generación temporal de features.tif (Paso 3). Separa bosque templado (sierras) de
selva baja (tierras bajas), y ubica aguacate (ladera) y agave (Los Altos).

    run_producer.bat add_dem.py                 # todos los tiles construidos
    run_producer.bat add_dem.py --tiles r006c000
    run_producer.bat add_dem.py --limit 2 --force

Salida: out/<tile>/<tile>_dem.tif  (banda 1 = elevation [m], banda 2 = slope [grados])
"""
import argparse
from pathlib import Path

import numpy as np
import pandas as pd
import rasterio
from rasterio.transform import from_origin
from rasterio.warp import transform_bounds, reproject, Resampling
import pystac_client
import planetary_computer as pc
import rioxarray  # noqa: F401
from odc.stac import load as odc_load

from s2_export import CATALOG, OUT_CRS, RES

HERE = Path(__file__).resolve().parent
OUT = HERE / "out"
DEM_COLLECTION = "cop-dem-glo-30"
DEM_BANDS = ["elevation", "slope"]


def dem_for(catalog, b4326):
    items = list(catalog.search(collections=[DEM_COLLECTION], bbox=b4326).items())
    if not items:
        return None
    for it in items:                       # los items del DEM suelen traer datetime=None
        if it.datetime is None:
            it.datetime = pd.Timestamp("2021-01-01").to_pydatetime()
    ds = odc_load(items, bands=["data"], crs=OUT_CRS, resolution=RES, bbox=b4326,
                  resampling="bilinear", dtype="float32", nodata=np.nan, fail_on_error=False)
    d = ds["data"]
    if "time" in d.dims:                    # mosaicar teselas del DEM
        d = d.max("time", skipna=True)
    return d


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tiles", nargs="*", default=None)
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--force", action="store_true", help="rehacer aunque ya exista _dem.tif")
    args = ap.parse_args()
    tiles = args.tiles or sorted(d.name for d in OUT.glob("r*c*") if d.is_dir())
    if args.limit:
        tiles = tiles[:args.limit]

    catalog = pystac_client.Client.open(CATALOG, modifier=pc.sign_inplace)
    n_ok = n_skip = n_miss = 0
    for i, tid in enumerate(tiles, 1):
        feat = OUT / tid / f"{tid}_features.tif"
        dpath = OUT / tid / f"{tid}_dem.tif"
        if not feat.exists():
            n_miss += 1; continue
        if dpath.exists() and not args.force:
            n_skip += 1; continue
        with rasterio.open(feat) as t:
            dst_tr, dst_crs, H, W = t.transform, t.crs, t.height, t.width
            b4326 = list(transform_bounds(t.crs, "EPSG:4326", *t.bounds))

        d = dem_for(catalog, b4326)
        if d is None:
            n_miss += 1; print(f"  [{i}/{len(tiles)}] {tid}: sin DEM"); continue
        xs, ys = d["x"].values, d["y"].values
        src_tr = from_origin(float(xs[0]) - RES / 2, float(ys[0]) + RES / 2, RES, RES)

        elev = np.full((H, W), np.nan, "float32")
        reproject(np.ascontiguousarray(d.values, "float32"), elev,
                  src_transform=src_tr, src_crs=OUT_CRS,
                  dst_transform=dst_tr, dst_crs=dst_crs,
                  src_nodata=np.nan, dst_nodata=np.nan, resampling=Resampling.bilinear)
        gy, gx = np.gradient(elev, RES, RES)                         # dz/dy, dz/dx (m/m)
        slope = np.degrees(np.arctan(np.hypot(gx, gy))).astype("float32")

        prof = {"driver": "GTiff", "height": H, "width": W, "count": 2, "dtype": "float32",
                "crs": dst_crs, "transform": dst_tr, "nodata": float("nan"),
                "compress": "ZSTD", "tiled": True, "blockxsize": 512, "blockysize": 512}
        with rasterio.open(dpath, "w", **prof) as o:
            o.write(elev, 1); o.write(slope, 2)
            o.descriptions = tuple(DEM_BANDS)
        n_ok += 1
        print(f"  [{i}/{len(tiles)}] {tid}: dem ok (elev {np.nanmin(elev):.0f}–{np.nanmax(elev):.0f} m, "
              f"pend máx {np.nanmax(slope):.0f}°)")

    print(f"\nDEM: {n_ok} nuevos | {n_skip} ya existían | {n_miss} sin features/DEM  "
          f"-> out/<tile>/<tile>_dem.tif")


if __name__ == "__main__":
    main()
