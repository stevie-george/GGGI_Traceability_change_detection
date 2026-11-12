"""
cnn_infer.py — aplica el CNN entrenado (cnn_model.pt) a los tiles con ventana deslizante
+ solape (promedia softmax en los bordes). Escribe maps_cnn/<tile>_class.tif coloreado.
Corre en CUDA (o CPU). Para la Fase 3 masiva se exportaría a ONNX->OpenVINO->NPU.

    run_producer.bat cnn_infer.py --tiles r001c006
    run_producer.bat cnn_infer.py --all
"""
import argparse
import csv
from pathlib import Path

import numpy as np
import rasterio
import torch

from cnn_model import UNetCBAM
from cnn_data import read_features, OUT

HERE = Path(__file__).resolve().parent
MAPS_CNN = HERE / "maps_cnn"


def build_cmap(labels):
    leg = {}
    with open(HERE / "legend.csv", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            h = r["color_hex"].lstrip("#")
            leg[int(r["class_id"])] = (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16), 255)
    cmap = {0: (0, 0, 0, 0)}
    for g in labels:                       # grupo 13 (Agricultura) -> color de cultivo anual (9)
        cmap[int(g)] = leg.get(int(g), leg.get(9, (255, 213, 79, 255)))
    return cmap


@torch.no_grad()
def infer_tile(m, dev, mean, std, feats, labels, tile, patch, stride):
    X, H, W, tr = read_features(tile, list(feats))
    with rasterio.open(OUT / tile / f"{tile}_features.tif") as s:
        crs = s.crs
    valid = ~np.isnan(X).any(0)
    Xn = (X - mean[:, None, None]) / std[:, None, None]
    Xn[np.isnan(Xn)] = 0
    Xn = Xn.astype("float32")
    n_cls = len(labels)
    acc = np.zeros((n_cls, H, W), "float32")
    ys = sorted(set(list(range(0, max(H - patch, 0) + 1, stride)) + [max(H - patch, 0)]))
    xs = sorted(set(list(range(0, max(W - patch, 0) + 1, stride)) + [max(W - patch, 0)]))
    for y0 in ys:
        for x0 in xs:
            t = torch.from_numpy(Xn[None, :, y0:y0 + patch, x0:x0 + patch]).to(dev)
            with torch.autocast(device_type=dev, enabled=dev == "cuda"):
                o = torch.softmax(m(t), 1)[0].float().cpu().numpy()
            acc[:, y0:y0 + o.shape[1], x0:x0 + o.shape[2]] += o
    idx = acc.argmax(0)
    cls = np.where(valid, np.array(labels)[idx], 0).astype("uint8")
    return cls, crs, tr, H, W


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tiles", nargs="*", default=None)
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--patch", type=int, default=256)
    ap.add_argument("--stride", type=int, default=192)
    a = ap.parse_args()
    dev = "cuda" if torch.cuda.is_available() else "cpu"

    ck = torch.load(HERE / "cnn_model.pt", map_location=dev)
    labels = [int(x) for x in ck["labels"]]
    feats, mean, std = ck["feats"], np.array(ck["mean"]), np.array(ck["std"])
    m = UNetCBAM(ck["in_ch"], len(labels)).to(dev)
    m.load_state_dict(ck["state"]); m.eval()
    cmap = build_cmap(labels)

    tiles = (sorted(d.name for d in OUT.glob("r*c*") if d.is_dir()) if a.all else (a.tiles or []))
    MAPS_CNN.mkdir(exist_ok=True)
    for i, t in enumerate(tiles, 1):
        if not (OUT / t / f"{t}_features.tif").exists():
            print(f"  {t}: sin features, omito"); continue
        cls, crs, tr, H, W = infer_tile(m, dev, mean, std, feats, labels, t, a.patch, a.stride)
        prof = {"driver": "GTiff", "height": H, "width": W, "count": 1, "dtype": "uint8",
                "nodata": 0, "crs": crs, "transform": tr, "compress": "ZSTD",
                "tiled": True, "blockxsize": 512, "blockysize": 512}
        with rasterio.open(MAPS_CNN / f"{t}_class.tif", "w", **prof) as o:
            o.write(cls, 1); o.write_colormap(1, cmap)
        print(f"  [{i}/{len(tiles)}] {t}: ok", flush=True)
    print(f"-> {MAPS_CNN}/  (abre los _class.tif en QGIS)")


if __name__ == "__main__":
    main()
