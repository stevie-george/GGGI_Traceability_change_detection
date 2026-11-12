# COBIOCOM LULC — Cheatsheet de comandos

> Correr todo desde `cobiocom_lulc\` en Command Prompt. `run_producer.bat` lanza con el
> env `cobiocom` y el PATH limpio (GDAL correcto). Los pasos que leen tiles (`s2_export`,
> `add_dem`, `sample`, `infer`) **requieren el SSD F: conectado** (`out/` → F:).

## 0. Lanzador
```bat
run_producer.bat <script.py> [args]     REM cualquier script del pipeline
entrenar.bat [args de train.py]          REM pipeline de entrenamiento completo (sample → train)
```

Códigos de estado (CVE_ENT): **Jalisco 14** · Michoacán 16 · Nayarit 18 · Colima 06 · Guanajuato 11 · Aguascalientes 01 · Zacatecas 32 · San Luis Potosí 24.

---

## 1. Exportar un estado (generar tiles Sentinel-2)
Stack bloqueado del corredor = **green + dry** (36 predictores con DEM).
**Convención de carpetas:** Jalisco = `out/` (producción, tiles `r###c###`); cada otro
estado = `out_<estado>/` con tiles **prefijados** `<CVE>_r###c###` (el prefijo mantiene
los `tile_id` únicos en todo el corredor — NO quitarlo).
```bat
REM Jalisco (año actual 2025-26):
run_producer.bat s2_export.py --states 14 --seasons green dry --out out

REM Otro estado (ej. Michoacán = 16) -> carpeta propia:
run_producer.bat s2_export.py --states 16 --seasons green dry --out out_michoacan

REM Tiles específicos:
run_producer.bat s2_export.py --states 14 --seasons green dry --tile-ids r004c011 r003c011 --out out

REM Año histórico (ej. 2016), ventana ancha por pocas escenas:
run_producer.bat s2_export.py --states 14 --year 2016 --wide-green --seasons green dry --out out_2016

REM Prueba de 1 tile:
run_producer.bat s2_export.py --states 16 --seasons green dry --limit 1 --out out_michoacan
```
Después de exportar, generar el **DEM** (elevación+pendiente, estático) en la MISMA carpeta:
```bat
run_producer.bat add_dem.py                       REM Jalisco (out/)
run_producer.bat add_dem.py --out out_michoacan   REM otro estado
```
(La generación es reanudable: re-correr el mismo comando salta los tiles ya hechos.)

---

## 2. Paquetes de muestras para consultores
```bat
REM Paquete nuevo con los tiles de un consultor (según tile_grid.gpkg):
run_producer.bat package_for_consultants.py --name jalisco_tona --consultant tona

REM Paquete con tiles específicos:
run_producer.bat package_for_consultants.py --name campaña3 --tiles r004c011 r004c012 r005c013

REM Actualizar un paquete existente (solo manda los tiles NUEVOS):
run_producer.bat package_for_consultants.py --name jalisco_tona --update --tiles r006c010
```

---

## 3. Unir etiquetas de los consultores
Edita la lista `SOURCES` en `merge_labels.py` para agregar/quitar entregas, luego:
```bat
run_producer.bat merge_labels.py            REM -> labels_merged.gpkg (EPSG:6372)
```

---

## 4. Entrenar el modelo (RandomForest)
Pipeline completo (re-muestrea + entrena). **Comando oficial actual:**
```bat
entrenar.bat --drop-class 11 --rodrigo-drop 1 2 4 5 7 --groups groups_v2.csv ^
    --features-like entrenamientos\entrenamiento_04\rf_model.pkl --version manual_b3_v3
```
Flags de `train.py`:
- `--drop-class 11` — excluye suelo desnudo (clase eliminada).
- `--rodrigo-drop 1 2 4 5 7` — excluye clases poco confiables de Rodrigo (conserva su agave, etc.).
- `--groups groups_v2.csv` — 10 clases agrupadas (urbano solo, sin suelo).
- `--features-like <pkl>` — usa los 36 predictores del modelo de referencia (corre en tiles de 2 y 4 estaciones).
- `--version NAME` — guarda en `entrenamientos\NAME\` y actualiza `rf_model.pkl`.
- `--table samples.parquet` — tabla solo-manual (lo pone `entrenar.bat` solo).

Solo re-entrenar (sin re-muestrear; rápido, prueba otros args):
```bat
run_producer.bat train.py --table samples.parquet --drop-class 11 --rodrigo-drop 1 2 4 5 7 ^
    --groups groups_v2.csv --features-like entrenamientos\entrenamiento_04\rf_model.pkl --version prueba
```

---

## 5. Evaluar / validar
```bat
REM Umbral de confianza para capa de alta precisión (aguacate/agave):
run_producer.bat calibrate_conf.py                 REM -> calibracion_conf.csv

REM Comparar clasificadores (RF vs LightGBM vs SVM):
run_producer.bat compare_models.py

REM Validación independiente (mapa 2016 vs referencia aguacate):
run_producer.bat validate_2016.py

REM Puntos de validación para Collect Earth Online (consultores muestrean):
run_producer.bat generate_validation.py --n 300 --priority 5 6 --priority-min 40
```
Los reportes por clase de cada entrenamiento están en `entrenamientos\<version>\rf_report.md`.

---

## 6. Inferir (generar el mapa)
```bat
REM Mapa completo con el modelo vivo (rf_model.pkl), versionado aparte:
run_producer.bat infer.py --version manual_b3_v3 --all          REM -> maps_manual_b3_v3\

REM Solo unos tiles:
run_producer.bat infer.py --version manual_b3_v3 --tiles r004c011 r003c011

REM Reanudar tras interrupción (omite los ya hechos):
run_producer.bat infer.py --version manual_b3_v3 --all --skip-existing

REM Mapa de otro año (lee out_2016, reusa el DEM de out/):
run_producer.bat infer.py --in-dir out_2016 --version 2016 --tiles r004c011
```
Salida por tile: `<tile>_class.tif` (coloreado) + `<tile>_confidence.tif` (0-100) + `class_mosaic.vrt`.
Capa "alta confianza" en QGIS: `class == 5` (aguacate) **y** `confidence >= 65`.

---

## 7. Preparar fuentes externas (crosswalk → class_id)
```bat
run_producer.bat prep_semadet_matorral.py     REM matorral xerófilo SEMADET (class_id=3)
run_producer.bat prep_semadet_avocado.py      REM aguacate SEMADET + 2025 (class_id=5)
run_producer.bat prep_frontera_agricola.py    REM agricultura Frontera (class_id=9), sin aguacate/agave
```
(Luego se agregan a `SOURCES` en `merge_labels.py` y se re-corre el merge.)

---

## 8. QGIS / mosaicos
```bat
run_producer.bat make_render_vrt.py --overviews     REM mosaicos VRT de los renders (green/dry)
run_producer.bat make_qgis_assets.py                REM aoi.gpkg, tile_grid.gpkg locales
run_producer.bat make_qgis_project.py               REM proyecto .qgz
```

---

## Leyenda (10 clases, esquema groups_v2)
| ID | Clase | Color |
|----|-------|-------|
| 1 | Bosque templado | `#1b5e20` |
| 2 | Selva baja caducifolia | `#7cb342` |
| 3 | Matorral xerófilo | `#c0ca33` |
| 4 | Pastizal | `#dce775` |
| 5 | Aguacate | `#004d40` |
| 6 | Agave | `#8e24aa` |
| 8 | Agricultura protegida | `#e0e0e0` |
| 10 | Urbano / Asentamiento | `#b71c1c` |
| 12 | Cuerpo de agua | `#1565c0` |
| 13 | Agricultura (cultivos) | `#ffd54f` |

Modelo oficial vivo = `rf_model.pkl`. Versiones en `entrenamientos\`. Mapas en `maps_<version>\`.
