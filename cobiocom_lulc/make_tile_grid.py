"""
make_tile_grid.py — write the processing-tile grid as a GeoPackage, for PLANNING.

No imagery, runs in seconds. Load tile_grid.gpkg in QGIS over the basemaps to see
which 20 km tiles cover the avocado / agave / dry-forest / Bajio zones, read the
`tile_id` of the ones you want, then generate just those:

    run_producer.bat make_tile_grid.py --states 14
    run_producer.bat s2_export.py --states 14 --tile-ids r003c004 r003c005

Then bundle a set per consultant:  package_for_consultants.py --name jalisco_A --tiles ...
"""
import argparse
from pathlib import Path

import geopandas as gpd
from s2_export import read_aoi, make_grid, OUT_CRS   # same grid -> same tile ids

HERE = Path(__file__).resolve().parent


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--states", nargs="*", default=None,
                    help="CVE_ENT codes, e.g. 14 (default: all 8)")
    ap.add_argument("--out", default=str(HERE / "tile_grid.gpkg"))
    args = ap.parse_args()

    out = Path(args.out)
    if out.exists():
        print(f"{out.name} already exists — NOT overwriting (it may hold your consultant "
              f"assignments). Delete it first, or pass --out <other path>, to rebuild.")
        return

    aoi = read_aoi(args.states)
    tiles = make_grid(aoi)
    gdf = gpd.GeoDataFrame(
        {"tile_id": [t[0] for t in tiles]},
        geometry=[t[1] for t in tiles], crs=OUT_CRS)
    gdf.to_file(args.out, layer="tiles", driver="GPKG")
    print(f"wrote {args.out}\n  {len(gdf)} tiles | {OUT_CRS} | 20 km each")


if __name__ == "__main__":
    main()
