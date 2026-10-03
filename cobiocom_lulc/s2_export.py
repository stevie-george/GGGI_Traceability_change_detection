"""
s2_export.py — Sentinel-2 dual-season composites, renders and spectral indices
for the COBIOCOM 8-state land-cover classification (west-central Mexico).

Downloads NOTHING but the final products. For each processing tile it streams
cloud-free per-season MEDIAN composites straight from Microsoft Planetary
Computer (STAC + Cloud-Optimized GeoTIFF), masks clouds with the SCL band,
computes indices, and writes a feature stack + visual renders as compressed
COGs. Per-tile, resumable (skips finished tiles), dask-parallel.

Requires the conda env in environment.yml.

Examples
--------
    python s2_export.py --out ./out --states 14 16 --limit 1   # test one tile
    python s2_export.py --out ./out                            # all 8 states
"""
from __future__ import annotations
import argparse
import subprocess
import sys
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
import xarray as xr
import geopandas as gpd
from shapely.geometry import box

import pystac_client
import planetary_computer as pc

# odc-loader logs one WARNING per scene it drops ("Ignoring read failure ...").
# With fail_on_error=False that is expected noise -- the median composite fills in
# from the dozens of scenes that DO load -- so silence just that logger and keep the
# console to per-tile progress. Real ERROR-level problems still print.
import logging
logging.getLogger("odc.loader._rio").setLevel(logging.ERROR)
from odc.stac import load as odc_load
import rasterio
from rasterio.enums import Resampling
from rasterio.transform import from_origin
from rasterio.warp import transform_bounds, reproject
from rasterio.windows import from_bounds, Window
import rioxarray  # noqa: F401  registers the .rio accessor

# ------------------------------------------------------------------ config --
CATALOG    = "https://planetarycomputer.microsoft.com/api/stac/v1"
COLLECTION = "sentinel-2-l2a"

AOI_GPKG = (r"C:\Users\StephaniePatriciaGeo\OneDrive - Global Green Growth "
            r"Institute\Documents\MX40\Geoespacial_compartida\Shapes_COBIOCOM\RecortesCOBIOCOM\EntidadesCOBIOCOM.gpkg")
AOI_LAYER = "EntidadesCOBIOCOM"
# Prefer a LOCAL copy (made by make_qgis_assets.py) so a run never depends on the
# OneDrive path, which can dehydrate to cloud-only and vanish mid-run.
AOI_LOCAL = Path(__file__).resolve().parent / "aoi.gpkg"
GRID_GPKG = Path(__file__).resolve().parent / "tile_grid.gpkg"

OUT_CRS = "EPSG:6372"   # Mexico ITRF2008 / LCC (metres) — national metric grid, no UTM seams
#                         (the AOI gpkg is EPSG:6365 = geographic/degrees; we reproject to this)
RES     = 10            # metres
TILE_M  = 20000         # 20 km processing tiles
MAX_CLOUD  = 40         # scene-level prefilter (%)
SCENES_PER_MGRS = 8     # least-cloudy scenes/season kept PER Sentinel-2 MGRS footprint.
#                         Capping globally can starve a footprint that covers part of a
#                         tile and blow a hole (corner tiles straddle up to 4 footprints).
#                         Per-footprint keeps coverage AND stays light: a 1-footprint tile
#                         pulls 8, a 4-corner tile ~32.
READ_WORKERS = 1        # lecturas directas en paralelo por temporada. SECUENCIAL a propósito: con
#                         conexiones concurrentes PC estrangula ciertas escenas costeras (T13Q*);
#                         secuencial/baja-concurrencia lee rápido. Reemplaza a odc_load (que colgaba).
SCENE_TIMEOUT = 120     # s máx por escena; una lenta/ilegible se salta
SCENE_CACHE = Path(__file__).resolve().parent / "out" / "_scene_cache"  # escenas pre-descargadas (en F:)
TILE_TIMEOUT = 1800     # per-tile watchdog (s): con 4 temporadas + lectura serializada un tile
#                         costero puede tardar ~15-20 min; damos margen antes de matarlo.
#                         running at 15 min is hung on a dead socket -> kill + retry it.

# Seasons for the 2025-2026 cycle — EDIT to your target mapping year.
SEASONS = {
    "wet":     ("2025-06-01", "2025-08-31"),   # green-up / monzón temprano
    "green":   ("2025-09-01", "2025-11-30"),   # post-monsoon peak greenness
    "cooldry": ("2025-12-01", "2026-02-28"),   # seca fría / senescencia temprana
    "dry":     ("2026-03-01", "2026-05-31"),   # dry-season senescence trough
}
RENDER_SEASONS = ("green", "dry")   # renders para consultores solo en estas (no inflar storage)

OPTICAL = ["B02", "B03", "B04", "B05", "B06", "B07", "B08", "B8A", "B11", "B12"]
BANDS   = OPTICAL + ["SCL"]
KEEP_SCL = [4, 5, 6, 7, 11]   # veg, bare, water, unclassified, snow (drop cloud/shadow/cirrus/shadow)

# Surface-reflectance harmonisation: processing baseline >= 04.00 (all 2022+
# scenes, so all of ours) carries a -1000 BOA offset. refl = (DN - 1000)/10000.
BOA_OFFSET = -1000
QUANT      = 10000.0

# Visual renders (R, G, B). SWIR combo is the most useful for separating
# avocado / agave / bare soil / crop moisture.
RENDERS = {
    "TRUE": ["B04", "B03", "B02"],   # true colour
    "CIR":  ["B08", "B04", "B03"],   # NIR false colour  (vegetation bright red)
    "SWIR": ["B12", "B8A", "B04"],   # SWIR false colour (crops / soil / moisture)
}

# Per-season index bands carried into the classifier feature stack.
INDEX_BANDS = ["NDVI", "NDRE", "NDMI", "MNDWI", "EVI", "BSI"]


# --------------------------------------------------------------- functions --
def read_aoi(states=None):
    if AOI_LOCAL.exists():
        gdf = gpd.read_file(AOI_LOCAL, layer="aoi").to_crs(OUT_CRS)
    else:
        gdf = gpd.read_file(AOI_GPKG, layer=AOI_LAYER).to_crs(OUT_CRS)
    if states:
        keep = [str(s).zfill(2) for s in states]
        gdf = gdf[gdf["CVE_ENT"].isin(keep)]
    return gdf


def tiles_for_consultant(value):
    """Tile ids assigned to a consultant in tile_grid.gpkg's 'consultant' column."""
    grid = gpd.read_file(GRID_GPKG)
    col = next((c for c in grid.columns if c.lower().startswith("consult")), None)
    if col is None:
        raise SystemExit(f"no 'consultant' column in {GRID_GPKG.name}")
    try:
        mask = grid[col].astype(float) == float(value)
    except (ValueError, TypeError):
        mask = grid[col].astype(str) == str(value)
    return sorted(grid.loc[mask, "tile_id"].tolist())


def state_prefix(states):
    """Tile-id prefix that keeps states apart (ids are r/c LOCAL to each state's bbox,
    so every state restarts at r000c000 and would collide in out/). Jalisco (14) stays
    UNPREFIXED — it's already in production with bare ids; new states get '<CVE>_'."""
    if not states:
        return ""
    codes = [str(s).zfill(2) for s in states]
    if codes == ["14"]:
        return ""
    if len(codes) == 1:
        return f"{codes[0]}_"
    raise SystemExit("separación por estado: genera un estado a la vez (--states <uno>)")


def make_grid(aoi, prefix=""):
    """Regular TILE_M grid (in OUT_CRS) over the AOI, keeping cells that touch it."""
    minx, miny, maxx, maxy = aoi.total_bounds
    union = aoi.union_all() if hasattr(aoi, "union_all") else aoi.unary_union
    tiles, y, r = [], miny, 0
    while y < maxy:
        x, c = minx, 0
        while x < maxx:
            cell = box(x, y, x + TILE_M, y + TILE_M)
            if cell.intersects(union):
                tiles.append((f"{prefix}r{r:03d}c{c:03d}", cell))
            x += TILE_M
            c += 1
        y += TILE_M
        r += 1
    return tiles


def _has_crs(item):
    """True if the item's B04 COG is georeferenced (a few PC scenes are not)."""
    try:
        with rasterio.open(_asset_src(item, "B04")) as r:
            return r.crs is not None
    except Exception:
        return False


def _drop_ungeoreferenced(items):
    """Drop scenes whose COGs have no CRS. Baja concurrencia (4): muchas aperturas
    simultáneas por red congelan ciertas escenas costeras (desde caché local da igual)."""
    with ThreadPoolExecutor(max_workers=4) as ex:
        keep = list(ex.map(_has_crs, items))
    good = [it for it, ok in zip(items, keep) if ok]
    if len(good) < len(items):
        print(f"    dropped {len(items) - len(good)} ungeoreferenced scene(s)")
    return good


def _asset_src(item, band):
    """Ruta LOCAL de la escena si fue descargada al caché; si no, la URL (firmada) de PC."""
    local = SCENE_CACHE / f"{item.id}__{band}.tif"
    return str(local) if local.exists() else item.assets[band].href


def _season_items(catalog, cell, start, end, drop=True):
    """Escenas seleccionadas de una temporada (búsqueda + tope por MGRS [+ drop sin-CRS]).
    La comparten season_composite y download_scenes.py para descargar/leer EXACTAMENTE lo mismo.
    drop=False en la descarga: no abre B04 por red (eso congela); el composite filtra desde caché."""
    b4326 = list(gpd.GeoSeries([cell], crs=OUT_CRS).to_crs(4326).total_bounds)
    items = catalog.search(collections=[COLLECTION], bbox=b4326, datetime=f"{start}/{end}",
                           query={"eo:cloud_cover": {"lt": MAX_CLOUD}}).item_collection()
    if len(items) == 0:
        return []
    by_mgrs = defaultdict(list)
    for it in items:
        by_mgrs[it.properties.get("s2:mgrs_tile", it.id)].append(it)
    sel = []
    for grp in by_mgrs.values():
        grp.sort(key=lambda it: it.properties.get("eo:cloud_cover", 100))
        sel.extend(grp[:SCENES_PER_MGRS])
    return _drop_ungeoreferenced(sel) if drop else sel


def tile_grid(tdir, tile_id, cell):
    """(crs, transform, H, W) del tile. Usa dem.tif si existe (mantiene la alineación con los
    tiles ya generados por odc); si no, un grid limpio desde el cell en OUT_CRS (10 m)."""
    dem = Path(tdir) / f"{tile_id}_dem.tif"
    if dem.exists():
        with rasterio.open(dem) as d:
            return d.crs, d.transform, d.height, d.width
    minx, miny, maxx, maxy = cell.bounds
    W, H = round((maxx - minx) / RES), round((maxy - miny) / RES)
    return rasterio.crs.CRS.from_user_input(OUT_CRS), from_origin(minx, maxy, RES, RES), H, W


def _read_scene(item, grid, cell):
    """Lee TODAS las bandas de una escena y las reproyecta al grid del tile. Clave: lee la
    VENTANA NATIVA (rápido: ~seg) y reproyecta con numpy — WarpedVRT y odc_load se cuelgan
    leyendo ciertas escenas costeras, la lectura nativa con ventana no."""
    dst_crs, dst_tr, H, W = grid
    out = {}
    for bnd in BANDS:                     # OPTICAL + SCL
        dst = np.zeros((H, W), "float32")
        with rasterio.open(_asset_src(item, bnd)) as src:
            bb = transform_bounds(dst_crs, src.crs, *cell.bounds)
            win = from_bounds(*bb, transform=src.transform).round_offsets().round_lengths()
            win = win.intersection(Window(0, 0, src.width, src.height))   # clip al área válida
            if win.width >= 1 and win.height >= 1:
                native = src.read(1, window=win).astype("float32")        # no-boundless = rápido
                reproject(native, dst, src_transform=src.window_transform(win), src_crs=src.crs,
                          dst_transform=dst_tr, dst_crs=dst_crs,
                          resampling=Resampling.nearest if bnd == "SCL" else Resampling.bilinear,
                          src_nodata=src.nodata, dst_nodata=0)
        out[bnd] = dst
    return out


def season_composite(catalog, cell, start, end, grid):
    """Cloud-free median surface-reflectance composite for one tile & season.
    Lectura DIRECTA en paralelo (WarpedVRT) en vez de odc_load: una escena lenta/ilegible
    se salta (no cuelga todo el tile como hacía odc con las costeras)."""
    items = _season_items(catalog, cell, start, end)
    if not items:
        return None

    scenes = []
    with ThreadPoolExecutor(max_workers=READ_WORKERS) as ex:
        futs = {ex.submit(_read_scene, it, grid, cell): it for it in items}
        for fut in futs:
            try:
                scenes.append(fut.result(timeout=SCENE_TIMEOUT))
            except Exception:
                pass            # escena lenta/ilegible -> se salta
    if not scenes:
        return None

    _, dst_tr, H, W = grid
    med = {}
    for bnd in OPTICAL:
        cube = np.stack([sc[bnd].astype("float32") for sc in scenes])          # (n, H, W)
        clear = np.stack([np.isin(sc["SCL"], KEEP_SCL) for sc in scenes])
        refl = (cube + BOA_OFFSET).clip(min=0) / QUANT
        refl[~clear] = np.nan
        med[bnd] = np.nanmedian(refl, axis=0).astype("float32")

    xs = dst_tr.c + (np.arange(W) + 0.5) * dst_tr.a
    ys = dst_tr.f + (np.arange(H) + 0.5) * dst_tr.e
    ds = xr.Dataset({b: (("y", "x"), med[b]) for b in OPTICAL}, coords={"y": ys, "x": xs})
    return add_indices(ds).rio.write_crs(OUT_CRS)


def add_indices(med):
    b = med
    nd = lambda a, c: (a - c) / (a + c)
    med["NDVI"]  = nd(b["B08"], b["B04"]).astype("float32")
    med["NDRE"]  = nd(b["B08"], b["B05"]).astype("float32")
    med["NDMI"]  = nd(b["B08"], b["B11"]).astype("float32")
    med["MNDWI"] = nd(b["B03"], b["B11"]).astype("float32")
    med["BSI"]   = nd(b["B11"] + b["B04"], b["B08"] + b["B02"]).astype("float32")
    evi = 2.5 * (b["B08"] - b["B04"]) / (b["B08"] + 6 * b["B04"] - 7.5 * b["B02"] + 1.0)
    med["EVI"] = evi.clip(-1, 1).astype("float32")
    return med


def _stretch(da, lo=2, hi=98):
    a = da.values.astype("float32")
    finite = np.isfinite(a)
    if not finite.any():
        return np.zeros(a.shape, "uint8")
    p_lo, p_hi = np.nanpercentile(a[finite], [lo, hi])
    p_hi = max(p_hi, p_lo + 1e-6)
    out = np.clip((a - p_lo) / (p_hi - p_lo), 0, 1) * 255
    return np.nan_to_num(out).astype("uint8")


def _write_cog(da, path, nodata=None):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    da = da.rio.write_crs(OUT_CRS)
    if nodata is not None:
        da = da.rio.write_nodata(nodata)
    da.rio.to_raster(path, driver="COG", compress="ZSTD",
                     blocksize=512, overview_resampling="average")


def write_render(med, combo, path):
    stacked = np.stack([_stretch(med[bd]) for bd in combo])   # (3, y, x) uint8
    da = xr.DataArray(stacked, dims=("band", "y", "x"),
                      coords={"band": [1, 2, 3], "y": med.y, "x": med.x})
    _write_cog(da, path, nodata=0)


def process_tile(catalog, tile_id, cell, out_dir):
    tdir = Path(out_dir) / tile_id
    stack_path = tdir / f"{tile_id}_features.tif"
    if stack_path.exists():
        return "skip"

    grid = tile_grid(tdir, tile_id, cell)
    seas = {}
    for name, (start, end) in SEASONS.items():
        import time as _t; _t0 = _t.time()
        med = season_composite(catalog, cell, start, end, grid)
        print(f"    {tile_id} {name}: {_t.time()-_t0:.0f}s", flush=True)
        if med is None:
            return f"empty:{name}"
        seas[name] = med
        if name in RENDER_SEASONS:
            for rname, combo in RENDERS.items():
                write_render(med, combo, tdir / f"{tile_id}_{name}_{rname}.tif")
            _write_cog(med["NDVI"], tdir / f"{tile_id}_{name}_NDVI.tif", nodata=np.nan)

    # cross-season change features
    dndvi = (seas["green"]["NDVI"] - seas["dry"]["NDVI"]).astype("float32")
    dndmi = (seas["green"]["NDMI"] - seas["dry"]["NDMI"]).astype("float32")
    ndvi_amp = xr.concat([seas[s]["NDVI"] for s in SEASONS], dim="s")
    ndvi_amp = (ndvi_amp.max("s") - ndvi_amp.min("s")).astype("float32")   # amplitud anual (matorral bajo)
    _write_cog(dndvi, tdir / f"{tile_id}_dNDVI.tif", nodata=np.nan)

    # classifier feature stack (trim): green/dry con 16 bandas completas; wet/cooldry solo
    # los 6 índices (la señal fenológica que importa) -> 47 bandas en vez de 67, ~30% menos.
    feats, names = [], []
    for name in SEASONS:
        bands = (OPTICAL + INDEX_BANDS) if name in RENDER_SEASONS else INDEX_BANDS
        for v in bands:
            feats.append(seas[name][v])
            names.append(f"{name}_{v}")
    feats += [dndvi, dndmi, ndvi_amp]
    names += ["dNDVI", "dNDMI", "NDVI_amp"]
    stack = xr.concat(feats, dim="band").assign_coords(band=np.arange(1, len(names) + 1))
    _write_cog(stack.astype("float32"), stack_path, nodata=np.nan)
    (tdir / f"{tile_id}_bands.txt").write_text(
        "\n".join(f"{i+1}\t{n}" for i, n in enumerate(names)), encoding="utf-8")
    return "ok"


def _process_one(tid, cell, out):
    """Build ONE tile in this process (the body of a --worker-tile subprocess)."""
    catalog = pystac_client.Client.open(CATALOG, modifier=pc.sign_inplace)
    try:
        status = process_tile(catalog, tid, cell, out)
    except Exception as e:                          # log & report; the parent decides
        import traceback as _tb
        _tb.print_exc()
        status = f"ERROR: {type(e).__name__}: {e}"
    print(f"    worker {tid}: {status}", flush=True)
    return status


def _run_tile_watchdog(tid, out, states):
    """Run one tile in a subprocess under a hard timeout. A hung network read can't be
    killed from inside the process (it's stuck in GDAL/threads), but killing the whole
    subprocess frees the stalled socket -- so one dead connection can never freeze the
    run. Retries a stalled tile once, then skips it (rerun later)."""
    if (Path(out) / tid / f"{tid}_features.tif").exists():
        return "skip"
    cmd = [sys.executable, str(Path(__file__).resolve()), "--worker-tile", tid, "--out", out]
    if states:
        cmd += ["--states", *[str(s) for s in states]]
    for attempt in (1, 2):
        try:
            r = subprocess.run(cmd, timeout=TILE_TIMEOUT)     # run() kills the child on timeout
            return "ok" if r.returncode == 0 else f"error(rc={r.returncode})"
        except subprocess.TimeoutExpired:
            if attempt == 1:
                print(f"    {tid}: no progress in {TILE_TIMEOUT // 60} min "
                      f"-> killed, retrying once", flush=True)
    return f"TIMEOUT-skipped (stalled twice) -- rerun {tid} later"


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default="./out")
    ap.add_argument("--states", nargs="*", default=None,
                    help="CVE_ENT codes, e.g. 14 16 (default: all 8)")
    ap.add_argument("--limit", type=int, default=None, help="max tiles (for testing)")
    ap.add_argument("--tile-ids", nargs="*", default=None,
                    help="only these tile ids (from make_tile_grid.py), e.g. r003c004 r003c005")
    ap.add_argument("--consultant", default=None,
                    help="only tiles assigned to this consultant in tile_grid.gpkg")
    ap.add_argument("--worker-tile", default=None,
                    help="internal: build exactly this one tile in-process then exit "
                         "(the orchestrator spawns one per tile under a timeout)")
    args = ap.parse_args()

    aoi = read_aoi(args.states)
    prefix = state_prefix(args.states)

    # child process: build the single requested tile, exit 0 (ok/skip) or 1 (error)
    if args.worker_tile:
        cell = dict(make_grid(aoi, prefix)).get(args.worker_tile)
        if cell is None:
            print(f"    worker {args.worker_tile}: no such tile", flush=True)
            sys.exit(1)
        status = _process_one(args.worker_tile, cell, args.out)
        sys.exit(0 if status in ("ok", "skip") else 1)

    # orchestrator: pick the tiles, run each in its own watchdog'd subprocess
    tiles = make_grid(aoi, prefix)
    if args.consultant is not None:
        want = set(tiles_for_consultant(args.consultant))
        tiles = [t for t in tiles if t[0] in want]
    if args.tile_ids:
        wanted = set(args.tile_ids)
        tiles = [t for t in tiles if t[0] in wanted]
    if args.limit:
        tiles = tiles[:args.limit]
    print(f"{len(tiles)} tiles -> {args.out}")
    for i, (tid, _cell) in enumerate(tiles, 1):
        status = _run_tile_watchdog(tid, args.out, args.states)
        print(f"[{i}/{len(tiles)}] {tid}: {status}", flush=True)


if __name__ == "__main__":
    main()
