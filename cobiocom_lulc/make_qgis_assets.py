"""
make_qgis_assets.py — create the empty `labels` GeoPackage for digitising.

Schema = SAMPLING_PROTOCOL.md §6, CRS = EPSG:6372 (metres), geometry = MultiPolygon.
Plain Python (geopandas / pyogrio) — no QGIS needed. Run once:

    python make_qgis_assets.py
"""
from pathlib import Path
import pandas as pd
import geopandas as gpd
from pyogrio import write_dataframe

OUT_CRS = "EPSG:6372"   # Mexico ITRF2008 / LCC (metres); AOI source gpkg is 6365 (degrees)
HERE = Path(__file__).parent
GPKG = HERE / "labels.gpkg"
AOI_LOCAL = HERE / "aoi.gpkg"
AOI_SRC = (r"C:\Users\StephaniePatriciaGeo\OneDrive - Global Green Growth "
           r"Institute\Documents\MX40\Geoespacial_compartida\Shapes_COBIOCOM\RecortesCOBIOCOM\EntidadesCOBIOCOM.gpkg")

# field name -> pandas dtype (protocol §6)
SCHEMA = {
    "class_id":     "int32",
    "class_name":   "object",
    "set":          "object",   # 'train' | 'val'
    "state":        "object",   # INEGI CVE_ENT, e.g. '14'
    "source":       "object",   # 'basemap' | 'field' | 'streetview'
    "confidence":   "int32",    # 1..3
    "interpreter":  "object",
    "date_labeled": "object",   # ISO 'YYYY-MM-DD'
    "notes":        "object",
}


def make_labels():
    if GPKG.exists():
        print(f"{GPKG.name} already exists — leaving it untouched.")
        return
    data = {k: pd.Series([], dtype=v) for k, v in SCHEMA.items()}
    gdf = gpd.GeoDataFrame(data, geometry=gpd.GeoSeries([], crs=OUT_CRS))
    write_dataframe(gdf, GPKG, layer="labels", driver="GPKG",
                    geometry_type="MultiPolygon", promote_to_multi=True)
    print(f"created {GPKG.name}  (layer 'labels' | {len(SCHEMA)} fields | {OUT_CRS})")


def make_local_aoi():
    # a LOCAL copy of the boundary so the QGIS project stays portable/bundleable
    if AOI_LOCAL.exists():
        print(f"{AOI_LOCAL.name} already exists — leaving it untouched.")
        return
    if not Path(AOI_SRC).exists():
        print(f"[skip] AOI source not found (fine on a consultant machine): {AOI_SRC}")
        return
    gdf = gpd.read_file(AOI_SRC).to_crs(OUT_CRS)
    write_dataframe(gdf, AOI_LOCAL, layer="aoi", driver="GPKG")
    print(f"created {AOI_LOCAL.name}  (layer 'aoi' | {len(gdf)} states | {OUT_CRS})")


def main():
    make_labels()
    make_local_aoi()


if __name__ == "__main__":
    main()
