"""
filter_polys.py — filtro de CALIDAD espectral: quita polígonos que NO cuadran con su
clase (p. ej. "aguacate" que no es perenne, "agricultura" que en realidad es bosque/agua).
Lee la media de índices bajo cada polígono (features.tif -> requiere F:) y aplica una
regla por clase. Sobrescribe el gpkg (o usa --out).

    run_producer.bat filter_polys.py --gpkg semadet_avocado.gpkg --class 5
    run_producer.bat filter_polys.py --gpkg frontera_agricola.gpkg --class 9
"""
import argparse
from pathlib import Path
import numpy as np
import geopandas as gpd
import rasterio
from rasterio.windows import from_bounds, Window
from rasterio.features import geometry_mask

HERE = Path(__file__).resolve().parent
OUT = HERE / "out"
CRS = "EPSG:6372"
WANT = ["green_NDVI", "dry_NDVI", "green_NDMI", "green_MNDWI"]


def keep_rule(cid, v):
    """True = conservar. v = dict de medias de índices (o NaN)."""
    g, d, m, w = v["green_NDVI"], v["dry_NDVI"], v["green_NDMI"], v["green_MNDWI"]
    if any(np.isnan(x) for x in (g, d, m)):
        return False                                  # sin dato -> fuera
    if cid == 5:        # Aguacate: perenne (verde todo el año) + húmedo/regado
        return (d >= 0.35) and (g >= 0.45) and (m >= -0.05)
    if cid == 9:        # Agricultura (Frontera): NO bosque permanente y NO agua
        es_bosque = (g > 0.70) and (d > 0.60) and (m > 0.20)
        es_agua = (not np.isnan(w)) and (w > 0.15)
        return not (es_bosque or es_agua)
    return True


def band_names(t):
    return [l.split("\t")[1] for l in (OUT / t / f"{t}_bands.txt").read_text(encoding="utf-8").splitlines() if "\t" in l]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--gpkg", required=True)
    ap.add_argument("--class", dest="cid", type=int, required=True)
    ap.add_argument("--out", default=None, help="default: sobrescribe el gpkg")
    a = ap.parse_args()

    g = gpd.read_file(HERE / a.gpkg, layer="labels").to_crs(CRS).reset_index(drop=True)
    grid = gpd.read_file(HERE / "tile_grid.gpkg").to_crs(CRS)
    if "tile_id" not in grid.columns:
        grid = grid.rename(columns={grid.columns[0]: "tile_id"})
    rp = gpd.GeoDataFrame(geometry=g.representative_point(), crs=CRS)
    g["tile_id"] = gpd.sjoin(rp, grid[["tile_id", "geometry"]], how="left", predicate="within")["tile_id"].values

    keep = []
    for _, r in g.iterrows():
        t = r["tile_id"]
        v = {b: np.nan for b in WANT}
        if isinstance(t, str) and (OUT / t / f"{t}_features.tif").exists():
            names = band_names(t)
            with rasterio.open(OUT / t / f"{t}_features.tif") as s:
                w = from_bounds(*r.geometry.bounds, transform=s.transform).round_offsets().round_lengths().intersection(Window(0, 0, s.width, s.height))
                if w.width >= 1 and w.height >= 1:
                    idx = [names.index(b) + 1 for b in WANT if b in names]
                    got = [b for b in WANT if b in names]
                    arr = s.read(idx, window=w).astype("float32")
                    m = geometry_mask([r.geometry], out_shape=arr.shape[1:], transform=s.window_transform(w), invert=True)
                    for i, b in enumerate(got):
                        vv = arr[i][m]
                        v[b] = float(np.nanmean(vv)) if np.isfinite(vv).any() else np.nan
        keep.append(keep_rule(a.cid, v))

    keep = np.array(keep)
    out = HERE / (a.out or a.gpkg)
    g[keep].to_file(out, layer="labels", driver="GPKG")
    print(f"{a.gpkg} clase {a.cid}: {int(keep.sum())}/{len(g)} conservados "
          f"({int((~keep).sum())} incorrectos filtrados) -> {out.name}")


if __name__ == "__main__":
    main()
