"""Sondea Google Earth Engine en busca de versiones más recientes de los
datasets anuales versionados (Hansen GFC y JRC TMF) y actualiza
modules/dataset_versions.json si encuentra algo más nuevo.

Se ejecuta desde el workflow update-datasets.yml. Requiere las variables de
entorno GEE_SA_KEY (JSON del service account) y GEE_PROJECT.
"""
import os
import json
import datetime
import ee

SA_KEY = os.environ.get("GEE_SA_KEY", "").strip()
PROJECT = os.environ.get("GEE_PROJECT", "ee-stephaniegeorge").strip()

if not SA_KEY:
    raise SystemExit("Falta GEE_SA_KEY (secreto del repositorio).")

key_dict = json.loads(SA_KEY)
credentials = ee.ServiceAccountCredentials(key_dict["client_email"], key_data=SA_KEY)
ee.Initialize(credentials=credentials, project=PROJECT)

CONFIG_PATH = os.path.join("modules", "dataset_versions.json")
with open(CONFIG_PATH, encoding="utf-8") as f:
    config = json.load(f)


def asset_exists(asset_id):
    try:
        ee.data.getAsset(asset_id)
        return True
    except Exception:
        return False


this_year = datetime.date.today().year

# ── Hansen Global Forest Change ──────────────────────────────────────────────
# Patrón observado: global_forest_change_{Y}_v1_{Y-2012}
# (2023->v1_11, 2024->v1_12, 2025->v1_13). Probamos algunos sufijos alrededor
# del esperado por si UMD altera la numeración.
best_hansen = config.get("hansen_asset")
found = False
for y in range(this_year + 1, 2018, -1):
    expected = y - 2012
    for v in (expected + 1, expected, expected - 1):
        if v < 1:
            continue
        cand = f"UMD/hansen/global_forest_change_{y}_v1_{v}"
        if asset_exists(cand):
            best_hansen = cand
            found = True
            break
    if found:
        break

# ── JRC TMF AnnualChanges ────────────────────────────────────────────────────
best_jrc = int(config.get("jrc_tmf_year", 2023))
for y in range(this_year, best_jrc, -1):
    if asset_exists(f"projects/JRC/TMF/v1_{y}/AnnualChanges"):
        best_jrc = y
        break

# ── Guardar si cambió ────────────────────────────────────────────────────────
changed = False
if best_hansen and best_hansen != config.get("hansen_asset"):
    print(f"Hansen: {config.get('hansen_asset')} -> {best_hansen}")
    config["hansen_asset"] = best_hansen
    changed = True
if best_jrc != config.get("jrc_tmf_year"):
    print(f"JRC TMF: v1_{config.get('jrc_tmf_year')} -> v1_{best_jrc}")
    config["jrc_tmf_year"] = best_jrc
    changed = True

if changed:
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2, ensure_ascii=False)
        f.write("\n")
    print("Config actualizada.")
else:
    print("Sin versiones nuevas. Config sin cambios:", config)
