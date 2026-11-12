"""Trae WorldCover (cropland) recortado a la región + contorno de México (Natural Earth)."""
import numpy as np, rasterio, geopandas as gpd
from rasterio.warp import reproject, Resampling
from rasterio.transform import from_bounds
from pathlib import Path

HERE = Path(__file__).resolve().parent
BBOX = [-102.92, 20.09, -99.57, 22.13]          # región + margen (lon/lat)
RES = 0.0015                                     # ~150 m para figura/QGIS ligero
WC_URL = "https://esa-worldcover.s3.eu-central-1.amazonaws.com/v200/2021/map/ESA_WorldCover_10m_2021_v200_{t}_Map.tif"
TILES = ["N18W105", "N18W102", "N21W105", "N21W102"]

minx, miny, maxx, maxy = BBOX
W, H = int((maxx - minx) / RES), int((maxy - miny) / RES)
dst_tr = from_bounds(minx, miny, maxx, maxy, W, H)
mosaic = np.zeros((H, W), "uint8")
for t in TILES:
    try:
        with rasterio.open(WC_URL.format(t=t)) as src:
            tmp = np.zeros((H, W), "uint8")
            reproject(rasterio.band(src, 1), tmp, dst_transform=dst_tr, dst_crs="EPSG:4326",
                      src_crs=src.crs, resampling=Resampling.nearest)
            mosaic = np.where(tmp > 0, tmp, mosaic)
        print(f"  WorldCover {t}: ok")
    except Exception as e:
        print(f"  WorldCover {t}: {repr(e)[:80]}")

prof = {"driver": "GTiff", "height": H, "width": W, "count": 1, "dtype": "uint8", "nodata": 0,
        "crs": "EPSG:4326", "transform": dst_tr, "compress": "ZSTD"}
with rasterio.open(HERE / "worldcover_region.tif", "w", **prof) as o:
    o.write(mosaic, 1)
crop = (mosaic == 40).astype("uint8")            # 40 = Cropland (WorldCover v200)
with rasterio.open(HERE / "worldcover_cropland.tif", "w", **prof) as o:
    o.write(crop, 1)
print(f"WorldCover -> worldcover_region.tif (clases) + worldcover_cropland.tif | cropland {100*crop.mean():.0f}% del bbox")

# --- México (Natural Earth admin0) para el localizador ---
try:
    mx = gpd.read_file("/vsicurl/https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master/geojson/ne_50m_admin_0_countries.geojson")
    col = next((c for c in mx.columns if c.upper() in ("ADMIN", "NAME", "SOVEREIGNT")), None)
    mxs = mx[mx[col].astype(str).str.contains("Mexico", case=False, na=False)][["geometry"]]
    mxs.to_file(HERE / "mexico.gpkg", layer="mexico", driver="GPKG")
    print(f"México -> mexico.gpkg ({len(mxs)} geom)")
except Exception as e:
    print(f"México: ERROR {repr(e)[:120]}")
