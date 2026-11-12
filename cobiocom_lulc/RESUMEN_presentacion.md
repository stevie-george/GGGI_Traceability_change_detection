# COBIOCOM — Clasificación de cobertura (aguacate/agave) — Resumen para presentación

> Brief autocontenido para elaborar una presentación. Fecha: octubre 2026.

## 1. Proyecto y objetivo
- **Organización:** GGGI México (Global Green Growth Institute), área de trazabilidad.
- **Marco:** corredor biocultural **COBIOCOM**, 8 estados del occidente de México (Jalisco, Michoacán, Nayarit, Colima, Guanajuato, Aguascalientes, Zacatecas, San Luis Potosí). **Jalisco primero** como piloto.
- **Objetivo:** mapa de cobertura y uso de suelo centrado en **aguacate y agave** (cultivos de interés por su expansión y trazabilidad), separándolos de bosque, selva seca, matorral, pastizal, agricultura, agua y urbano.
- **Fases:** Fase 1 = clasificador RandomForest (actual). Fase 2 = CNN (explorada, en pausa). Fase 3 = inferencia masiva (futuro).

## 2. Datos y método
- **Imágenes:** Sentinel-2 L2A (reflectancia de superficie) vía Microsoft Planetary Computer, resolución 10 m.
- **Stack de predictores (36 bandas, bloqueado para todo el corredor):** 2 temporadas — **green** (post-monzón, Sep-Nov) + **dry** (seca, Mar-May) — con 16 bandas cada una (ópticas + índices NDVI/NDRE/NDMI/MNDWI/EVI/BSI), más **dNDVI** y **dNDMI** (cambio entre temporadas) y **DEM** (elevación + pendiente, Copernicus GLO-30).
- **Clasificador:** RandomForest (scikit-learn), 10 clases agrupadas, pesos balanceados.
- **Validación:** cruzada **espacial** por tile (GroupKFold) — nunca se mezclan píxeles del mismo tile en entrenamiento y prueba (evita inflar la exactitud).
- **Clases (10):** Bosque templado, Selva seca, Matorral, Pastizal, **Aguacate**, **Agave**, Agricultura, Agricultura protegida, Urbano/Suelo, Agua.

## 3. Datos de entrenamiento (muestras manuales)
- **4,542 polígonos** delineados a mano por 3 fotointérpretes consultores (Tona, Mau, Rodrigo), en **2 entregas (batches)**.
- Auditoría de etiquetas: el aguacate de un consultor (Rodrigo) resultó **no confiable** (0% de traslape con una referencia verificada) → se excluye su aguacate del entrenamiento.
- El **batch 2** aportó las clases naturales (bosque, selva, pastizal, matorral); el batch 1 era casi todo aguacate.

## 4. Hallazgo central: los negativos automáticos metían RUIDO
- Para abaratar el muestreo se usaban negativos automáticos de **INEGI Serie VII** (cartografía 1:250,000, año base 2018) en las clases naturales.
- Un experimento controlado A/B (con vs sin INEGI, todo lo demás igual) mostró que **quitar INEGI MEJORA** bosque, selva seca y agricultura — porque esas etiquetas gruesas y viejas enseñaban una "firma" sucia:
  - **Bosque: F1 0.69 → 0.81** (y precisión ~0.78, casi la meta de 0.80).
  - Selva seca: 0.61 → 0.73. Agricultura: 0.60 → 0.70.
- Pero INEGI **sí daba soporte** a matorral y pastizal (donde los consultores casi no tienen muestras): sin INEGI, esas dos clases caen.
- **Decisión:** entrenar **solo con muestras manuales** (sin INEGI) y reforzar matorral/pastizal con el **batch 3** de los consultores.

## 5. Resultados del modelo actual (solo manual, 36 bandas)
Exactitud global (validación espacial): **0.704**. Por clase (F1):

| Clase | F1 | Comentario |
|---|---|---|
| Agua | 0.92 | excelente |
| Agricultura protegida | 0.85 | excelente |
| **Bosque templado** | **0.81** | logro clave (de 0.69) |
| Aguacate | 0.74 | sólido |
| Agave | 0.71 | sólido |
| Selva seca | 0.70 | |
| Agricultura | 0.66 | |
| Urbano/Suelo | 0.57 | medio |
| Pastizal | 0.31 | débil → batch 3 |
| Matorral | 0.10 | débil → batch 3 |

- **Logro destacado:** el bosque subió a ~0.81 **solo quitando el ruido de INEGI**, sin más procesamiento.
- **Pendiente:** matorral y pastizal necesitan más muestras manuales (batch 3).

## 6. Capa de alta confianza (para entregables de aguacate/agave)
El modelo entrega por píxel una **confianza 0-100**. Calibrando contra la referencia:
- **Aguacate:** con confianza ≥ 65 la **precisión sube a 96%** (conservando ~41% de la superficie) → se puede entregar una capa "aguacate seguro" de muy alta pureza.
- **Agave:** la confianza **no** logra una capa pura (techo ~83%); indica confusión sistemática que se corrige con mejores muestras, no con el umbral.

## 7. Fase 2 — CNN (explorada, en pausa)
- Se construyó y entrenó una red U-Net + atención (CBAM) sobre pseudo-etiquetas del RF + anclas humanas.
- En la comparación honesta **no superó al RandomForest**: suavizaba de más y perdía las clases de parches chicos (urbano, pastizal).
- **Decisión:** el RandomForest sigue siendo el modelo oficial; el CNN queda en pausa. El árbitro final de calidad será la validación independiente (Collect Earth / Olofsson).

## 8. Mapa histórico 2016 (en curso) — detección de cambio
- Objetivo: generar un mapa **2016** con el mismo método para comparar **2016 vs 2025** (expansión de la frontera del aguacate, pérdida de bosque).
- Factible: hay Sentinel-2 desde oct-2015. Salvedad: en 2016 solo existía Sentinel-2A → menos imágenes limpias en la temporada "green" (se amplía la ventana para compensar); la temporada seca está bien.
- Se puede **validar** el aguacate 2016 porque existe referencia de huertas de 2016 (814 polígonos).

## 9. Reproducibilidad y consistencia del corredor
- **Mismo stack de 36 bandas y mismo mecanismo de descarga para los 8 estados** (decisión tomada): un solo modelo infiere en todo el corredor.
- Pipeline versionado y respaldado en git; entrenamientos e inferencias guardados por versión (no se sobrescriben).

## 10. Próximos pasos
1. **Batch 3** de muestras manuales (prioridad: matorral, pastizal, más bosque) → reentrenar.
2. **Validación independiente** tipo Collect Earth / buenas prácticas (Olofsson) — el número "oficial" de exactitud por clase.
3. Escalar la generación e inferencia a los **8 estados**.
4. **Mapa 2016** completo → análisis de cambio 2016→2025.
5. Fase 3: inferencia masiva (aceleración por NPU).

## 11. Material visual disponible
- Matriz de confusión y gráfico de importancia de predictores del modelo actual (`entrenamientos/manual_sin_inegi/rf_confusion.png`, `rf_importances.png`).
- Mapa de Jalisco 2025 clasificado (`maps_manual_sin_inegi/`, abrible en QGIS como mosaico).
- (Próximo) comparación visual mapa 2016 vs 2025.

## 12. Mensajes clave para la presentación
1. Un clasificador de cobertura **operativo para Jalisco**, enfocado en aguacate/agave, construido con muestras de campo de consultores.
2. **Hallazgo metodológico:** depurar las fuentes automáticas (INEGI) **subió el bosque a ~0.81** — la calidad de las etiquetas pesa más que la complejidad del modelo.
3. Capa de aguacate de **alta pureza (96%)** lista para entregables mediante umbral de confianza.
4. Método **reproducible y consistente** para los 8 estados, con detección de cambio histórico (2016) en camino.
5. Ruta clara de mejora: más muestras (batch 3) para las clases débiles + validación independiente.
