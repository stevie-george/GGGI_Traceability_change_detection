# Handoff — Subir las capas LULC a la plataforma Streamlit + Google Earth Engine

> Para una sesión que publicará los mapas generados en la app de trazabilidad. Oct 2026.

---
## ⚠️ ACTUALIZACIÓN (2026-11-12) — COGs v6 LISTOS para subir
El modelo de producción ya NO es `manual_sin_inegi` (v1); es **`manual_b3_v6`** (RF 10 clases,
36 bandas green+dry+DEM, + muestras SEMADET verificadas 2025; exactitud CV 0.776, bosque F1 0.83).
Los COGs mosaicados de Jalisco 2025 ya están generados y verificados en **`cobiocom_lulc/plataforma/`**:

| Capa | Archivo (COG, EPSG:6372, ZSTD, nodata=0) | Tamaño |
|---|---|---|
| **Clase** | `plataforma/jalisco_lulc_2025_manual_b3_v6_class.tif` | 194 MB, 44060×44051, con tabla de color + 7 overviews |
| **Confianza** | `plataforma/jalisco_lulc_2025_manual_b3_v6_conf.tif` | 1029 MB, 44060×44051, 7 overviews |

Generados con `_make_cog.py` (gdal.Translate→COG desde los VRT de `maps_manual_b3_v6/`; NO warp, preserva paleta).
**Lo único que falta (fuera de la sesión que los generó): bucket GCS + permiso de escritura del SA.**
Comandos de subida (reemplazan los de §4, misma leyenda §2/§5):
```
gsutil cp plataforma/jalisco_lulc_2025_manual_b3_v6_class.tif gs://<bucket>/
gsutil cp plataforma/jalisco_lulc_2025_manual_b3_v6_conf.tif  gs://<bucket>/
earthengine upload image --asset_id=projects/lulcc-traceability-mx40/assets/cobiocom/jalisco_lulc_2025_class \
    --nodata_value=0 gs://<bucket>/jalisco_lulc_2025_manual_b3_v6_class.tif
earthengine upload image --asset_id=projects/lulcc-traceability-mx40/assets/cobiocom/jalisco_lulc_2025_conf \
    --nodata_value=0 gs://<bucket>/jalisco_lulc_2025_manual_b3_v6_conf.tif
```
La leyenda/paleta (§2, §5) NO cambió (mismas 10 clases agrupadas, mismos class_id 1,2,3,4,5,6,8,10,12,13).

**Michoacán 2025 (mismo modelo v6) — COGs TAMBIÉN listos** en `plataforma/`:
| Capa | Archivo | Tamaño |
|---|---|---|
| Clase | `plataforma/michoacan_lulc_2025_manual_b3_v6_class.tif` | 133 MB, 40000×28000 |
| Confianza | `plataforma/michoacan_lulc_2025_manual_b3_v6_conf.tif` | 734 MB, 40000×28000 |
Mismos comandos de subida (cambiando el nombre de archivo y el `--asset_id` a `.../cobiocom/michoacan_lulc_2025_{class,conf}`).
⚠️ Michoacán es **transferencia** del modelo entrenado en Jalisco (sin referencia de campo propia aún); la capa de confianza sirve para filtrar. El % "agua" incluye el océano Pacífico (tiles costeros).

Lo de abajo (§1–§6) es el contexto original v1; sigue válido salvo el nombre del modelo/archivo.

---

## 1. Qué capas hay que subir (generadas en esta conversación)
Están como COGs locales en `cobiocom_lulc/`:

| Capa | Ruta | Contenido |
|---|---|---|
| **Jalisco 2025 — clase** | `maps_manual_sin_inegi/<tile>_class.tif` (+ `class_mosaic.vrt`) | 1 banda uint8 = `class_id` (ver leyenda); colormap embebido |
| **Jalisco 2025 — confianza** | `maps_manual_sin_inegi/<tile>_confidence.tif` (+ `confidence_mosaic.vrt`) | 1 banda uint8 = confianza 0-100 (prob. máx. del RF) |
| Jalisco 2016 (histórico) | `maps_2016/` | **pendiente de generar** (PoC de 4 tiles en curso) |
| ~~`maps/`~~ | `maps/` | modelo viejo (04), **superado** — no subir salvo comparación |

- **Modelo vigente:** `manual_sin_inegi` (RandomForest, solo muestras manuales, 36 bandas green+dry+DEM). Es el `rf_model.pkl` vivo.
- **Formato:** GeoTIFF/COG, **EPSG:6372**, 10 m, comprimido ZSTD, `nodata = 0`.
- Hay 266 tiles por capa → conviene **mosaicarlos a un solo COG por capa/año** antes de subir (ver §4).

## 2. Leyenda (10 clases agrupadas) — para los vis_params en GEE
> Los `class_id` NO son contiguos (faltan 7, 9, 11 por el agrupamiento). Mejor **remapear** a 0-9 (ver §5).

| idx | class_id | Clase | Color (hex) |
|---|---|---|---|
| 0 | 1 | Bosque templado | `#1b5e20` |
| 1 | 2 | Selva seca | `#7cb342` |
| 2 | 3 | Matorral | `#c0ca33` |
| 3 | 4 | Pastizal | `#dce775` |
| 4 | 5 | **Aguacate** | `#004d40` |
| 5 | 6 | **Agave** | `#8e24aa` |
| 6 | 8 | Agricultura protegida | `#e0e0e0` |
| 7 | 10 | Urbano / Suelo | `#b71c1c` |
| 8 | 12 | Agua | `#1565c0` |
| 9 | 13 | Agricultura (cultivos) | `#ffd54f` |

Nota: la clase **13 (Agricultura)** no está en `cobiocom_lulc/legend.csv` (es una agrupación de 7+9); usar `#ffd54f`. Las demás salen de `legend.csv` (`class_id`,`color_hex`).

## 3. La plataforma destino (código existente)
- **App Streamlit:** `app.py` (raíz del repo) + módulos:
  - `modules/gee_analysis.py` — inicializa GEE. **Proyecto GEE: `lulcc-traceability-mx40`** (línea 9). Init con service account: `ee.ServiceAccountCredentials(service_account, key_data=creds_json)` → `ee.Initialize(credentials, project)`.
  - `modules/map_viewer.py` — mapas folium. Helper clave: **`get_tile_url(image, vis_params)`** (usa `image.getMapId(vis_params)`) → se añade como `folium.TileLayer`. Los vis_params son `{min, max, palette}`.
- **Credenciales:** en `.streamlit/secrets.toml` → `[gee].project`, `[earthengine].service_account`, `[earthengine].credentials` (JSON del SA). **No imprimir ni commitear la llave.**
- La app hoy muestra datasets externos (Hansen GFC, JRC TMF, GLAD, MODIS). **Aún no muestra nuestros mapas LULC.**
- La UI "Agregar nueva fuente de datos" (tab Fuentes, `app.py:~378`) está **deshabilitada (v2.0)** → la capa LULC se cablea **en código** (map_viewer / gee_analysis), no por la UI.

## 4. Subir los COGs como assets de GEE
El SA del proyecto necesita **permiso de escritura** al proyecto y a un **bucket de Google Cloud Storage** (confirmar cuál — no está en esta conversación).

1. **Mosaicar** cada capa a un COG único (desde el VRT):
   ```
   gdalwarp -of COG -co COMPRESS=ZSTD maps_manual_sin_inegi/class_mosaic.vrt jalisco_lulc_2025_class.tif
   gdalwarp -of COG -co COMPRESS=ZSTD maps_manual_sin_inegi/confidence_mosaic.vrt jalisco_lulc_2025_conf.tif
   ```
2. **Subir a GCS** (`gsutil cp ... gs://<bucket>/`).
3. **Ingerir a GEE** (CLI `earthengine`, autenticado con el SA o cuenta con acceso):
   ```
   earthengine upload image --asset_id=projects/lulcc-traceability-mx40/assets/cobiocom/jalisco_lulc_2025_class \
       --nodata_value=0 gs://<bucket>/jalisco_lulc_2025_class.tif
   ```
   Igual para `_conf` y, cuando exista, para 2016.
- Alternativa sin GCS: subir el GeoTIFF directo desde el panel de assets del Code Editor de GEE (si el peso lo permite).
- GEE maneja el EPSG:6372 en la ingesta (reproyecta al vuelo en despliegue).

## 5. Mostrar la capa en la app (integración en código)
En `modules/gee_analysis.py` / `map_viewer.py`:
```python
PALETTE = ["1b5e20","7cb342","c0ca33","dce775","004d40","8e24aa","e0e0e0","b71c1c","1565c0","ffd54f"]
img = ee.Image("projects/lulcc-traceability-mx40/assets/cobiocom/jalisco_lulc_2025_class")
# ids no contiguos -> remapear a 0..9 para la paleta:
disp = img.remap([1,2,3,4,5,6,8,10,12,13], [0,1,2,3,4,5,6,7,8,9])
vis = {"min": 0, "max": 9, "palette": PALETTE}
url = get_tile_url(disp, vis)          # map_viewer.py:130
# añadir folium.TileLayer(url, name="COBIOCOM LULC 2025", ...)
```
- **Confianza:** `vis = {"min":0,"max":100,"palette":["ff0000","ffff00","00a000"]}` (rojo→verde).
- Añadir un control de capas y una leyenda (el `map_viewer` ya arma leyendas HTML).

## 6. Notas de consistencia
- El **mismo stack de 36 bandas y la misma leyenda** aplican a los 8 estados y a otros años (2016) → todos los mapas futuros comparten formato, asset path y paleta. Sugerencia de convención: `projects/lulcc-traceability-mx40/assets/cobiocom/<estado>_lulc_<año>_{class,conf}`.
- Mapa actual = **Jalisco 2025 v1** (modelo `manual_sin_inegi`). Clases débiles (matorral, pastizal) se reforzarán con el batch 3; versionar el asset si se re-sube.
- Confirmar con la sesión/usuario: **bucket GCS** y **permisos de escritura del SA** (lo único que falta de esta conversación).
