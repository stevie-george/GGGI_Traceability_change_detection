"""
download_scenes.py — descarga a disco LOCAL las escenas Sentinel-2 que necesitan unos tiles,
para luego componer OFFLINE. Evita el throttle de Planetary Computer, que congela la lectura
concurrente de ciertas escenas costeras (T13Q*) — una descarga secuencial simple sí funciona.

    run_producer.bat download_scenes.py --states 14 --tile-ids r001c006 r001c012
    run_producer.bat download_scenes.py --states 14 --tiles-file missing.txt

Escribe out/_scene_cache/<scene_id>__<band>.tif (salta las ya descargadas, reusa entre tiles).
Después: run_producer.bat s2_export.py --states 14 --tile-ids <esos>  (lee del caché -> rápido).
"""
import argparse
from pathlib import Path

import requests
import pystac_client
import planetary_computer as pc

from s2_export import (CATALOG, read_aoi, make_grid, state_prefix, SEASONS, BANDS,
                       _season_items, SCENE_CACHE)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--states", nargs="*", default=None)
    ap.add_argument("--tile-ids", nargs="*", default=None)
    ap.add_argument("--tiles-file", default=None)
    args = ap.parse_args()
    tids = list(args.tile_ids or [])
    if args.tiles_file:
        tids += Path(args.tiles_file).read_text().split()
    if not tids:
        raise SystemExit("da --tile-ids o --tiles-file")

    aoi = read_aoi(args.states)
    grid = dict(make_grid(aoi, state_prefix(args.states)))
    cat = pystac_client.Client.open(CATALOG, modifier=pc.sign_inplace)
    SCENE_CACHE.mkdir(parents=True, exist_ok=True)

    # 1) escenas únicas que usarán esos tiles (misma selección que season_composite)
    uniq = {}
    for tid in tids:
        cell = grid.get(tid)
        if cell is None:
            print(f"  [omito] {tid}: no está en el grid"); continue
        for name, (s, e) in SEASONS.items():
            for it in _season_items(cat, cell, s, e, drop=False):   # sin drop: no abre B04 por red
                uniq[it.id] = it
    print(f"{len(tids)} tiles -> {len(uniq)} escenas únicas × {len(BANDS)} bandas", flush=True)

    # 2) descargar secuencial (firma fresca por archivo; salta las que ya están)
    n_dl = n_skip = n_fail = 0
    items = sorted(uniq.items())
    for k, (sid, it) in enumerate(items, 1):
        for bnd in BANDS:
            dst = SCENE_CACHE / f"{sid}__{bnd}.tif"
            if dst.exists() and dst.stat().st_size > 0:
                n_skip += 1; continue
            try:
                url = pc.sign(it.assets[bnd].href)
                with requests.get(url, stream=True, timeout=180) as r:
                    r.raise_for_status()
                    tmp = dst.with_suffix(".part")
                    with open(tmp, "wb") as f:
                        for chunk in r.iter_content(1 << 20):
                            f.write(chunk)
                    tmp.replace(dst)
                n_dl += 1
            except Exception as ex:
                n_fail += 1
                print(f"    [fallo] {sid} {bnd}: {type(ex).__name__}: {ex}", flush=True)
        if k % 5 == 0 or k == len(items):
            print(f"  [{k}/{len(items)}] escenas | nuevas {n_dl} | ya estaban {n_skip} | "
                  f"fallos {n_fail}", flush=True)

    print(f"\nLISTO: descargadas {n_dl} | existentes {n_skip} | fallos {n_fail}  -> {SCENE_CACHE}")
    if n_fail:
        print("  (re-ejecuta para reintentar las fallidas; salta las ya descargadas)")


if __name__ == "__main__":
    main()
