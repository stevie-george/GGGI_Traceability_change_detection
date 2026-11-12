"""
cnn_data.py — parches de entrenamiento para el CNN (Fase 2) + Dataset de PyTorch.

Objetivo por píxel (enfoque RF -> CNN con candados):
  - etiqueta HUMANA (ancla) donde exista, o
  - clase del RF 04 donde su CONFIANZA sea alta (pseudo-etiqueta densa), o
  - IGNORADO (255, sin pérdida) donde el RF duda y no hay ancla.
Canales de entrada = los 36 predictores del RF 04 (por NOMBRE) + normalizados.

    run_producer.bat cnn_data.py --prepare     # extrae parches -> cnn_patches/  (~45 min, corre en terminal)
"""
import argparse
import csv
from pathlib import Path

import numpy as np
import pandas as pd
import geopandas as gpd
import rasterio
from rasterio.features import rasterize
import joblib
import torch
from torch.utils.data import Dataset

HERE = Path(__file__).resolve().parent
OUT = HERE / "out"
LABELS = HERE / "labels_merged.gpkg"
PATCHDIR = HERE / "cnn_patches"
MODEL = HERE / "entrenamientos" / "entrenamiento_04" / "rf_model.pkl"   # modelo OFICIAL
DEM_BANDS = ["elevation", "slope"]

GROUPS = {}
with open(HERE / "groups.csv", encoding="utf-8") as f:
    for r in csv.DictReader(f):
        GROUPS[int(r["class_id"])] = int(r["group_id"])


def band_names(tile):
    return [ln.split("\t")[1] for ln in (OUT / tile / f"{tile}_bands.txt").read_text(encoding="utf-8").splitlines() if "\t" in ln]


def read_features(tile, feats):
    """Los `feats` (por NOMBRE) de features.tif + dem.tif -> (C,H,W), transform, crs."""
    with rasterio.open(OUT / tile / f"{tile}_features.tif") as s:
        names = band_names(tile)
        arr = s.read().astype("float32")
        H, W, tr = s.height, s.width, s.transform
    dpath = OUT / tile / f"{tile}_dem.tif"
    if dpath.exists():
        with rasterio.open(dpath) as d:
            arr = np.concatenate([arr, d.read().astype("float32")], axis=0)
    names = names + DEM_BANDS
    return arr[[names.index(fn) for fn in feats]], H, W, tr


def prepare(patch=256, stride=192, conf_thr=0.6, min_valid=0.03, limit=None):
    bundle = joblib.load(MODEL)
    rf, feats = bundle["model"], bundle["features"]
    rf.n_jobs = 4
    labels_list = sorted(int(c) for c in bundle["labels"])          # grouped ids presentes
    id2idx = {g: i for i, g in enumerate(labels_list)}              # grouped id -> 0..N-1
    rf_classes = np.array(rf.classes_)

    lab = gpd.read_file(LABELS, layer="labels")
    lab["grp"] = lab["class_id"].map(GROUPS)
    lab = lab[lab["grp"].notna()].copy(); lab["grp"] = lab["grp"].astype(int)
    tiles = sorted(lab["tile_id"].dropna().unique())
    if limit:
        tiles = tiles[:limit]                                        # prueba rápida

    PATCHDIR.mkdir(exist_ok=True)
    tt = pd.read_parquet(HERE / "training_table.parquet")
    mean = tt[feats].mean().to_numpy("float32")
    std = tt[feats].std().to_numpy("float32") + 1e-6
    np.savez(PATCHDIR / "_norm.npz", mean=mean, std=std,
             feats=np.array(feats), labels=np.array(labels_list))

    n_patch = 0
    for ti, tile in enumerate(tiles, 1):
        if not (OUT / tile / f"{tile}_features.tif").exists():
            continue
        X, H, W, tr = read_features(tile, feats)                    # (C,H,W)
        flat = X.reshape(len(feats), -1).T
        valid = ~np.isnan(flat).any(1)
        cls = np.zeros(H * W, "uint8"); conf = np.zeros(H * W, "float32")
        if valid.any():
            p = rf.predict_proba(flat[valid])
            cls[valid] = rf_classes[p.argmax(1)].astype("uint8")
            conf[valid] = p.max(1)
        cls, conf = cls.reshape(H, W), conf.reshape(H, W)

        g = lab[lab["tile_id"] == tile]
        anchor = (rasterize([(geom, int(grp)) for geom, grp in zip(g.geometry, g["grp"])],
                            out_shape=(H, W), transform=tr, fill=0, dtype="int32")
                  if len(g) else np.zeros((H, W), "int32"))
        tgt_grp = np.where(anchor > 0, anchor, cls.astype("int32"))
        mask = ((anchor > 0) | (conf >= conf_thr)) & valid.reshape(H, W)
        tgt = np.full((H, W), 255, "uint8")
        for g_id, ix in id2idx.items():
            tgt[tgt_grp == g_id] = ix
        tgt[~mask] = 255

        Xn = (X - mean[:, None, None]) / std[:, None, None]
        Xn[np.isnan(Xn)] = 0
        Xn = Xn.astype("float16")

        for y0 in range(0, H - patch + 1, stride):
            for x0 in range(0, W - patch + 1, stride):
                m = tgt[y0:y0 + patch, x0:x0 + patch]
                if (m != 255).mean() < min_valid:
                    continue
                np.savez_compressed(PATCHDIR / f"{tile}_{y0}_{x0}.npz",
                                    x=Xn[:, y0:y0 + patch, x0:x0 + patch], y=m)
                n_patch += 1
        print(f"  [{ti}/{len(tiles)}] {tile}: parches {n_patch}", flush=True)
    print(f"\nLISTO: {n_patch} parches -> {PATCHDIR}  ({len(labels_list)} clases)")


class PatchDS(Dataset):
    def __init__(self, files):
        self.files = list(files)

    def __len__(self):
        return len(self.files)

    def __getitem__(self, i):
        d = np.load(self.files[i])
        return torch.from_numpy(d["x"].astype("float32")), torch.from_numpy(d["y"].astype("int64"))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--prepare", action="store_true")
    ap.add_argument("--patch", type=int, default=256)
    ap.add_argument("--stride", type=int, default=192)
    ap.add_argument("--conf-thr", type=float, default=0.6)
    ap.add_argument("--limit", type=int, default=None, help="solo los primeros N tiles (prueba)")
    a = ap.parse_args()
    if a.prepare:
        prepare(a.patch, a.stride, a.conf_thr, limit=a.limit)
    else:
        print("usa --prepare para extraer parches")
