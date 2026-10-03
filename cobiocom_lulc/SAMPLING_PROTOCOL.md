# COBIOCOM — Sampling Protocol for Land-Cover Classification

**Area:** 8 states of the COBIOCOM corridor (Aguascalientes, Colima, Guanajuato,
Jalisco, Michoacán, Nayarit, San Luis Potosí, Zacatecas) — ≈ 34.4 Mha.
*(AOI under review: the 8 full states = 34.4 Mha vs. the COBIOCOM corridor polygon
`COBIOCOM_2022` = 15.2 Mha used by the phase‑2 validation — pick one so the map and
its validation share a domain.)*
**Reference imagery:** Sentinel-2 L2A dual-season median composites (green +
dry) with true-colour / CIR / SWIR renders and NDVI, dNDVI, NDMI, EVI, NDRE, BSI.
**Method:** manual polygon labelling → Random Forest / LightGBM classification.
**Legend:** see [`legend.csv`](legend.csv) (12 classes; edit before you start).

The goal of this protocol is a labelled dataset that is (a) **representative** of
each class across the whole corridor and (b) **statistically valid** for
accuracy assessment. Read §2 before drawing a single polygon.

> **Two phases.** This protocol is **phase 1 — training** (labelling samples to *fit*
> the classifier). Accuracy and area estimation are a **separate phase‑2 validation**
> in Collect Earth (`Diseno_muestreo_COBIOCOM.docx` + `generar_muestras_collectearth.py`),
> an independent Olofsson/GFOI probability sample. Use the **same legend and mapping
> year (T2)** in both so the validation applies to this map.
>
> **Why this map:** it is the land‑use *attribution* layer for the deforestation tool —
> avocado & agave are intersected with the Hansen/JRC/GLAD alert consensus to flag loss
> **inside or next to** plantations, and *Bare / recently cleared* is a direct cross‑check
> on fresh conversion.

---

## 1. Class legend

Use the 12 classes in `legend.csv`. Two design choices worth confirming:

- **"Forest" is split** into *temperate forest* and *tropical dry forest*.
  They have opposite dry-season behaviour (evergreen vs. leaf-off) and dry
  forest otherwise gets confused with agriculture/agave. Keeping them separate
  is also what lets you measure avocado-driven loss of *temperate* forest.
- **Five classes were added** to absorb land that would otherwise contaminate
  your target classes: *shrubland/matorral*, *grassland/pastizal*,
  *protected agriculture*, *bare soil*, and the dry-forest split above.

**Hierarchical option.** Map at the 12 classes, but you can collapse *temperate +
tropical dry forest* → one **Forest** class for reporting and to match the phase‑2
validation legend (which uses a single forest class): fine level for the map, coarse
level for area statistics.

If you want a lighter first pass, the *minimum viable* legend is: temperate
forest, dry forest, shrubland, grassland, avocado, agave, other perennial,
annual cropland, urban, bare, water (merge "protected agriculture" into urban
or annual cropland). Do **not** drop bare/grassland/shrubland — those are the
big-area classes that wreck accuracy when missing.

---

## 2. Sampling design (the rules that matter)

1. **Two independent sets.** Keep **training** and **validation** polygons
   separate. Training may be purposive (you pick clear examples); **validation
   must be a probability sample** (stratified random) so accuracy is unbiased
   (Olofsson et al. 2014, *good practices*). Never compute accuracy on training
   polygons.
2. **Stratify by class *and* by region.** Collect samples for every class in
   **each ecoregion it occurs in** — altiplano (Zac/SLP/Ags), Bajío
   (Gto/Jal), occidente coastal (Nay/Col/Mich), and the Eje Neovolcánico
   highlands. A class trained in only one state will misclassify elsewhere.
3. **Spatial independence.** Do not place training and validation polygons in
   the same field/patch, and avoid pixels that straddle both sets — adjacent
   pixels are correlated and will inflate accuracy.
4. **Temporal consistency.** Every label must be valid for the mapping year and
   interpreted using **both** seasons. A field that is bare in the dry composite
   and green in the wet composite is still *annual cropland*, not bare soil.

---

## 3. Sample sizes

**Training polygons** (each **homogeneous**, interior to a patch, **≥ 3×3
pixels ≈ 30 m**, spread across all states where the class occurs):

| Class | Min. training polygons |
|---|---|
| Avocado, Agave *(oversample — rare & high-interest)* | 100–150 each |
| Temperate forest, Dry forest, Shrubland, Grassland, Annual cropland *(large & variable)* | 100–150 each |
| Other perennial crop | 80–120 |
| Urban, Protected agriculture, Bare soil, Water *(distinctive)* | 40–60 each |

**Validation points** — do **not** draw these here. Accuracy and area estimation are
the **phase‑2 Collect Earth exercise** (`Diseno_muestreo_COBIOCOM.docx` +
`generar_muestras_collectearth.py`): an independent Olofsson probability sample sized
by target SE of overall accuracy — **S(Ô)=0.015 → ~575 plots** or **S(Ô)=0.010 →
~1,288**, a **floor of 50 per rare class**, the rest area‑proportional — analysed with
area‑adjusted estimators and 95 % CIs. Keep the **same legend and mapping year (T2)**
so it applies to this map.

---

## 4. Interpretation keys (what to look for)

Label on the **dual-season** renders + indices, cross-checked against
**very-high-resolution basemaps** (Esri/Google/Bing/Planet) for texture and
Google Street View for roadside checks. Use known production zones as priors
(DO Tequila / Los Altos for agave; the Michoacán–Jalisco avocado belt).

| Class | Best layers | Diagnostic cues |
|---|---|---|
| **Avocado** | SWIR + dNDVI + NDMI + VHR | Dense **dark-green evergreen**; **low dNDVI** (green in dry season while oak browns); **high NDMI** (irrigated); orchard **rows** & terraces on slopes at VHR; reservoirs (*ollas*) nearby. |
| **Agave** | SWIR + BSI + VHR | Blue-grey rosettes in **rows** with wide **bare inter-row** (red soil) → **high BSI**, low–mid NDVI; strong geometric texture; **stable** across seasons. |
| **Other perennial** | NDRE + phenology + VHR | Tree/bush rows (citrus, mango, open berry); greener/wetter than agave, less evergreen-uniform than avocado. |
| **Temperate forest** | CIR + dNDVI + VHR | Rugged sierra, **rough natural texture, no rows**; conifer evergreen, oak semi-deciduous. |
| **Dry forest** | dNDVI (green−dry) | **Very high dNDVI** — green in wet, leaf-off in dry; low–mid elevation coastal ranges. |
| **Shrubland/Matorral** | dry NDVI + BSI | Sparse, **low NDVI both seasons**, altiplano. |
| **Grassland/Pastizal** | dNDVI | Herbaceous, strong wet-season green-up, low structure; often fenced parcels. |
| **Annual cropland** | dNDVI + TRUE | Geometric fields, **bare↔green** phenology, irrigation districts / center pivots; sugarcane in Nay/Jal/Col lowlands. |
| **Protected agriculture** | TRUE (visible) | **Very bright white/blue** plastic/mesh; extreme visible reflectance; geometric blocks. |
| **Urban/Settlement** | TRUE + NDBI | Bright/grey, geometric, low NDVI both seasons. |
| **Bare soil** | BSI + NDVI | **High BSI**, low NDVI both seasons; fallow, quarries, dry lakebeds. |
| **Water** | MNDWI | Dark in NIR, **high MNDWI**; reservoirs shrink in dry season. |

> **Hardest pair: avocado vs. temperate forest.** Both are dense evergreen
> canopy. Lean on **dNDVI** (avocado stays green), **NDMI** (irrigation), and
> **row texture** at VHR. At 10 m this pair may still need texture (GLCM) or
> Sentinel-1 backscatter features — flag ambiguous polygons with `confidence=1`.

---

## 5. Digitising rules

- One class per polygon; **homogeneous interior only**; keep ≥ 30 m from patch
  edges to avoid mixed pixels.
- Avoid any pixel that is cloud/shadow in the composite (check both seasons).
- Digitise at native 10 m scale; do not trace tiny slivers.
- Spread polygons across the class's full geographic and spectral range.

---

## 6. Attribute schema — GeoPackage layer `labels` (CRS EPSG:6372, metres)

| Field | Type | Notes |
|---|---|---|
| `class_id` | int | matches `legend.csv` |
| `class_name` | text | for readability |
| `set` | text | `train` or `val` |
| `state` | text | INEGI `CVE_ENT` (e.g. `14`) |
| `source` | text | `basemap` / `field` / `streetview` |
| `confidence` | int | 1 (low) – 3 (high) |
| `interpreter` | text | initials |
| `date_labeled` | date | ISO `YYYY-MM-DD` |
| `notes` | text | free text |

---

## 7. QA / QC

- Second-interpreter review of **≥ 10 %** of polygons **and all** avocado/agave;
  resolve disagreements before use.
- Drop `confidence = 1` polygons from **training** (keep flagged for review).
- Spectral-outlier check per class (a forest polygon with cropland phenology is
  probably mislabelled).
- Confirm every class has samples in every state where it occurs.

---

## 8. Workflow

1. Run `s2_export.py` → per-tile renders + NDVI/dNDVI (COGs).
2. Load them in **QGIS** (heavy digitising) or a **Jupyter + leafmap /
   localtileserver** map (in-notebook); optionally build a VRT mosaic per render.
3. Create the `labels` GeoPackage with the schema above; digitise per class per
   region; QA per §7.
4. `sample.py` extracts feature-stack values under the polygons → training table.
5. `train.py` fits RF/LightGBM with a spatially-separated hold-out.
6. `infer.py` classifies each tile block-wise and mosaics the result.
7. Accuracy report: confusion matrix, overall / producer's / user's accuracy,
   and **area-adjusted** estimates with confidence intervals (Olofsson 2014).

---

*Reference: Olofsson, P. et al. (2014). "Good practices for estimating area and
assessing accuracy of land change." Remote Sensing of Environment 148, 42–57.*
