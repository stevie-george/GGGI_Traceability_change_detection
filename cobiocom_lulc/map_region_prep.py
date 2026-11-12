"""
map_region_prep.py — base para el mapa de paisajes agrícolas semiáridos
(Altos Norte Jalisco + N/NE Guanajuato). Arma map_base.gpkg con municipios, cuenca,
ríos, estados y Frontera Agrícola (temporal/riego) recortada a la región.
"""
import io, unicodedata, zipfile
from pathlib import Path
import pandas as pd
import geopandas as gpd

HERE = Path(__file__).resolve().parent
GEO = Path(r"C:\Users\StephaniePatriciaGeo\OneDrive - Global Green Growth Institute\Documents\MX40\Geoespacial_compartida")
SH = GEO / "Shapes_COBIOCOM" / "RecortesCOBIOCOM"
CRS = "EPSG:6372"
SCR = Path(r"C:\Users\STEPHA~1\AppData\Local\Temp\claude\C--Users-StephaniePatriciaGeo-Documents-deforestation-alert\0bc1a772-ac32-430d-94f8-b72814ba6d9c\scratchpad\frontera2")


def norm(s):
    return "".join(c for c in unicodedata.normalize("NFD", str(s)) if unicodedata.category(c) != "Mn").lower().strip()


NAMED = {
    "Altos Norte (Jal)": ["Lagos de Moreno", "Encarnacion de Diaz", "Ojuelos de Jalisco", "Union de San Antonio"],
    "Cuenca Alta Rio Laja (Gto)": ["Dolores Hidalgo Cuna de la Independencia Nacional", "San Miguel de Allende",
                                    "San Diego de la Union", "San Luis de la Paz", "San Felipe", "Ocampo"],
    "Penjamo-Abasolo (Gto)": ["Penjamo", "Abasolo"],
}
ALTIPLANO_EXTRA_JAL = ["San Juan de los Lagos", "Villa Hidalgo", "San Diego de Alejandria", "Teocaltiche",
                       "San Julian", "Jalostotitlan", "San Miguel el Alto", "Valle de Guadalupe", "Arandas"]
ALTIPLANO_EXTRA_GTO = ["San Jose Iturbide", "Doctor Mora", "Victoria", "Xichu", "Atarjea", "Tierra Blanca", "Comonfort"]

named_norm = {grp: [norm(m) for m in ms] for grp, ms in NAMED.items()}
alt_norm = set(sum(named_norm.values(), [])) | {norm(m) for m in ALTIPLANO_EXTRA_JAL + ALTIPLANO_EXTRA_GTO}

mun = gpd.read_file(SH / "MunCOBIOCOM.gpkg").to_crs(CRS)
mun = mun[mun["CVE_ENT"].astype(str).str.zfill(2).isin(["14", "11"])].copy()
mun["n"] = mun["NOMGEO"].map(norm)
mun["region"] = None
for grp, ms in named_norm.items():
    mun.loc[mun["n"].isin(ms), "region"] = grp
named = mun[mun["region"].notna()].copy()
alti = mun[mun["n"].isin(alt_norm)].copy()
print(f"municipios nombrados: {len(named)} | altiplano: {len(alti)}")
for grp in NAMED:
    print(f"  {grp}: {sorted(named[named['region']==grp]['NOMGEO'])}")

cu = gpd.read_file(SH / "Cuencas.gpkg").to_crs(CRS)
laja = cu[cu["CUENCA"].astype(str).str.contains("Laja", case=False, na=False)]
rios = gpd.read_file(SH / "Ríos.gpkg").to_crs(CRS)
est = gpd.read_file(SH / "EntidadesCOBIOCOM.gpkg").to_crs(CRS)

# recorte = unión de municipios del altiplano (superset)
clip_geom = alti.union_all() if hasattr(alti, "union_all") else alti.unary_union
rios_r = gpd.clip(rios, clip_geom)
laja_r = gpd.clip(laja, clip_geom) if len(laja) else laja

# --- Frontera Agrícola Jal + Gto, recortada a la región ---
SCR.mkdir(parents=True, exist_ok=True)
reps = gpd.GeoDataFrame(geometry=alti.representative_point().values, crs=CRS)  # no se usa; placeholder
fa_parts = []
for inner in ("Jalisco_Serie_IV.zip", "Guanajuato_Serie_IV.zip"):
    with zipfile.ZipFile(GEO / "Descargas_datos_clasificacion/FronteraAgricola_SIV.zip") as zf:
        data = zf.read(inner)
    dest = SCR / inner.replace(".zip", ""); dest.mkdir(exist_ok=True)
    with zipfile.ZipFile(io.BytesIO(data)) as iz:
        iz.extractall(dest)
    shp = list(dest.rglob("*.shp"))[0]
    fa = gpd.read_file(shp).to_crs(CRS)
    rp = gpd.GeoDataFrame(geometry=fa.representative_point(), crs=CRS); rp["ix"] = range(len(fa))
    hit = gpd.sjoin(rp, alti[["geometry"]], predicate="within", how="inner")["ix"].unique()
    keep = fa.iloc[sorted(set(hit))].copy()
    agr = next((c for c in keep.columns if c.upper().startswith("MOD_AGR")), None)
    keep["tipo"] = keep[agr].map({"T": "Temporal", "R": "Riego"}).fillna("Agrícola") if agr else "Agrícola"
    keep = keep[["tipo", "geometry"]]
    print(f"  Frontera {inner.split('_')[0]}: {len(keep)} parcelas en la región")
    fa_parts.append(keep)
fa = gpd.GeoDataFrame(pd.concat(fa_parts, ignore_index=True), crs=CRS)

out = HERE / "map_base.gpkg"
named.drop(columns="n").to_file(out, layer="munis_named", driver="GPKG")
alti.drop(columns=["n", "region"]).to_file(out, layer="munis_altiplano", driver="GPKG")
if len(laja_r):
    laja_r.to_file(out, layer="cuenca_laja", driver="GPKG")
rios_r.to_file(out, layer="rios", driver="GPKG")
est.to_file(out, layer="estados", driver="GPKG")
fa.to_file(out, layer="frontera_ag", driver="GPKG")
b = alti.to_crs(4326).total_bounds
print(f"\n-> map_base.gpkg | extent región (lon/lat): {[round(x,2) for x in b]}")
