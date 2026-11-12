"""
cnn_eval.py — A/B honesto: RF-04 vs CNN contra las ANCLAS HUMANAS (consultores),
en los tiles de VALIDACIÓN (mismo split/semilla que cnn_train). Reporta, por clase,
la exactitud de cada modelo sobre los píxeles etiquetados a mano.

Caveat de interpretación: el RF-04 SÍ vio estos píxeles de ancla en su entrenamiento
(sample.py muestrea de todos los tiles), mientras que el CNN NO (split por tile ->
estos tiles quedaron fuera). Es decir, el RF juega "de local": si el CNN empata o
gana aquí, es un resultado fuerte.

    run_producer.bat cnn_eval.py
"""
import csv
from pathlib import Path

import numpy as np
import geopandas as gpd
from rasterio.features import rasterize
import joblib
import torch

from cnn_model import UNetCBAM
from cnn_data import read_features, OUT, LABELS, PATCHDIR, GROUPS, MODEL
from cnn_infer import infer_tile
from cnn_train import tile_of

HERE = Path(__file__).resolve().parent
VAL_FRAC = 0.2


def class_names(ids):
    leg = {}
    try:
        with open(HERE / "legend.csv", encoding="utf-8") as f:
            for r in csv.DictReader(f):
                leg[int(r["class_id"])] = r.get("class_name", f"clase {r['class_id']}")
    except Exception:
        pass
    nm = {g: leg.get(g, f"clase {g}") for g in ids}
    if 13 in nm:
        nm[13] = "Agricultura"
    if 10 in nm:
        nm[10] = "Urbano/Suelo"
    return nm


def main():
    # split de validación idéntico a cnn_train (misma semilla, mismos parches en disco)
    files = sorted(p for p in PATCHDIR.glob("*.npz") if p.name != "_norm.npz")
    if not files:
        raise SystemExit("no hay parches en cnn_patches/ — no puedo reproducir el split")
    tiles_all = sorted({tile_of(p) for p in files})
    rng = np.random.default_rng(0)
    rng.shuffle(tiles_all)
    valt = sorted(tiles_all[:max(1, int(len(tiles_all) * VAL_FRAC))])
    print(f"{len(valt)} tiles de validación: {valt}", flush=True)

    bundle = joblib.load(MODEL)
    rf, feats = bundle["model"], bundle["features"]
    rf.n_jobs = 4
    rf_classes = np.array(rf.classes_)

    dev = "cuda" if torch.cuda.is_available() else "cpu"
    ck = torch.load(HERE / "cnn_model.pt", map_location=dev)
    labels = [int(x) for x in ck["labels"]]
    mean, std = np.array(ck["mean"]), np.array(ck["std"])
    m = UNetCBAM(ck["in_ch"], len(labels)).to(dev)
    m.load_state_dict(ck["state"]); m.eval()

    lab = gpd.read_file(LABELS, layer="labels")
    lab["grp"] = lab["class_id"].map(GROUPS)
    lab = lab[lab["grp"].notna()].copy(); lab["grp"] = lab["grp"].astype(int)

    acc = {g: np.zeros(3, dtype=np.int64) for g in labels}      # g -> [n_ancla, rf_ok, cnn_ok]
    for i, tile in enumerate(valt, 1):
        if not (OUT / tile / f"{tile}_features.tif").exists():
            print(f"  {tile}: sin features, omito"); continue
        g = lab[lab["tile_id"] == tile]
        if len(g) == 0:
            print(f"  {tile}: sin anclas, omito"); continue
        X, H, W, tr = read_features(tile, feats)
        valid = ~np.isnan(X).any(0)
        anchor = rasterize([(geom, int(gr)) for geom, gr in zip(g.geometry, g["grp"])],
                           out_shape=(H, W), transform=tr, fill=0, dtype="int32")
        sel = (anchor > 0) & valid
        idx = np.flatnonzero(sel.reshape(-1))
        if idx.size == 0:
            print(f"  {tile}: anclas fuera de zona válida, omito"); continue

        flat = X.reshape(len(feats), -1).T
        rf_at = rf_classes[rf.predict_proba(flat[idx]).argmax(1)].astype("int32")   # solo píxeles de ancla
        cnn_pred, *_ = infer_tile(m, dev, mean, std, ck["feats"], labels, tile, 256, 192)
        cnn_at = cnn_pred.reshape(-1)[idx].astype("int32")
        anc_at = anchor.reshape(-1)[idx].astype("int32")

        for gid in labels:
            gsel = anc_at == gid
            n = int(gsel.sum())
            if n == 0:
                continue
            acc[gid][0] += n
            acc[gid][1] += int((rf_at[gsel] == gid).sum())
            acc[gid][2] += int((cnn_at[gsel] == gid).sum())
        print(f"  [{i}/{len(valt)}] {tile}: {idx.size} px de ancla", flush=True)

    names = class_names(labels)
    tot = np.zeros(3, dtype=np.int64)
    print("\n clase                  n_ancla     RF    CNN      Δ")
    print(" " + "-" * 53)
    for gid in labels:
        n, rfk, cnk = acc[gid]
        tot += acc[gid]
        if n == 0:
            continue
        print(f" {names[gid]:<20} {n:>9} {rfk/n:6.3f} {cnk/n:6.3f} {cnk/n - rfk/n:+6.3f}")
    N, RFK, CNK = tot
    print(" " + "-" * 53)
    if N:
        print(f" {'GLOBAL':<20} {N:>9} {RFK/N:6.3f} {CNK/N:6.3f} {(CNK - RFK)/N:+6.3f}")
    print("\n(RF jugó de local: vio estos píxeles en su entrenamiento; el CNN no.)")


if __name__ == "__main__":
    main()
