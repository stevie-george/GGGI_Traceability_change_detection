"""
compare_models.py — compara clasificadores (RF vs LightGBM vs SVM) con el MISMO
preprocesamiento y validación espacial (GroupKFold por tile) que el modelo v2.
Experimento APARTE: no toca rf_model.pkl. No necesita F: (usa training_table.parquet).

    run_producer.bat compare_models.py
"""
import csv
from pathlib import Path
import numpy as np
import pandas as pd
import joblib
from sklearn.ensemble import RandomForestClassifier
from sklearn.svm import SVC
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import make_pipeline
from sklearn.model_selection import GroupKFold, cross_val_predict
from sklearn.metrics import f1_score, accuracy_score
from lightgbm import LGBMClassifier

HERE = Path(__file__).resolve().parent
META = ["class_id", "class_name", "is_avocado", "src_file", "tile_id"]
CAP = 40000
SVM_PER_CLASS = 3000       # SVM no escala: submuestreo (indicativo)
GROUPS_CSV = HERE / "groups_v2.csv"
DROP_SOURCE = ["inegi_svii"]
DROP_CLASS = [11]
RODRIGO_DROP = [5, 7]


def prep():
    df = pd.read_parquet(HERE / "training_table.parquet")
    feats = joblib.load(HERE / "entrenamientos/entrenamiento_04/rf_model.pkl")["features"]
    feats = [f for f in feats if f in df.columns]
    df = df.dropna(subset=feats).reset_index(drop=True)
    df = df[~df["src_file"].isin(DROP_SOURCE)]
    df = df[~df["class_id"].isin(DROP_CLASS)]
    rod = df[df["src_file"] == "rodrigo"]
    keep = rod[~rod["class_id"].isin(RODRIGO_DROP)]
    df = pd.concat([df[df["src_file"] != "rodrigo"], keep], ignore_index=True)
    remap = {}
    with open(GROUPS_CSV, encoding="utf-8") as f:
        for r in csv.DictReader(f):
            remap[int(r["class_id"])] = int(r["group_id"])
    df["class_id"] = df["class_id"].map(remap)
    df = df[df["class_id"].notna()].copy(); df["class_id"] = df["class_id"].astype(int)
    # cap por clase
    rng = np.random.default_rng(0)
    df = pd.concat([g.iloc[rng.choice(len(g), min(CAP, len(g)), replace=False)] if len(g) > CAP else g
                    for _, g in df.groupby("class_id")]).reset_index(drop=True)
    return df, feats


def main():
    df, feats = prep()
    X = df[feats].to_numpy("float32"); y = df["class_id"].to_numpy(); groups = df["tile_id"].to_numpy()
    labels = sorted(np.unique(y))
    cv = GroupKFold(n_splits=5)
    print(f"{len(df):,} px | {len(feats)} predictores | {df['tile_id'].nunique()} tiles | clases {labels}\n")

    res = {}
    # RF (= config de train.py)
    rf = RandomForestClassifier(n_estimators=300, class_weight="balanced", min_samples_leaf=2,
                                n_jobs=-1, random_state=0)
    print("RF..."); res["RF"] = cross_val_predict(rf, X, y, groups=groups, cv=cv, n_jobs=1)

    # LightGBM
    lgbm = LGBMClassifier(n_estimators=400, learning_rate=0.05, num_leaves=63,
                          class_weight="balanced", n_jobs=-1, random_state=0, verbose=-1)
    print("LightGBM..."); res["LightGBM"] = cross_val_predict(lgbm, X, y, groups=groups, cv=cv, n_jobs=1)

    # SVM (submuestreado)
    rng = np.random.default_rng(0)
    idx = np.concatenate([rng.choice(np.where(y == c)[0], min(SVM_PER_CLASS, (y == c).sum()), replace=False)
                          for c in labels])
    Xs, ys, gs = X[idx], y[idx], groups[idx]
    svm = make_pipeline(StandardScaler(), SVC(kernel="rbf", class_weight="balanced", cache_size=1000))
    print(f"SVM (submuestreo {len(Xs):,} px)...")
    svm_pred = cross_val_predict(svm, Xs, ys, groups=gs, cv=cv, n_jobs=1)

    # --- reporte ---
    names = {}
    with open(GROUPS_CSV, encoding="utf-8") as f:
        for r in csv.DictReader(f):
            names[int(r["group_id"])] = r["group_name"]

    print(f"\n{'clase':26s} {'RF':>8} {'LightGBM':>9} {'SVM*':>8}")
    print("-" * 54)
    for c in labels:
        f_rf = f1_score(y == c, res["RF"] == c)
        f_lg = f1_score(y == c, res["LightGBM"] == c)
        f_sv = f1_score(ys == c, svm_pred == c)
        print(f"{names.get(c, c)[:25]:26s} {f_rf:>8.3f} {f_lg:>9.3f} {f_sv:>8.3f}")
    print("-" * 54)
    print(f"{'EXACTITUD GLOBAL':26s} {accuracy_score(y, res['RF']):>8.3f} "
          f"{accuracy_score(y, res['LightGBM']):>9.3f} {accuracy_score(ys, svm_pred):>8.3f}")
    print(f"{'MACRO-F1':26s} {f1_score(y, res['RF'], average='macro'):>8.3f} "
          f"{f1_score(y, res['LightGBM'], average='macro'):>9.3f} "
          f"{f1_score(ys, svm_pred, average='macro'):>8.3f}")
    print("\n* SVM: submuestreado a 3k/clase (no escala a la tabla completa) -> solo indicativo.")


if __name__ == "__main__":
    main()
