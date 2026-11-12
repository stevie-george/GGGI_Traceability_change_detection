# COBIOCOM · Jalisco — Workshop Quickstart (ROI collection in GEE)

Companion to [`jalisco_workshop_roi.js`](jalisco_workshop_roi.js). Goal of the session:
participants draw training ROIs for the **hard classes** (avocado, agave, other crops) on a
cloud‑free multi‑season Sentinel‑2 reference, while the **easy classes** are auto‑seeded.
The ROIs export as geometries that feed the **local** Python classifier — no heavy GEE compute.

---

## A. Facilitator prep — do these BEFORE the workshop

1. **Earth Engine accounts (lead time!).** Every participant needs a Google account
   **registered for Earth Engine** at <https://code.earthengine.google.com>. Approval is not
   always instant — send the signup link **several days ahead** and confirm everyone can open
   the Code Editor.
2. **VHR basemap = Google Satellite (free).** GEE's built‑in satellite basemap is the high‑res
   aid for the workshop — no signup, no key needed. *The old free **Planet NICFI** program has
   ended; it's now the paid **Tropical Forest Observatory** (~$180 USD/mo, single‑user). The GEE
   `projects/planet-nicfi/...` layer is commented out and optional — the S2 layers + Google VHR
   are all participants need.*
3. **Upload the boundary as an asset.** In the Code Editor → *Assets* → *New* → *Shape upload*,
   upload `EntidadesCOBIOCOM_shp.zip` (the WGS84 shapefile). Set the script's `ASSET_ID` to its
   path (default assumes `projects/ee-stephaniegeorge/assets/EntidadesCOBIOCOM`). *(This is the
   one place that shapefile zip is needed — GEE can't ingest the GeoPackage.)*
4. **Share the script.** Save it, then *Get Link* (or share via a shared repo) so everyone opens
   the **same** script. Do a dry run: confirm layers 1–6 render over Jalisco.
5. **Skim the legend & cues** with the group from
   [`../SAMPLING_PROTOCOL.md`](../SAMPLING_PROTOCOL.md) §4 — especially avocado vs. temperate
   forest, and agave's bare inter‑row signature.

## B. Participant steps — during the session

1. Open the shared script → **Run**. Center on Jalisco; toggle layers 1–6
   (RGB seca/lluvias, falso color NIR, **SWIR**, dNDVI) and NICFI/VHR.
2. For each crop class, create a geometry import: **gear icon → Import as `FeatureCollection`**,
   name it **exactly** `avocado`, `agave`, `other_crop`, `protected_ag`, or `annual_ag`.
3. **Draw pure polygons** well inside homogeneous stands (avoid edges/roads). Cross‑check
   **SWIR + dNDVI + NICFI** before committing avocado/agave.
4. **Uncomment** the matching `manualParts.merge(label(...))` line in §7 as you add each import.
5. Re‑run to see your polygon count. Aim for the per‑class targets in the protocol (§3), spread
   across Jalisco (Los Altos, coast, sierra).

## C. Facilitator — after the session

1. Set `RUN_PREVIEW = true` to show a quick Random Forest + confusion matrix — a live look at
   which classes still collide (add samples where they do). *(Preview only; the real model is local.)*
2. Run the three **Exports** (Tasks tab): `_manual_polys`, `_auto_points`, `_cropland_candidates`
   (SHP → Drive folder `COBIOCOM`, plus the manual‑polys asset).
3. Optionally relabel `_cropland_candidates` in QGIS into classes 5–9 and keep them.
4. Hand the exported SHPs to the local pipeline: they'll be re‑sampled against the local
   Sentinel‑2 composites (`s2_export.py --states 14`) — **not** GEE band values — so features
   stay consistent with the classifier.

---

**Why GEE for this and not QGIS:** for a multi‑person workshop, GEE loads the S2 composites +
indices + NICFI + VHR **instantly and identically for everyone, with zero install**. The rigorous
in‑house set is still better done in QGIS (full attribute schema); both feed the same local model.
