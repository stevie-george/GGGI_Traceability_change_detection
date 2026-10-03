"""
check_tiles.py — QA a batch of generated tiles before packaging.

Reports each tile's valid-pixel % (non-NoData) in its TRUE render per season, so
degraded tiles (holes) are caught early. Expect ~97-98% in BOTH seasons; a tile
below 90% -- especially a corner tile that straddles Sentinel-2 MGRS footprints --
is suspect: delete its out/<tile> dir and rebuild.

    run_producer.bat check_tiles.py                      # every tile in out/
    run_producer.bat check_tiles.py r004c008 r006c000    # only these
"""
import sys
from pathlib import Path
import numpy as np
import rasterio

OUT = Path(__file__).resolve().parent / "out"


def valid_frac(p):
    with rasterio.open(p) as src:
        a = src.read(1)
        nod = src.nodata
    if nod is not None:
        return float((a != nod).mean())
    if a.dtype.kind == "f":
        return float((np.isfinite(a) & (a != 0)).mean())
    return float((a != 0).mean())


def main():
    want = sys.argv[1:]
    tiles = want or sorted(d.name for d in OUT.glob("*") if d.is_dir())
    worst = 100.0
    for t in tiles:
        d = OUT / t
        feat = (d / f"{t}_features.tif").exists()
        parts, vals = [], []
        for s in ("dry", "green"):
            p = d / f"{t}_{s}_TRUE.tif"
            if p.exists():
                v = valid_frac(p) * 100
                vals.append(v)
                parts.append(f"{s}={v:3.0f}%")
            else:
                vals.append(0.0)
                parts.append(f"{s}=  --")
        lo = min(vals) if vals else 0.0
        worst = min(worst, lo)
        flag = "  <-- CHECK" if (not feat or lo < 90) else ""
        print(f"{t}  feat={int(feat)}  " + "  ".join(parts) + flag)
    print(f"\n{len(tiles)} tiles; worst season coverage = {worst:.0f}%  "
          f"({'all good' if worst >= 90 else 'rebuild the flagged tiles'})")


if __name__ == "__main__":
    main()
