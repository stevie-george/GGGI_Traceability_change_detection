"""
package_for_consultants.py — build a portable ZIP bundle for QGIS labellers.

A consultant unzips it and opens the project in QGIS — no Python, no conda, no keys.
Run in the `cobiocom` env, from cobiocom_lulc, AFTER make_qgis_project.py has built
cobiocom_labeling.qgz:

    python package_for_consultants.py --name jalisco                    # all tiles in out/
    python package_for_consultants.py --name jalisco_C1_tona --consultant 1     # that consultant's set
    # send a NEW batch later -- tiles ONLY; their project, layout and labels are untouched:
    python package_for_consultants.py --name jalisco_C1_tona --update --tiles r003c020 r003c021

Bundle layout (relative paths -> works in any folder):
    cobiocom_labeling.qgz
    aoi.gpkg
    labels.gpkg               (EMPTY — the consultant labels into their own copy)
    out/<tile>/...            (reference COGs)
    legend.csv  SAMPLING_PROTOCOL.md  CONSULTANT_INSTALL.md
"""
import argparse
import re
import shutil
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

import pandas as pd
import numpy as np
import geopandas as gpd
import rasterio
from pyogrio import write_dataframe

from make_qgis_assets import SCHEMA, OUT_CRS   # reuse the label schema

HERE = Path(__file__).resolve().parent
COPY = ["aoi.gpkg", "legend.csv", "SAMPLING_PROTOCOL.md", "CONSULTANT_INSTALL.md"]
# cobiocom_labeling.qgz is handled separately (trimmed to this bundle's tiles)


def fresh_labels(path):
    """Write an EMPTY labels layer — never ship your own labels in the bundle."""
    data = {k: pd.Series([], dtype=v) for k, v in SCHEMA.items()}
    gdf = gpd.GeoDataFrame(data, geometry=gpd.GeoSeries([], crs=OUT_CRS))
    write_dataframe(gdf, path, layer="labels", driver="GPKG",
                    geometry_type="MultiPolygon", promote_to_multi=True)


def _index_to_uint8(src, dst):
    """Ship a float NDVI/dNDVI render as a compact uint8 grayscale GTiff (NoData=0) —
    ~10x smaller and identical for visual labeling. A 2-98% percentile stretch keeps the
    contrast; full float precision still lives in features.tif for the classifier."""
    with rasterio.open(src) as r:
        a = r.read(1).astype("float32")
        crs, transform, h, w = r.crs, r.transform, r.height, r.width
    finite = np.isfinite(a)
    out = np.zeros(a.shape, "uint8")
    if finite.any():
        lo, hi = np.nanpercentile(a[finite], [2, 98])
        hi = max(hi, lo + 1e-6)
        out[finite] = (np.clip((a[finite] - lo) / (hi - lo), 0, 1) * 254 + 1).astype("uint8")
    prof = {"driver": "GTiff", "height": h, "width": w, "count": 1, "dtype": "uint8",
            "crs": crs, "transform": transform, "nodata": 0, "compress": "ZSTD",
            "tiled": True, "blockxsize": 512, "blockysize": 512}
    with rasterio.open(dst, "w", **prof) as wds:
        wds.write(out, 1)


def _write_filtered_project(src_qgz, dst_qgz, keep_tiles):
    """Copy the project but drop render layers for tiles NOT in this bundle,
    so the consultant's project references only the tiles they actually have."""
    with zipfile.ZipFile(src_qgz) as z:
        members = {n: z.read(n) for n in z.namelist()}
    qgs = next(n for n in members if n.endswith(".qgs"))
    root = ET.fromstring(members[qgs])
    tile_re = re.compile(r"out[\\/](r\d+c\d+)[\\/]")

    drop = set()
    pl = root.find("projectlayers")
    if pl is not None:
        for ml in list(pl.findall("maplayer")):
            m = tile_re.search(ml.findtext("datasource") or "")
            if m and m.group(1) not in keep_tiles:
                drop.add(ml.findtext("id"))
                pl.remove(ml)
    for grp in root.iter("layer-tree-group"):
        for ltl in list(grp.findall("layer-tree-layer")):
            if ltl.get("id") in drop:
                grp.remove(ltl)
    lo = root.find("layerorder")
    if lo is not None:
        for lyr in list(lo.findall("layer")):
            if lyr.get("id") in drop:
                lo.remove(lyr)
    # drop now-empty per-tile subgroups
    parents = {c: p for p in root.iter() for c in p}
    for grp in list(root.iter("layer-tree-group")):
        if (grp.get("name") not in (None, "Sentinel-2 renders", "Basemaps", "Esri Wayback (dated)")
                and grp.find("layer-tree-layer") is None and grp.find("layer-tree-group") is None):
            parent = parents.get(grp)
            if parent is not None:
                parent.remove(grp)

    members[qgs] = ET.tostring(root, encoding="utf-8")
    with zipfile.ZipFile(dst_qgz, "w", zipfile.ZIP_DEFLATED) as z:
        for n, b in members.items():
            z.writestr(n, b)
    return len(drop)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--name", default="jalisco")
    ap.add_argument("--tiles", nargs="*", default=None,
                    help="tile ids whose RENDERS go in the pack (default: all of --consultant's, "
                         "else everything in out/). For an update, pass just the NEW tile ids.")
    ap.add_argument("--consultant", default=None,
                    help="this consultant's tiles (from tile_grid.gpkg) drive the project "
                         "+ default renders")
    ap.add_argument("--update", action="store_true",
                    help="update pack: ship ONLY the new --tiles (+ add_tiles.py helper), NOT the "
                         "project or labels -- the consultant drops them into their existing project")
    ap.add_argument("--force", action="store_true",
                    help="sobrescribir un paquete existente con el mismo --name (por defecto NO "
                         "sobrescribe: cada paquete se guarda por separado)")
    args = ap.parse_args()

    bundle = HERE.parent / f"cobiocom_labeling_{args.name}"
    if (bundle.exists() or bundle.with_suffix(".zip").exists()) and not args.force:
        print(f"[detenido] ya existe el paquete '{args.name}' (carpeta o .zip). Los paquetes se "
              f"guardan por separado — usa otro --name (p. ej. añade _2, _3 o la fecha), o pasa "
              f"--force para sobrescribir a propósito.")
        return
    if bundle.exists():
        shutil.rmtree(bundle)
    bundle.mkdir(parents=True)

    # An UPDATE ships ONLY the new tiles (+ add_tiles.py) so the consultant's existing
    # project, layout and drawn labels are never touched. An INITIAL bundle ships the
    # full starting project: reference docs, a fresh empty labels layer, the styled .qgz.
    if not args.update:
        missing = [f for f in COPY if not (HERE / f).exists()]
        for f in COPY:
            if (HERE / f).exists():
                shutil.copy2(HERE / f, bundle / f)
        if missing:
            print("[warn] missing (build the project / assets first):", ", ".join(missing))
        fresh_labels(bundle / "labels.gpkg")

    out_src = HERE / "out"
    # full = every tile this consultant should END UP with -> drives the .qgz + default renders
    if args.consultant is not None:
        from s2_export import tiles_for_consultant
        full = tiles_for_consultant(args.consultant)
    elif args.tiles:
        full = list(args.tiles)
    else:
        full = ([d.name for d in sorted(out_src.glob("*")) if d.is_dir()]
                if out_src.exists() else [])
    # render_tiles = tiles whose renders actually go in THIS pack (a subset, for an update)
    render_tiles = list(args.tiles) if args.tiles else full

    for t in render_tiles:
        s = out_src / t
        if s.is_dir():
            # ship only the renders (not the classifier stack), and convert the float
            # NDVI/dNDVI renders to compact uint8 grayscale -> ~1/3 the pack size
            shutil.copytree(s, bundle / "out" / t,
                            ignore=shutil.ignore_patterns("*_features.tif", "*_bands.txt",
                                                          "*.aux.xml", "*NDVI.tif"))
            for name in (f"{t}_dry_NDVI.tif", f"{t}_green_NDVI.tif", f"{t}_dNDVI.tif"):
                if (s / name).exists():
                    _index_to_uint8(s / name, bundle / "out" / t / name)
        else:
            print(f"  [warn] {t}: not found in out/ — run s2_export.py for it first")
    print(f"included renders for {len(render_tiles)} tile(s): "
          f"{', '.join(render_tiles) or '(none — run s2_export.py first)'}")

    if args.update:
        # tiles-only: include a one-paste console helper that drops the new tiles into the
        # project they ALREADY have open -- no .qgz, no labels, nothing else touched.
        if (HERE / "add_tiles.py").exists():
            shutil.copy2(HERE / "add_tiles.py", bundle / "add_tiles.py")
        (bundle / "NUEVOS_TILES_leeme.txt").write_text(
            "Actualizacion de tiles — NO toca tu proyecto, tu vista ni tus poligonos.\n"
            "======================================================================\n\n"
            "1. Descomprime este ZIP en la carpeta que CONTIENE tu carpeta de proyecto\n"
            "   'cobiocom_labeling_...'. Se combina y solo agrega tiles nuevos en out\\.\n"
            "   Acepta combinar/reemplazar si Windows pregunta.\n"
            "2. Con tu proyecto abierto, agrega los tiles nuevos de UNA de estas formas:\n"
            "   a) Consola de Python (Complementos -> Consola de Python), pega y Enter:\n"
            "        exec(open(r'add_tiles.py').read())\n"
            "      (usa la ruta completa a add_tiles.py si hace falta). Aparecen agrupados y con estilo.\n"
            "   b) O arrastra los .tif de out\\<tile>\\ al mapa (p. ej. *_dry_SWIR.tif).\n"
            "3. Guarda (Ctrl+S). Tu cobiocom_labeling.qgz y tu labels.gpkg quedan intactos.\n",
            encoding="utf-8")
        print(f"tiles-only update: {len(render_tiles)} tile(s) + add_tiles.py "
              f"(their project + labels untouched)")
    else:
        src_qgz = HERE / "cobiocom_labeling.qgz"
        if src_qgz.exists():
            dropped = _write_filtered_project(src_qgz, bundle / "cobiocom_labeling.qgz", set(full))
            print(f"project references this consultant's {len(full)} tile(s) "
                  f"(dropped {dropped} other-tile layers)")
        else:
            print("[warn] cobiocom_labeling.qgz not found — build it in QGIS (make_qgis_project.py) first")

    zip_path = bundle.with_suffix(".zip")
    if zip_path.exists():
        zip_path.unlink()
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
        for p in bundle.rglob("*"):
            z.write(p, p.relative_to(bundle.parent))
    print(f"wrote {zip_path.name}  ({zip_path.stat().st_size / 1e6:.0f} MB)  + folder {bundle.name}/")


if __name__ == "__main__":
    main()
