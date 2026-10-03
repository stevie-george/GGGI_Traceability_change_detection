"""
add_tiles.py — add NEW Sentinel-2 tiles into the project you ALREADY have open,
without recreating or replacing anything.

After unzipping a tile update into your project folder, open your project, then in the
QGIS Python Console (Complementos -> Consola de Python) paste and press Enter:

    exec(open(r'add_tiles.py').read())        # use the full path to this file if needed

It scans out/ and adds a styled, grouped layer set for each tile that isn't already in
the project. Tiles you already have, your labels, and your layout are left untouched.
Save the project (Ctrl+S) afterwards to keep the new tiles.
"""
from pathlib import Path
from qgis.core import QgsProject, QgsRasterLayer

proj = QgsProject.instance()
home = proj.homePath()
if not home:
    raise RuntimeError("Open your saved cobiocom_labeling.qgz first, then run this.")

out = Path(home) / "out"
root = proj.layerTreeRoot()
grp = root.findGroup("Sentinel-2 renders") or root.addGroup("Sentinel-2 renders")
have = {c.name() for c in grp.children()}

added = 0
for td in sorted(d for d in out.glob("*") if d.is_dir()):
    if td.name in have:                      # already in the project -> skip
        continue
    tg = grp.addGroup(td.name)
    for season in ("dry", "green"):
        for r in ("SWIR", "CIR", "TRUE", "NDVI"):
            p = td / f"{td.name}_{season}_{r}.tif"
            if p.exists():
                lyr = QgsRasterLayer(str(p), f"{season} {r}")
                if lyr.isValid():
                    proj.addMapLayer(lyr, False)
                    tg.addLayer(lyr).setItemVisibilityChecked(season == "dry" and r == "SWIR")
    dd = td / f"{td.name}_dNDVI.tif"
    if dd.exists():
        lyr = QgsRasterLayer(str(dd), "dNDVI")
        if lyr.isValid():
            proj.addMapLayer(lyr, False)
            tg.addLayer(lyr).setItemVisibilityChecked(False)
    added += 1

print(f"added {added} new tile(s) to the open project - Ctrl+S to save (labels untouched)")
