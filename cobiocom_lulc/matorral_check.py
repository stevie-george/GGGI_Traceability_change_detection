"""
matorral_check.py — ¿todos entienden lo mismo por 'matorral'?
Desglosa el matorral POR CONSULTOR (Tona/Mau/Rodrigo, todas las entregas) vs SEMADET (KMZ),
compara ubicación y firma espectral, imprime tabla y genera la lámina matorral_lamina.png.
"""
from pathlib import Path
import numpy as np
import pandas as pd
import geopandas as gpd
import rasterio
from rasterio.windows import from_bounds, Window
from rasterio.features import geometry_mask
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE = Path(r"C:\Users\StephaniePatriciaGeo\Documents\deforestation_alert\cobiocom_lulc")
GEO = Path(r"C:\Users\StephaniePatriciaGeo\OneDrive - Global Green Growth Institute\Documents\MX40\Geoespacial_compartida")
SEM = GEO / "Muestras/SEMADET"
OUT = HERE / "out"
CRS = "EPSG:6372"
WANT = ["green_NDVI", "green_NDMI", "green_BSI"]

lab = gpd.read_file(HERE / "labels_merged.gpkg", layer="labels")
B3 = {"tona": GEO / "Muestras/Entrenamiento/Photointerpretation_05_10_2026/Labels_C3.gpkg",
      "mau": GEO / "Muestras/Entrenamiento/Mau_05_10_2026/labels_mau_b3.gpkg"}


def consultant_mat(who):
    parts = [lab[(lab["src_file"] == who) & (lab["class_id"] == 3)][["geometry"]].to_crs(CRS)]
    if who in B3:
        g = gpd.read_file(B3[who]); g["class_id"] = pd.to_numeric(g["class_id"], errors="coerce")
        parts.append(g[g["class_id"] == 3][["geometry"]].to_crs(CRS))
    return gpd.GeoDataFrame(pd.concat(parts, ignore_index=True), geometry="geometry", crs=CRS)


sem = pd.concat([gpd.read_file(SEM / f)[["geometry"]].to_crs(CRS) for f in
                 ["Muestra-matorral.kmz", "muestras Matorral Mariela.kmz", "MuestrasMatorral.kmz"]],
                ignore_index=True)
srcs = {
    "SEMADET (KMZ)": gpd.GeoDataFrame(sem, geometry="geometry", crs=CRS),
    "Tona": consultant_mat("tona"),
    "Mau": consultant_mat("mau"),
    "Rodrigo": consultant_mat("rodrigo"),
    "Pastizal (ref)": lab[lab["class_id"] == 4][["geometry"]].to_crs(CRS),
}
srcs = {k: v for k, v in srcs.items() if len(v) > 0}

grid = gpd.read_file(HERE / "tile_grid.gpkg").to_crs(CRS)
if "tile_id" not in grid.columns:
    grid = grid.rename(columns={grid.columns[0]: "tile_id"})


def band_names(tile):
    fp = OUT / tile / f"{tile}_bands.txt"
    return [ln.split("\t")[1] for ln in fp.read_text(encoding="utf-8").splitlines() if "\t" in ln]


def sample_src(g):
    rp = gpd.GeoDataFrame(geometry=g.representative_point(), crs=CRS)
    tiles = gpd.sjoin(rp, grid[["tile_id", "geometry"]], how="left", predicate="within")["tile_id"].values
    vals = {b: [] for b in WANT}; elev = []
    for geom, tile in zip(g.geometry, tiles):
        if not isinstance(tile, str) or not (OUT / tile / f"{tile}_features.tif").exists():
            continue
        names = band_names(tile); got = [b for b in WANT if b in names]
        idx = [names.index(b) + 1 for b in got]
        with rasterio.open(OUT / tile / f"{tile}_features.tif") as s:
            win = from_bounds(*geom.bounds, transform=s.transform).round_offsets().round_lengths()
            win = win.intersection(Window(0, 0, s.width, s.height))
            if win.width < 1 or win.height < 1:
                continue
            arr = s.read(idx, window=win).astype("float32")
            m = geometry_mask([geom], out_shape=arr.shape[1:], transform=s.window_transform(win), invert=True)
            for bi, b in enumerate(got):
                v = arr[bi][m]; vals[b].extend(v[~np.isnan(v)].tolist())
        dp = OUT / tile / f"{tile}_dem.tif"
        if dp.exists():
            with rasterio.open(dp) as d:
                win = from_bounds(*geom.bounds, transform=d.transform).round_offsets().round_lengths()
                win = win.intersection(Window(0, 0, d.width, d.height))
                if win.width >= 1 and win.height >= 1:
                    a = d.read(1, window=win).astype("float32")
                    m = geometry_mask([geom], out_shape=a.shape, transform=d.window_transform(win), invert=True)
                    vv = a[m]; elev.extend(vv[~np.isnan(vv)].tolist())
    return vals, elev


stats = {}
print(f"{'fuente':16s} {'n':>4} {'elev_m':>7} " + "".join(f"{b:>12s}" for b in WANT))
print("-" * 70)
for k, g in srcs.items():
    vals, elev = sample_src(g)
    med = {b: (np.median(vals[b]) if vals[b] else np.nan) for b in WANT}
    e = np.median(elev) if elev else np.nan
    cen = g.to_crs(4326).representative_point()
    stats[k] = dict(n=len(g), elev=e, med=med, lon=cen.x.values, lat=cen.y.values)
    print(f"{k:16s} {len(g):>4} {e:>7.0f} " + "".join(f"{med[b]:>12.3f}" for b in WANT))

# ---------- LÁMINA ----------
COL = {"SEMADET (KMZ)": "#8e24aa", "Tona": "#1565c0", "Mau": "#2e7d32",
       "Rodrigo": "#ef6c00", "Pastizal (ref)": "#9e9e9e"}
keys = list(stats.keys())
fig, (axm, axs, axe) = plt.subplots(1, 3, figsize=(17, 5.6))

try:
    aoi = gpd.read_file(HERE / "aoi.gpkg").to_crs(4326)
    aoi.boundary.plot(ax=axm, color="#bbbbbb", linewidth=0.6)
except Exception:
    pass
for k in keys:
    axm.scatter(stats[k]["lon"], stats[k]["lat"], s=28, c=COL.get(k, "k"), label=f"{k} (n={stats[k]['n']})",
                edgecolor="white", linewidth=0.3, alpha=0.9)
axm.set_title("Ubicación de las muestras", fontsize=12, weight="bold")
axm.set_xlabel("Longitud"); axm.set_ylabel("Latitud"); axm.legend(fontsize=8, loc="upper right")

x = np.arange(len(WANT)); w = 0.8 / len(keys)
for i, k in enumerate(keys):
    axs.bar(x + i * w, [stats[k]["med"][b] for b in WANT], w, color=COL.get(k, "k"), label=k)
axs.axhline(0, color="k", linewidth=0.6)
axs.set_xticks(x + 0.4 - w / 2); axs.set_xticklabels(["NDVI\n(verdor)", "NDMI\n(humedad)", "BSI\n(suelo desnudo)"], fontsize=9)
axs.set_title("Firma espectral (mediana, temporada verde)", fontsize=12, weight="bold")
axs.legend(fontsize=8)

axe.bar(range(len(keys)), [stats[k]["elev"] for k in keys], color=[COL.get(k, "k") for k in keys])
axe.set_xticks(range(len(keys))); axe.set_xticklabels(keys, rotation=30, ha="right", fontsize=8)
axe.set_ylabel("metros"); axe.set_title("Elevación (mediana)", fontsize=12, weight="bold")

fig.suptitle("¿Entendemos lo mismo por «matorral»?  SEMADET (xerófilo árido) vs consultores",
             fontsize=14, weight="bold")
fig.text(0.5, 0.005,
         "SEMADET: NDVI bajo, NDMI negativo (seco), BSI positivo (suelo expuesto), ~1900 m (altiplano) = matorral xerófilo (leyenda).  "
         "Consultores: NDVI alto, húmedo, sin suelo expuesto, ~730 m = se parece al PASTIZAL, no a matorral árido.",
         ha="center", fontsize=8.5, style="italic", wrap=True)
fig.tight_layout(rect=[0, 0.03, 1, 0.95])
fig.savefig(HERE / "matorral_lamina.png", dpi=140)
print("\n-> matorral_lamina.png")
