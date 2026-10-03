"""
merge_labels.py — une las etiquetas de los fotointérpretes en una sola capa limpia.

Regla clave: la AUTORIDAD es `class_id` — el nombre de clase se deriva de legend.csv.
Esto corrige de un solo golpe el `class_name` vacío de Mau y el truncado de Rodrigo
("Avocado pl"), y homogeneiza los esquemas ligeramente distintos.

    run_producer.bat merge_labels.py

Salida: labels_merged.gpkg (capa 'labels', EPSG:6372) + reporte por clase.
"""
import csv
from pathlib import Path
import pandas as pd
import geopandas as gpd
from pyogrio import list_layers, write_dataframe

HERE = Path(__file__).resolve().parent
GEO = Path(r"C:\Users\StephaniePatriciaGeo\OneDrive - Global Green Growth "
          r"Institute\Documents\MX40\Geoespacial_compartida")
OUT_CRS = "EPSG:6372"
OUT = HERE / "labels_merged.gpkg"

# (src_file = consultor, batch, ruta). src_file NO lleva el batch para que el filtro
# de Rodrigo en train.py excluya sus dos entregas a la vez.
SOURCES = [
    ("tona",    1, GEO / "Muestras/Entrenamiento/Tona_31_08_26/labels_1.gpkg"),
    ("tona",    2, GEO / "Muestras/Entrenamiento/Tona_23_09_2026/levels_2.gpkg"),
    ("mau",     1, GEO / "Muestras/Entrenamiento/Mau_05_09_2026/labels_mau.gpkg"),
    ("mau",     2, GEO / "Muestras/Entrenamiento/Mau_14_09_2026/labels_mau_b2.gpkg"),
    ("rodrigo", 1, GEO / "Muestras/Entrenamiento/Rodrigo_06_09_2026/labels_Rodrigo.gpkg"),
    ("rodrigo", 2, GEO / "Muestras/Entrenamiento/Rodrigo_20_09_2026/Labels_RMRR.gpkg"),
]
RENAME = {"interprete": "interpreter", "date_label": "date_labeled"}
KEEP = ["class_id", "class_name", "set", "source", "confidence",
        "interpreter", "date_labeled", "notes"]

# class_id -> nombre canónico (legend.csv)
id2name = {}
with open(HERE / "legend.csv", encoding="utf-8") as f:
    for row in csv.DictReader(f):
        namecol = next((c for c in ("name_en", "name", "name_es") if c in row), None)
        id2name[int(row["class_id"])] = row[namecol]

parts = []
for who, batch, f in SOURCES:
    if not f.exists():
        print(f"[omitido] {who} b{batch}: no existe {f}"); continue
    lyr = list_layers(str(f))[0][0]
    g = gpd.read_file(f, layer=lyr).to_crs(OUT_CRS).rename(columns=RENAME)
    g["class_id"] = pd.to_numeric(g["class_id"], errors="coerce")
    n_bad = int(g["class_id"].isna().sum())
    g["class_name"] = g["class_id"].map(lambda i: id2name.get(int(i)) if pd.notna(i) else None)
    if "interpreter" not in g.columns:
        g["interpreter"] = who
    g["interpreter"] = g["interpreter"].fillna(who)
    for c in KEEP:
        if c not in g.columns:
            g[c] = None
    g["src_file"] = who
    g["batch"] = batch
    print(f"{who:8s} b{batch}: {len(g):4d} polígonos | class_id inválidos/fuera de leyenda: {n_bad}")
    parts.append(g[KEEP + ["src_file", "batch", "geometry"]])

merged = gpd.GeoDataFrame(pd.concat(parts, ignore_index=True), crs=OUT_CRS)
merged = merged[merged["class_name"].notna()].reset_index(drop=True)
n_raw = len(merged)

# --- limpieza: quitar duplicados, asignar tile_id, descartar lo que cae fuera del grid ---
grid = gpd.read_file(HERE / "tile_grid.gpkg").to_crs(OUT_CRS)
dups = int(merged.geometry.duplicated(keep="first").sum())
merged = merged[~merged.geometry.duplicated(keep="first")].reset_index(drop=True)
rp = merged.copy(); rp["geometry"] = merged.geometry.representative_point()
merged["tile_id"] = gpd.sjoin(rp, grid[["tile_id", "geometry"]], how="left",
                              predicate="within")["tile_id"].values
outside = merged["tile_id"].isna()
print("===== LIMPIEZA =====")
print(f"  crudo {n_raw} | duplicados quitados {dups} | fuera del grid {int(outside.sum())}")
for who in sorted(merged["src_file"].unique()):
    m = merged["src_file"] == who
    print(f"    {who}: fuera del grid {int((m & outside).sum())}")
merged = merged[~outside].reset_index(drop=True)

write_dataframe(merged, OUT, layer="labels", driver="GPKG",
                geometry_type="MultiPolygon", promote_to_multi=True)

merged["ha"] = merged.geometry.area / 1e4
rep = (merged.groupby("class_name")
       .agg(poligonos=("geometry", "size"), ha=("ha", "sum"),
            intérpretes=("src_file", "nunique"))
       .round(1).sort_values("poligonos", ascending=False))
print("\n===== CAPA UNIDA (limpia) -> labels_merged.gpkg =====")
print(rep.to_string())
avo = int(rep.index.to_series().str.contains("vocado", case=False).mul(rep["poligonos"]).sum())
print(f"\nTOTAL válidos: {len(merged)} | AGUACATE (positivos): {avo} | NO-aguacate: {len(merged) - avo}")
