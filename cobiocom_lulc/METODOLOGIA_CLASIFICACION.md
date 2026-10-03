# Metodología de clasificación de uso/cobertura del suelo — COBIOCOM

**Objetivo:** mapear **aguacate, agave**, bosque, cultivos y demás clases de la leyenda (12 clases)
como capa de uso del suelo para la herramienta de alertas de deforestación, en el corredor
COBIOCOM (8 estados, empezando por Jalisco).

**Enfoque en dos etapas complementarias:** primero un clasificador **RandomForest** (por píxel,
rápido, funciona con las etiquetas dispersas de los fotointérpretes), y luego —solo si mejora la
validación— una **CNN de segmentación semántica** entrenada con los mapas del RandomForest como
etiquetas densas. La CNN aporta lo que el RF no puede: **contexto espacial** (textura de las hileras
de agave, forma de las huertas de aguacate, bordes de parcela).

---

## Datos de entrada (ya generados)

- Compuestos **Sentinel‑2 bi‑estacionales** (verde y seca), 10 m, sin nubes (`s2_export.py`).
- Por cada tile: **stack de 34 bandas** (10 ópticas × 2 estaciones + índices NDVI, NDRE, NDMI,
  MNDWI, BSI, EVI × 2 estaciones + dNDVI, dNDMI). Es el archivo `<tile>_features.tif` en el SSD.
- **Etiquetas:** polígonos ROI de los fotointérpretes (muestra, `labels.gpkg`) + **datos de
  referencia externos** (mapas de cobertura, inventarios de aguacate/agave, clasificaciones previas).

## Mapeo al hardware disponible

| Tarea | Dispositivo |
|---|---|
| RandomForest (entrenar + clasificar) | **CPU** |
| Entrenar la CNN ligera (2D) | **GPU NVIDIA RTX 500** (CUDA, 4 GB, fp16) |
| Modelo pesado / 3D (opcional) | **iGPU Intel Arc** (XPU/IPEX, memoria compartida) |
| Inferencia a escala (corredor completo) | **NPU Intel AI Boost** (OpenVINO/ONNX) |

---

## FASE 1 — Clasificador base RandomForest (por píxel)

1. **Muestreo de entrenamiento.** Extraer los valores de las 34 bandas del stack bajo cada polígono
   ROI (`set = 'train'`). Cada píxel etiquetado = un ejemplo (clase + 34 variables).
2. **Entrenar** RandomForest / LightGBM sobre esos ejemplos. Ponderar las clases minoritarias
   (aguacate, agave) para el desbalance.
3. **Clasificar todos los tiles** → dos salidas por tile:
   - el **mapa de clases** (wall‑to‑wall), y
   - el **mapa de probabilidad/confianza** por clase (clave para la Fase 2).
4. **Validar** con el set independiente (ejercicio Collect Earth / Olofsson): matriz de confusión y
   **exactitud ajustada por área**. NO usar los mismos ROI de entrenamiento para validar.
5. **Entregable:** el mapa RF. Si la exactitud ya es suficiente para el objetivo, **se puede detener
   aquí** — la CNN es una mejora opcional, no un requisito.

---

## FASE 2 — CNN de segmentación semántica (contexto espacial)

Solo si se busca superar al RF en las clases con estructura espacial (aguacate/agave) o limpiar el
ruido "sal y pimienta" del RF.

### 2.1 Construir las etiquetas densas (fusión — el paso crítico)
El RF resuelve el problema de "etiqueta densa" que la segmentación necesita, pero hay que hacerlo con
cuidado para no heredar los errores sistemáticos del RF:

- **Pseudo‑etiquetas del RF, filtradas por confianza:** usar el mapa de clases del RF SOLO donde la
  probabilidad es alta (p. ej. > 0.7). Los píxeles inseguros se marcan como **"sin etiqueta"
  (`ignore`)** — no se usan para entrenar.
- **Anclar con los ROI humanos:** donde hay polígono de fotointérprete, **manda la etiqueta humana**
  (confianza total); las pseudo‑etiquetas RF solo rellenan el resto.
- **Datos de referencia externos** para clases "fáciles" (bosque, agua, urbano, suelo desnudo): usar
  mapas existentes como etiqueta densa de esas clases, liberando a los fotointérpretes para
  concentrarse en aguacate/agave.
- Resultado: **tiles de etiqueta densos** con un valor `ignore` en los píxeles no confiables.

### 2.2 Tensor de entrada
- **Canales = stack multi‑estacional** (las mismas ~34 bandas de `features.tif`). Se apila el tiempo
  como **canales**, NO como cubo 3D — así entra en los 4 GB de la GPU NVIDIA.
- Normalizar por percentiles 2/98 (igual que en `s2_export.py`).
- **Parches de 256×256** (o 128×128) con solapamiento; ignorar bordes en la inferencia.

### 2.3 Arquitectura (ligera, para 4 GB)
- **U‑Net 2D** (o SegNet) + módulos de atención **CBAM** (canal + espacial) en el encoder
  (idea de Gao et al. 2023).
- Salida: mapa de segmentación de las 12 clases.
- **Precisión mixta (fp16)**, batch 2–4, acumulación de gradiente si hace falta.
- *(Opcional: un modelo más pesado, o multitarea con extracción de bordes tipo Atanasova et al. 2026,
  se puede correr en la iGPU Intel Arc por su mayor memoria compartida — más lento.)*

### 2.4 Función de pérdida
- **Entropía cruzada categórica con `ignore_index`** (los píxeles sin etiqueta confiable no cuentan).
- **Pesos por clase** (mayor peso a aguacate/agave por el desbalance).
- Opcional: mayor peso a los píxeles de ROI humano que a las pseudo‑etiquetas RF.

### 2.5 Entrenamiento
- Partición **train/val por TILES** (no por píxeles) para evitar fuga espacial.
- Aumentos de datos: volteos y rotaciones.
- Early stopping según la métrica de validación.

### 2.6 Validación independiente (la salvaguarda más importante)
- Evaluar contra el set de verdad‑terreno humano (Collect Earth / Olofsson) y los datos de
  referencia — **NUNCA contra el mapa del RF**.
- La única pregunta válida: **¿la CNN SUPERA al RF** en exactitud ajustada por área? Solo entonces se
  adopta. Si solo lo imita, no aporta.

### 2.7 Iteración (auto‑entrenamiento, opcional)
RF → CNN → los fotointérpretes revisan/corrigen el mapa (más limpio) de la CNN → reentrenar.
Cada ronda reduce el error.

---

## FASE 3 — Inferencia a escala (corredor completo)

1. Generar los `features.tif` de **todos** los tiles (los 266 de Jalisco, luego los 8 estados) —
   ya se están acumulando en el SSD (esto es el "sustrato de predicción").
2. Exportar la CNN entrenada a **ONNX → OpenVINO / DirectML**.
3. Correr la inferencia en la **NPU Intel (AI Boost)** / Arc — eficiente, wall‑to‑wall, sin saturar
   la GPU pequeña.
4. **Mosaico** de los tiles clasificados → mapa final de uso del suelo del corredor.

---

## Salvaguardas clave (resumen)

1. **Confianza:** entrenar la CNN solo con los píxeles RF de alta probabilidad; el resto = `ignore`.
2. **Anclaje:** los ROI humanos mandan; el RF rellena lo demás.
3. **Validación independiente:** siempre contra verdad‑terreno, jamás contra el RF.
4. **Disciplina:** adoptar la CNN **solo** si mejora de forma medible sobre el RF; el RF es el
   entregable de la Fase 1 por sí mismo.

## Por qué esta ruta es viable aquí

- Usa las **etiquetas dispersas** que ya producen los fotointérpretes (no requiere una campaña de
  etiquetado denso nueva) — el RF las convierte en densas.
- Cada etapa cae en el hardware adecuado (CPU → RF, GPU chica → CNN, NPU → inferencia).
- La CNN aporta **contexto espacial**, que es justo lo que distingue aguacate (perenne, textura de
  huerta) y agave (hileras, suelo entre plantas) de bosque y otros cultivos.
