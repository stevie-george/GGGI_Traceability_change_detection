"""
calibrate_conf.py — ¿qué UMBRAL de confianza (prob. del RF) deja una capa de aguacate
y agave de ALTA PRECISIÓN? Replica exactamente la config del entrenamiento_04
(--rodrigo-drop 5 7 + groups.csv + cap 40k/clase + GroupKFold espacial), pero captura
las probabilidades OUT-OF-FOLD (honestas) y barre el umbral.

Precisión(U) = de los píxeles que el modelo llama aguacate (o agave) con confianza >= U,
qué fracción son realmente esa clase (según las etiquetas Tona+Mau y agave confiable).
Recall(U) = de todo el aguacate/agave verdadero, cuánto conservas a ese umbral.

    run_producer.bat calibrate_conf.py
Salida: tabla en consola + calibracion_conf.csv
"""
import csv
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import GroupKFold, cross_val_predict

HERE = Path(__file__).resolve().parent
TABLE = HERE / "training_table.parquet"
META = ["class_id", "class_name", "is_avocado", "src_file", "tile_id"]
GROUPS_CSV = HERE / "groups.csv"
RODRIGO_DROP = [5, 7]
CAP = 40000
TREES = 300
TARGETS = {5: "Aguacate", 6: "Agave"}       # ids AGRUPADOS (5->5, 6->6)
THRESHOLDS = [0.30, 0.40, 0.50, 0.55, 0.60, 0.65, 0.70, 0.75, 0.80, 0.85, 0.90, 0.95]


def cap_per_class(df, cap, seed=0):
    rng = np.random.default_rng(seed)
    keep = []
    for _, g in df.groupby("class_id"):
        keep.append(g.iloc[rng.choice(len(g), min(cap, len(g)), replace=False)] if len(g) > cap else g)
    return pd.concat(keep).reset_index(drop=True)


def main():
    df = pd.read_parquet(TABLE)
    feats = [c for c in df.columns if c not in META]
    df = df.dropna(subset=feats).reset_index(drop=True)

    # --rodrigo-drop 5 7 (igual que el 04)
    rod = df[df["src_file"] == "rodrigo"]
    keep_rod = rod[~rod["class_id"].isin(RODRIGO_DROP)]
    train_df = pd.concat([df[df["src_file"] != "rodrigo"], keep_rod], ignore_index=True)

    # legenda agrupada (igual que el 04)
    remap = {}
    with open(GROUPS_CSV, encoding="utf-8") as gf:
        for r in csv.DictReader(gf):
            remap[int(r["class_id"])] = int(r["group_id"])
    train_df = train_df.assign(class_id=train_df["class_id"].map(remap))
    train_df = cap_per_class(train_df, CAP)

    X = train_df[feats].to_numpy("float32")
    y = train_df["class_id"].to_numpy()
    groups = train_df["tile_id"].to_numpy()
    labels = sorted(train_df["class_id"].unique())
    n_tiles = train_df["tile_id"].nunique()
    n_splits = min(5, n_tiles)
    print(f"{len(train_df):,} px | {len(feats)} predictores | {n_tiles} tiles | "
          f"GroupKFold {n_splits} folds (replica entrenamiento_04)", flush=True)

    rf = RandomForestClassifier(n_estimators=TREES, class_weight="balanced",
                                min_samples_leaf=2, n_jobs=-1, random_state=0)
    proba = cross_val_predict(rf, X, y, groups=groups,
                              cv=GroupKFold(n_splits=n_splits), method="predict_proba", n_jobs=1)
    labels_arr = np.array(labels)
    pred = labels_arr[proba.argmax(1)]
    conf = proba.max(1)

    rows = []
    for cid, cname in TARGETS.items():
        if cid not in labels:
            print(f"  (clase {cname} no está en el modelo)"); continue
        total_true = int((y == cid).sum())
        print(f"\n=== {cname} (id {cid}) — {total_true:,} px verdaderos en el conjunto ===")
        print(f" {'umbral':>7} {'px_pred':>9} {'precisión':>10} {'recall':>8}")
        print(" " + "-" * 38)
        for U in THRESHOLDS:
            sel = (pred == cid) & (conf >= U)
            n = int(sel.sum())
            prec = float((y[sel] == cid).mean()) if n else float("nan")
            rec = float(((pred == cid) & (conf >= U) & (y == cid)).sum() / total_true) if total_true else float("nan")
            print(f" {U:>7.2f} {n:>9,} {prec:>10.3f} {rec:>8.3f}")
            rows.append({"clase": cname, "umbral": U, "px_pred": n, "precision": round(prec, 4), "recall": round(rec, 4)})
        # umbrales recomendados
        for tgt in (0.90, 0.95):
            ok = [U for U in THRESHOLDS
                  if (pred == cid).sum() and ((y[(pred == cid) & (conf >= U)] == cid).mean() if ((pred == cid) & (conf >= U)).any() else 0) >= tgt]
            if ok:
                Ustar = min(ok)
                sel = (pred == cid) & (conf >= Ustar)
                rec = ((pred == cid) & (conf >= Ustar) & (y == cid)).sum() / total_true
                print(f"  -> precisión >= {tgt:.2f}: umbral {Ustar:.2f} (conservas {rec*100:.0f}% del {cname.lower()})")
            else:
                print(f"  -> precisión >= {tgt:.2f}: NO se alcanza ni al umbral 0.95")

    pd.DataFrame(rows).to_csv(HERE / "calibracion_conf.csv", index=False)
    print("\n-> calibracion_conf.csv")


if __name__ == "__main__":
    main()
