# COBIOCOM · Jalisco — Guía de instalación para fotointérpretes (QGIS)

Vas a dibujar **polígonos de entrenamiento (ROIs)** sobre imágenes de referencia
Sentinel‑2 y de muy alta resolución. **No necesitas Python ni cuentas** — sólo QGIS
y este paquete.

## 1. Instala QGIS (una vez, ~10 min)
- Descarga la versión **LTR** (la más estable): <https://qgis.org/es/site/forusers/download.html>
- Instálala con las opciones por defecto (Windows: instalador de 64 bits).

## 2. Descarga y descomprime el paquete
- Descarga `cobiocom_labeling_jalisco.zip` del enlace que te compartió tu contacto.
- **Descomprímelo** en una carpeta local, p. ej. `Documentos\COBIOCOM`.
  > ⚠️ No trabajes dentro del ZIP: descomprime primero. Mantén **junta** toda la carpeta
  > (el `.qgz`, `out/`, `labels.gpkg`, `aoi.gpkg`) — el proyecto usa rutas relativas.

## 3. Abre el proyecto
- Doble clic en **`cobiocom_labeling.qgz`** (o QGIS → *Proyecto → Abrir*).
- Verás, de arriba a abajo: **labels (ROIs)** (donde dibujas), el contorno **AOI**,
  el grupo **Sentinel‑2 renders** (SWIR seca visible) y **Esri** (fondo de alta resolución).
- Clic derecho en una capa de render → *Acercar a la capa* para ir a tu zona.

## 4. Dibuja un polígono (el ciclo)
1. Selecciona la capa **labels (ROIs)** en el panel de capas.
2. Activa edición: lápiz amarillo (*Alternar edición*, Ctrl+E).
3. Botón **Agregar entidad poligonal**.
4. Clic izquierdo en cada vértice del **interior puro** de una sola clase; clic derecho para cerrar.
5. En el formulario, elige la **clase** en el desplegable (p. ej. `5 · Avocado plantation`).
   `set`, `source`, `confidence` y la fecha ya vienen puestos.
   **Escribe tus iniciales en `interpreter`.** Aceptar.
6. Repite. **Verifica en dNDVI + SWIR + Esri** antes de confirmar aguacate/agave
   (el aguacate sigue verde en dNDVI; el agave muestra hileras y suelo desnudo en Esri).
7. Guarda seguido (Ctrl+S). Al terminar, desactiva la edición (te pregunta si guardar).

> **Truco de trazabilidad:** activa *Configuración → Opciones → Digitalización →
> "Reutilizar el último valor introducido"* para no reescribir tus iniciales cada vez.

## 5. Reglas de calidad (resumen — ver `SAMPLING_PROTOCOL.md`)
- Interiores **puros**, a **≥ 30 m del borde**; muchos polígonos pequeños mejor que pocos grandes.
- Reparte por toda tu zona; captura la variedad de cada clase.
- Metas por clase (§3): ~100–150 para aguacate/agave.

## 6. Entrega tu trabajo
- Al terminar, **renombra** tu `labels.gpkg` como `labels_jalisco_TUSINICIALES.gpkg`
  y envíalo a tu contacto de trazabilidad. (No lo renombres mientras trabajas — el
  proyecto lo busca con el nombre `labels.gpkg`.)

## 7. Recibir más tiles (actualizaciones)
Las actualizaciones traen **sólo los tiles nuevos** — **no tocan** tu proyecto, tu vista ni tus polígonos.
1. **Descomprime el ZIP en la carpeta que _contiene_ tu carpeta de proyecto** `cobiocom_labeling_...`
   (donde la descomprimiste la primera vez). Se **combina** y sólo agrega carpetas nuevas en `out\`.
   Acepta **combinar** si Windows pregunta.
2. Con tu proyecto abierto, agrega los tiles nuevos de **una** de estas formas:
   - **Consola de Python** (*Complementos → Consola de Python*), pega y Enter:
     `exec(open(r'add_tiles.py').read())` — usa la ruta completa a `add_tiles.py` si hace falta.
     Aparecen agrupados y con estilo, sin tocar nada más.
   - **O arrastra** los `.tif` de `out\<tile>\` al mapa (p. ej. `*_dry_SWIR.tif`).
3. **Guarda** (Ctrl+S). Tu `cobiocom_labeling.qgz` y tu `labels.gpkg` quedan **intactos**.

## 8. Fondos VHR y fechas — referencia

El proyecto ya incluye estos fondos en el grupo **Basemaps** (actívalos con un clic; apaga
las capas *Sentinel-2 renders*, que son opacas, para verlos por debajo). Recuerda: tu
referencia **con fecha** es el compuesto Sentinel-2 (2025–2026); el VHR es sólo apoyo de textura.

Para agregarlos a mano: **Navegador → clic derecho en *Teselas XYZ* → *Conexión nueva…***,
pega el nombre y la URL, pon **Máximo de zoom = 19**, Aceptar, y arrástralo al mapa.

**Esri Wayback** — imagen mundial *publicada* en esa fecha (la toma real de un sitio puede ser algo anterior):
- **2024-12-12** (referencia anterior): `https://wayback.maptiles.arcgis.com/arcgis/rest/services/World_Imagery/WMTS/1.0.0/default028mm/MapServer/tile/16453/{z}/{y}/{x}`
- **2025-11-20** (≈ temporada verde): `https://wayback.maptiles.arcgis.com/arcgis/rest/services/World_Imagery/WMTS/1.0.0/default028mm/MapServer/tile/51127/{z}/{y}/{x}`
- **2026-05-28** (≈ temporada seca): `https://wayback.maptiles.arcgis.com/arcgis/rest/services/World_Imagery/WMTS/1.0.0/default028mm/MapServer/tile/10842/{z}/{y}/{x}`
- **2026-08-05** (más reciente): `https://wayback.maptiles.arcgis.com/arcgis/rest/services/World_Imagery/WMTS/1.0.0/default028mm/MapServer/tile/26334/{z}/{y}/{x}`

**Esri World Imagery** — más reciente, sin fecha fija: `https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}`

## Problemas comunes
- **No veo el fondo (Esri/Google)** → las capas de *Sentinel-2 renders* son **opacas** y lo
  tapan; **apágalas** para ver el fondo VHR que está debajo. Si aún así no aparece, prueba otra
  capa del grupo *Basemaps* (Esri / Google Satellite / Google Hybrid) o revisa tu conexión.
- **"Capa no disponible" al abrir** → ¿descomprimiste el ZIP? ¿está la carpeta `out/`
  junto al `.qgz`? Conserva la estructura del paquete.
- **Esri no carga** → revisa tu conexión (el fondo de alta resolución se transmite en línea).
- **No veo imágenes** → activa/desactiva las capas del grupo *Sentinel‑2 renders*.
