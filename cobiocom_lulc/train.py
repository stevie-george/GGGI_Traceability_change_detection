"""
train.py — Fase 1: RandomForest multiclase sobre training_table.parquet.

Diseño de la evaluación (lo que pediste: Rodrigo por separado):
  * ENTRENA con las etiquetas VERIFICADAS (Tona + Mau) + los negativos WorldCover.
  * DEJA FUERA a Rodrigo y lo evalúa como test independiente: ¿el modelo entrenado
    solo con datos verificados reconoce como aguacate los polígonos de Rodrigo?
    Alto % -> sus etiquetas son espectralmente consistentes (aguacate real, zona
    nueva); bajo % -> probables errores de interpretación.
  * Validación ESPACIAL por tile_id (GroupKFold): nunca hay píxeles del mismo tile
    en train y test a la vez. Un split aleatorio por píxel filtraría e inflaría la
    exactitud (píxeles del mismo polígono son casi idénticos).

    run_producer.bat train.py                    # Tona+Mau, Rodrigo como test aparte
    run_producer.bat train.py --with-rodrigo     # incluir Rodrigo en el entrenamiento
    run_producer.bat train.py --cap 60000        # tope de píxeles por clase

Salidas: rf_model.pkl, rf_report.md, rf_confusion.png, rf_importances.png
"""
import argparse
import csv
from pathlib import Path

import numpy as np
import pandas as pd
import joblib
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import GroupKFold, cross_val_predict
from sklearn.metrics import classification_report, confusion_matrix, ConfusionMatrixDisplay

HERE = Path(__file__).resolve().parent
TABLE = HERE / "training_table.parquet"
META = ["class_id", "class_name", "is_avocado", "src_file", "tile_id"]
AVOCADO_ID = 5

ID2NAME = {}
with open(HERE / "legend.csv", encoding="utf-8") as f:
    for r in csv.DictReader(f):
        ID2NAME[int(r["class_id"])] = r["name_en"]


def cap_per_class(df, cap, seed=0):
    if not cap:
        return df
    rng = np.random.default_rng(seed)
    keep = []
    for _, g in df.groupby("class_id"):
        keep.append(g.iloc[rng.choice(len(g), min(cap, len(g)), replace=False)] if len(g) > cap else g)
    return pd.concat(keep).reset_index(drop=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--with-rodrigo", action="store_true")
    ap.add_argument("--rodrigo-drop", nargs="*", type=int, default=None,
                    help="incluir a Rodrigo PERO quitando estas clases suyas (p. ej. 5 7 = "
                         "aguacate y otro-perenne, sus clases poco confiables)")
    ap.add_argument("--cap", type=int, default=40000, help="máx. píxeles por clase (0 = sin tope)")
    ap.add_argument("--trees", type=int, default=300)
    ap.add_argument("--groups", default=None,
                    help="CSV class_id->group_id,group_name: entrena con legenda AGRUPADA")
    ap.add_argument("--version", default=None,
                    help="guarda modelo+reporte+tablas en entrenamientos/<version>/")
    args = ap.parse_args()

    df = pd.read_parquet(TABLE)
    feats = [c for c in df.columns if c not in META]
    df = df.dropna(subset=feats).reset_index(drop=True)

    rod = df[df["src_file"] == "rodrigo"]
    if args.with_rodrigo:
        train_df, holdout, rod_mode = df.copy(), df.iloc[0:0], "incluido (todo)"
    elif args.rodrigo_drop:
        keep = rod[~rod["class_id"].isin(args.rodrigo_drop)]
        train_df = pd.concat([df[df["src_file"] != "rodrigo"], keep], ignore_index=True)
        holdout = rod[rod["class_id"].isin(args.rodrigo_drop)].copy()
        rod_mode = f"parcial (sin sus clases {args.rodrigo_drop}; +{len(keep):,} px suyos)"
    else:
        train_df, holdout, rod_mode = df[df["src_file"] != "rodrigo"].copy(), rod.copy(), "excluido (test aparte)"

    # legenda AGRUPADA opcional (id fino -> group_id). El filtro de Rodrigo ya usó ids FINOS.
    if args.groups:
        remap, namer = {}, {}
        with open(args.groups, encoding="utf-8") as gf:
            for r in csv.DictReader(gf):
                remap[int(r["class_id"])] = int(r["group_id"]); namer[int(r["group_id"])] = r["group_name"]
        train_df = train_df.assign(class_id=train_df["class_id"].map(remap))
        if len(holdout):
            holdout = holdout.assign(class_id=holdout["class_id"].map(remap))
        print(f"legenda AGRUPADA: {Path(args.groups).name} -> {len(set(remap.values()))} clases")
    else:
        namer = ID2NAME
    train_df = cap_per_class(train_df, args.cap)

    X = train_df[feats].to_numpy("float32")
    y = train_df["class_id"].to_numpy()
    groups = train_df["tile_id"].to_numpy()
    labels = sorted(train_df["class_id"].unique())
    names = [namer[i] for i in labels]
    n_tiles = train_df["tile_id"].nunique()
    print(f"entrenamiento: {len(train_df)} px | {len(feats)} predictores | {n_tiles} tiles | "
          f"Rodrigo {rod_mode}")

    rf = RandomForestClassifier(n_estimators=args.trees, class_weight="balanced",
                                min_samples_leaf=2, n_jobs=-1, random_state=0)

    # --- validación espacial (out-of-fold) ---
    n_splits = min(5, n_tiles)
    print(f"GroupKFold espacial ({n_splits} folds por tile_id)...")
    oof = cross_val_predict(rf, X, y, groups=groups, cv=GroupKFold(n_splits=n_splits), n_jobs=1)
    rep = classification_report(y, oof, labels=labels, target_names=names, digits=3, zero_division=0)
    cm = confusion_matrix(y, oof, labels=labels)

    # binario aguacate (derivado del multiclase)
    ya, pa = (y == AVOCADO_ID), (oof == AVOCADO_ID)
    tp, fp, fn = int((pa & ya).sum()), int((pa & ~ya).sum()), int((~pa & ya).sum())
    prec = tp / (tp + fp) if tp + fp else 0
    rec = tp / (tp + fn) if tp + fn else 0
    f1 = 2 * prec * rec / (prec + rec) if prec + rec else 0
    acc = float((oof == y).mean())

    # --- modelo final + Rodrigo como test independiente ---
    rf.fit(X, y)
    joblib.dump({"model": rf, "features": feats, "labels": labels}, HERE / "rf_model.pkl")

    rod_lines = "No se evaluó Rodrigo (ya está incluido en el entrenamiento)."
    if len(holdout):
        Xr = holdout[feats].to_numpy("float32")
        yr = holdout["class_id"].to_numpy()
        pr = rf.predict(Xr)
        agree = float((pr == yr).mean())
        am = yr == AVOCADO_ID
        avo_conf = float((pr[am] == AVOCADO_ID).mean()) if am.any() else float("nan")
        per = []
        for c in sorted(set(int(v) for v in yr)):
            mc = yr == c
            per.append(f"    - {namer.get(c, c)}: {int(mc.sum()):,} px, el modelo coincide "
                       f"{100*(pr[mc] == c).mean():.0f}%")
        rod_lines = (f"- Rodrigo como test independiente: **{len(holdout):,} px**, acuerdo global con "
                     f"el modelo verificado (Tona+Mau) **{agree*100:.1f}%**\n"
                     f"- Su AGUACATE ({int(am.sum()):,} px): el modelo lo confirma aguacate en "
                     f"**{avo_conf*100:.1f}%**\n"
                     f"- Acuerdo por clase que etiquetó Rodrigo:\n" + "\n".join(per))
        print(f"\nRODRIGO holdout: acuerdo global {agree*100:.1f}% | su aguacate confirmado {avo_conf*100:.1f}%")

    # --- figuras ---
    fig, axc = plt.subplots(figsize=(9, 8))
    ConfusionMatrixDisplay(confusion_matrix(y, oof, labels=labels, normalize="true"),
                           display_labels=names).plot(ax=axc, cmap="Greens", colorbar=False,
                                                       xticks_rotation=90, values_format=".2f")
    axc.set_title("Matriz de confusión (validación espacial, normalizada por fila)")
    fig.tight_layout(); fig.savefig(HERE / "rf_confusion.png", dpi=130); plt.close(fig)

    imp = pd.Series(rf.feature_importances_, index=feats).sort_values(ascending=True).tail(20)
    fig, axi = plt.subplots(figsize=(7, 7))
    imp.plot.barh(ax=axi, color="#2e7d32"); axi.set_title("Importancia de predictores (top 20)")
    fig.tight_layout(); fig.savefig(HERE / "rf_importances.png", dpi=130); plt.close(fig)

    # --- reporte ---
    md = [f"# RandomForest Fase 1 — reporte\n",
          f"- Entrenamiento: **{len(train_df):,} px**, {len(feats)} predictores, {n_tiles} tiles",
          f"- Rodrigo: {rod_mode}",
          f"- Validación: GroupKFold espacial por `tile_id` ({n_splits} folds)\n",
          f"## Global (out-of-fold)\n",
          f"- Exactitud general: **{acc:.3f}**",
          f"- Aguacate — precisión **{prec:.3f}**, recall **{rec:.3f}**, F1 **{f1:.3f}** "
          f"(TP {tp:,} · FP {fp:,} · FN {fn:,})\n",
          f"## Por clase (out-of-fold)\n", "```", rep, "```\n",
          f"## Rodrigo como test independiente\n", rod_lines, "",
          f"## Figuras\n", "![confusión](rf_confusion.png)\n", "![importancias](rf_importances.png)\n"]
    (HERE / "rf_report.md").write_text("\n".join(md), encoding="utf-8")

    print(f"\nExactitud OOF {acc:.3f} | Aguacate P {prec:.3f} R {rec:.3f} F1 {f1:.3f}")
    print("-> rf_model.pkl, rf_report.md, rf_confusion.png, rf_importances.png")

    if args.version:
        import shutil
        vdir = HERE / "entrenamientos" / args.version
        vdir.mkdir(parents=True, exist_ok=True)
        keep = ["rf_model.pkl", "rf_report.md", "rf_confusion.png", "rf_importances.png",
                "training_table.parquet", "samples.parquet", "samples_inegi.parquet", "labels_merged.gpkg"]
        if args.groups:
            keep.append(Path(args.groups).name)
        for f in keep:
            if (HERE / f).exists():
                shutil.copy2(HERE / f, vdir / f)
        print(f"-> versión guardada en entrenamientos/{args.version}/")


if __name__ == "__main__":
    main()
