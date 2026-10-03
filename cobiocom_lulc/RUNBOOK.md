# COBIOCOM LULC — Runbook (ejercicio repetible)

Clasificación supervisada de uso/cobertura de suelo (aguacate, agave, bosque, etc.) en el
corredor COBIOCOM (8 estados, Jalisco primero). **Dos fases:** RandomForest por píxel (Fase 1)
→ CNN con contexto espacial (Fase 2). El modelo clasifica *todos* los tiles; solo se etiqueta
una **muestra**.

> **Modelo OFICIAL actual: `entrenamientos/entrenamiento_04/`** (10 clases agrupadas + DEM,
> 2 temporadas). Exactitud espacial OOF 0.641; aguacate P 0.84. El `rf_model.pkl` en la raíz
> apunta a este. Ver `entrenamientos/` para todas las versiones (00…05).

## 0. Entorno

Todo se corre con **`run_producer.bat <script.py> [args]`** (activa el env conda `cobiocom`
con un PATH limpio para que GDAL 3.12 no choque con la base de Anaconda). Datos en SSD vía la
junction `out/` → `F:\Traceability\MX40\Data\Sentinel2\...`.

## 1. Datos de tiles (Fase 0)

```bat
REM grid de la muestra por estado (ver MASTER_PLAN.md / plan_all_states.csv)
run_producer.bat plan_sample.py --dump

REM generar tiles de un estado (Jalisco=14; otros llevan prefijo <CVE>_, ver s2_export.state_prefix)
run_producer.bat s2_export.py --states 14 --tile-ids r000c011 r000c012 ...

REM terreno (elevación+slope desde Copernicus DEM) — estático, por tile
run_producer.bat add_dem.py
```
Cada tile: `out/<tile>/<tile>_features.tif` (stack de predictores) + `_dem.tif` + renders.
**Costeros (MGRS T13Q*):** PC congela la lectura CONCURRENTE → `s2_export` lee **secuencial**
(`READ_WORKERS=1`, lento pero confiable). `generar_costeros.bat` los hace con reintentos.

## 2. Clasificador RandomForest (Fase 1)

```bat
REM 1) unir etiquetas de los consultores (batch1+2) -> labels_merged.gpkg
run_producer.bat merge_labels.py

REM 2) ENTRENAMIENTO COMPLETO (muestreo -> negativos INEGI -> entrenar -> versiona):
entrenar.bat --version mi_version --groups groups.csv --rodrigo-drop 5 7
```
`entrenar.bat` encadena `sample.py` → `add_inegi_negatives.py` → `train.py`. Flags útiles de
`train.py`: `--groups groups.csv` (legenda agrupada de 10), `--rodrigo-drop 5 7` (incluye a
Rodrigo sin sus clases poco confiables: aguacate=5, otro-perenne=7), `--with-rodrigo`, `--cap`.

**Insumos de la tabla de entrenamiento:**
- etiquetas humanas (consultores) bajo `labels_merged.gpkg`,
- negativos de clases generales desde **INEGI Serie VII** (`add_inegi_negatives.py`),
- + 2 bandas de **DEM**.

Validación: **GroupKFold espacial por `tile_id`** (nunca píxeles del mismo tile en train y
test). Reporte en `rf_report.md` + `entrenamientos/<version>/`.

## 3. Inferencia / mapa

```bat
run_producer.bat infer.py --all           REM todos los tiles construidos
run_producer.bat infer.py --skip-existing  REM reanudar tras un corte
run_producer.bat make_render_vrt.py        REM mosaicos de renders para QGIS
```
`infer.py` selecciona predictores **por NOMBRE** → el modelo 04 (36 bandas) corre igual sobre
tiles de 34 o 47 bandas (usa las que necesita, ignora las extra). Salidas: `maps/<tile>_class.tif`
(coloreado con legend.csv) + `_confidence.tif` + `class_mosaic.vrt`.

## 4. Validación independiente (Olofsson / Collect Earth Online)

```bat
run_producer.bat generate_validation.py    REM centros de parcela estratificados por clase del mapa
```
Diseño: parcela 100×100 m, grilla 5×5 (25 puntos). Se sube `validation/ceo_plots.csv` a CEO
(sin la clase, para no sesgar); al volver, se cruza con `strata_key.csv` por PLOTID → matriz
de error + exactitud usuario/productor + área ajustada (IC 95%).

## 5. CNN (Fase 2) — ver METODOLOGIA_CLASIFICACION.md

Toma el mapa + confianza del RF (04) como pseudo-etiquetas (con compuerta de confianza +
anclas humanas), añade contexto espacial (U-Net + CBAM), para afinar sobre todo las clases con
geometría (aguacate en hileras/terrazas, agave, cultivo). *En construcción.*

## Archivos clave
- `s2_export.py` — genera tiles (STAC → composites multi-temporada + índices + deltas).
- `add_dem.py`, `add_inegi_negatives.py`, `sample.py` — insumos del modelo.
- `train.py` (`--version`, `--groups`, `--rodrigo-drop`) + `entrenar.bat` — entrenamiento.
- `infer.py`, `make_render_vrt.py` — mapas.
- `merge_labels.py` — unifica etiquetas de consultores (class_id es la autoridad vía legend.csv).
- `plan_sample.py` / `MASTER_PLAN.md` / `plan_all_states.csv` — plan de muestreo 8 estados.
- `legend.csv` (12 clases finas), `groups.csv` (agrupación a 10), `tile_grid.gpkg`, `aoi.gpkg`.

## Notas / gotchas
- **Selección por nombre:** un modelo corre sobre cualquier stack que CONTENGA sus bandas (por
  eso 04 sirve en tiles de 2 y 4 temporadas).
- **Rodrigo:** su aguacate no es confiable (0% traslape con referencia 2022) → se excluye del
  entrenamiento (`--rodrigo-drop 5 7`); sus demás clases sí sirven.
- **Throttle PC:** lecturas concurrentes de escenas costeras congelan → secuencial. Descargas
  simples sí funcionan (`download_scenes.py`, alternativa no usada).
- **Separación por estado:** ids con prefijo `<CVE>_` para estados nuevos; Jalisco (14) sin
  prefijo (ya en producción).
