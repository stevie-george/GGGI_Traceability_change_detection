# RandomForest Fase 1 — reporte

- Entrenamiento: **400,000 px**, 36 predictores, 235 tiles
- Rodrigo: parcial (sin sus clases [1, 2, 4, 5, 7]; +209,444 px suyos)
- Validación: GroupKFold espacial por `tile_id` (5 folds)

## Global (out-of-fold)

- Exactitud general: **0.776**
- Aguacate — precisión **0.830**, recall **0.809**, F1 **0.819** (TP 32,350 · FP 6,645 · FN 7,650)

## Por clase (out-of-fold)

```
                       precision    recall  f1-score   support

     Temperate forest      0.831     0.831     0.831     40000
  Tropical dry forest      0.786     0.849     0.816     40000
 Shrubland / Matorral      0.756     0.786     0.771     40000
 Grassland / Pastizal      0.634     0.606     0.620     40000
   Avocado plantation      0.830     0.809     0.819     40000
     Agave plantation      0.686     0.712     0.699     40000
Protected agriculture      0.950     0.762     0.846     40000
   Urban / Settlement      0.844     0.858     0.851     40000
           Water body      0.939     0.865     0.900     40000
  Agriculture (crops)      0.583     0.684     0.630     40000

             accuracy                          0.776    400000
            macro avg      0.784     0.776     0.778    400000
         weighted avg      0.784     0.776     0.778    400000

```

## Rodrigo como test independiente

- Rodrigo como test independiente: **230,460 px**, acuerdo global con el modelo verificado (Tona+Mau) **60.9%**
- Su AGUACATE (88,456 px): el modelo lo confirma aguacate en **55.1%**
- Acuerdo por clase que etiquetó Rodrigo:
    - Temperate forest: 65,474 px, el modelo coincide 79%
    - Tropical dry forest: 28,084 px, el modelo coincide 43%
    - Grassland / Pastizal: 16,944 px, el modelo coincide 55%
    - Avocado plantation: 88,456 px, el modelo coincide 55%
    - Agriculture (crops): 31,502 px, el modelo coincide 60%

## Figuras

![confusión](rf_confusion.png)

![importancias](rf_importances.png)
