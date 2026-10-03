# RandomForest Fase 1 — reporte

- Entrenamiento: **364,641 px**, 49 predictores, 93 tiles
- Rodrigo: parcial (sin sus clases [5, 7]; +156,791 px suyos)
- Validación: GroupKFold espacial por `tile_id` (5 folds)

## Global (out-of-fold)

- Exactitud general: **0.649**
- Aguacate — precisión **0.826**, recall **0.693**, F1 **0.754** (TP 27,727 · FP 5,840 · FN 12,273)

## Por clase (out-of-fold)

```
                       precision    recall  f1-score   support

     Temperate forest      0.659     0.716     0.686     40000
  Tropical dry forest      0.581     0.637     0.608     40000
 Shrubland / Matorral      0.439     0.176     0.251      4641
 Grassland / Pastizal      0.344     0.487     0.403     40000
   Avocado plantation      0.826     0.693     0.754     40000
     Agave plantation      0.711     0.631     0.669     40000
Protected agriculture      0.941     0.790     0.859     40000
         Urban / Bare      0.533     0.496     0.514     40000
           Water body      0.909     0.830     0.868     40000
  Agriculture (crops)      0.578     0.614     0.596     40000

             accuracy                          0.649    364641
            macro avg      0.652     0.607     0.621    364641
         weighted avg      0.673     0.649     0.657    364641

```

## Rodrigo como test independiente

- Rodrigo como test independiente: **97,199 px**, acuerdo global con el modelo verificado (Tona+Mau) **38.9%**
- Su AGUACATE (88,369 px): el modelo lo confirma aguacate en **36.8%**
- Acuerdo por clase que etiquetó Rodrigo:
    - Avocado plantation: 88,369 px, el modelo coincide 37%
    - Agriculture (crops): 8,830 px, el modelo coincide 59%

## Figuras

![confusión](rf_confusion.png)

![importancias](rf_importances.png)
