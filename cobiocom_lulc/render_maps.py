"""
render_maps.py — 2 composiciones de paisajes agrícolas semiáridos (Altos Norte Jal + N/NE Gto):
  mapa_regiones_nombradas.png  — las 3 regiones nombradas resaltadas
  mapa_altiplano.png           — todo el altiplano semiárido
Base: ESA WorldCover (cobertura) + Frontera Agrícola (temporal/riego) + municipios + Río Laja.
Cada una con localizador de México.
"""
from pathlib import Path
import numpy as np, geopandas as gpd, rasterio
from rasterio.features import rasterize
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Patch, Rectangle

HERE = Path(__file__).resolve().parent
WC_COL = {0: (255, 255, 255), 10: (0, 100, 0), 20: (222, 192, 130), 30: (255, 240, 150),
          40: (240, 150, 255), 50: (250, 60, 60), 60: (190, 180, 165), 80: (0, 110, 200), 90: (0, 150, 160)}
WC_LAB = {10: "Bosque/árbol", 20: "Matorral", 30: "Pastizal", 40: "Agricultura (WorldCover)",
          50: "Urbano", 60: "Suelo desnudo", 80: "Agua"}

with rasterio.open(HERE / "worldcover_region.tif") as s:
    wc = s.read(1); wtr = s.transform; H, W = wc.shape
    ext = [s.bounds.left, s.bounds.right, s.bounds.bottom, s.bounds.top]
rgb = np.full((H, W, 3), 255, "uint8")
for v, c in WC_COL.items():
    rgb[wc == v] = c

munN = gpd.read_file(HERE / "map_base.gpkg", layer="munis_named").to_crs(4326)
munA = gpd.read_file(HERE / "map_base.gpkg", layer="munis_altiplano").to_crs(4326)
fa = gpd.read_file(HERE / "map_base.gpkg", layer="frontera_ag").to_crs(4326)
rios = gpd.read_file(HERE / "map_base.gpkg", layer="rios").to_crs(4326)
try:
    laja = gpd.read_file(HERE / "map_base.gpkg", layer="cuenca_laja").to_crs(4326)
except Exception:
    laja = None
est = gpd.read_file(HERE / "map_base.gpkg", layer="estados").to_crs(4326)
mx = gpd.read_file(HERE / "mexico.gpkg").to_crs(4326)

# Frontera -> raster (1 temporal, 2 riego) para overlay rápido
shp = [(g, 1 if t == "Temporal" else 2) for g, t in zip(fa.geometry, fa["tipo"])]
fr = rasterize(shp, out_shape=(H, W), transform=wtr, fill=0, dtype="uint8")
fa_rgba = np.zeros((H, W, 4), "float32")
fa_rgba[fr == 1] = (0.10, 0.45, 0.10, 0.55)      # temporal (verde)
fa_rgba[fr == 2] = (0.10, 0.30, 0.75, 0.60)      # riego (azul)

REG_COL = {"Altos Norte (Jal)": "#d81b60", "Cuenca Alta Rio Laja (Gto)": "#8e24aa", "Penjamo-Abasolo (Gto)": "#f57c00"}


def locator(fig, bbox):
    ax = fig.add_axes([0.70, 0.08, 0.26, 0.26])
    mx.plot(ax=ax, color="#eeeeee", edgecolor="#888", linewidth=0.5)
    x0, y0, x1, y1 = bbox
    ax.add_patch(Rectangle((x0, y0), x1 - x0, y1 - y0, fill=True, color="#d81b60", alpha=0.85, zorder=5))
    ax.set_xlim(-118, -86); ax.set_ylim(14, 33); ax.set_xticks([]); ax.set_yticks([])
    ax.set_title("Ubicación en México", fontsize=8)


def base(ax, xlim, ylim):
    ax.imshow(rgb, extent=ext, origin="upper", interpolation="nearest")
    ax.imshow(fa_rgba, extent=ext, origin="upper", interpolation="nearest")
    est.boundary.plot(ax=ax, color="#222", linewidth=1.4)
    munA.boundary.plot(ax=ax, color="#444", linewidth=0.4, alpha=0.6)
    rios.plot(ax=ax, color="#1565c0", linewidth=0.8, alpha=0.8)
    if laja is not None:
        laja.boundary.plot(ax=ax, color="#00695c", linewidth=1.6, linestyle="--")
    ax.set_xlim(xlim); ax.set_ylim(ylim); ax.set_xlabel("Longitud"); ax.set_ylabel("Latitud")


LEG = [Patch(fc=np.array(WC_COL[k]) / 255, label=WC_LAB[k]) for k in (20, 30, 10, 60, 50, 80)] + \
      [Patch(fc=(0.10, 0.45, 0.10), alpha=0.6, label="Frontera Agrícola — Temporal"),
       Patch(fc=(0.10, 0.30, 0.75), alpha=0.6, label="Frontera Agrícola — Riego"),
       Patch(fc=np.array(WC_COL[40]) / 255, label="Agricultura (WorldCover)")]

# ---------- Mapa A: regiones nombradas ----------
bN = munN.total_bounds
fig, ax = plt.subplots(figsize=(13, 9))
base(ax, (bN[0] - 0.1, bN[2] + 0.1), (bN[1] - 0.1, bN[3] + 0.1))
for grp, col in REG_COL.items():
    sub = munN[munN["region"] == grp]
    sub.dissolve().boundary.plot(ax=ax, color=col, linewidth=2.6)
    c = sub.dissolve().geometry.representative_point().iloc[0]
    ax.annotate(grp, (c.x, c.y), fontsize=11, weight="bold", color=col, ha="center",
                path_effects=[], bbox=dict(boxstyle="round,pad=0.2", fc="white", ec=col, alpha=0.85))
ax.set_title("Paisajes agrícolas semiáridos — regiones de interés\nAltos Norte (Jalisco) · Cuenca Alta del Río Laja y Pénjamo-Abasolo (Guanajuato)",
             fontsize=13, weight="bold")
ax.legend(handles=LEG, loc="upper left", fontsize=8, framealpha=0.9)
locator(fig, bN)
fig.tight_layout(); fig.savefig(HERE / "mapa_regiones_nombradas.png", dpi=150, bbox_inches="tight")
print("-> mapa_regiones_nombradas.png")

# ---------- Mapa B: altiplano completo ----------
bA = munA.total_bounds
fig, ax = plt.subplots(figsize=(13, 9))
base(ax, (bA[0] - 0.1, bA[2] + 0.1), (bA[1] - 0.1, bA[3] + 0.1))
munA.dissolve().boundary.plot(ax=ax, color="#b71c1c", linewidth=2.6)
ax.set_title("Altiplano semiárido agrícola — Altos de Jalisco y norte/noreste de Guanajuato",
             fontsize=13, weight="bold")
ax.legend(handles=LEG, loc="upper left", fontsize=8, framealpha=0.9)
locator(fig, bA)
fig.tight_layout(); fig.savefig(HERE / "mapa_altiplano.png", dpi=150, bbox_inches="tight")
print("-> mapa_altiplano.png")
