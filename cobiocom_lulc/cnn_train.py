"""
cnn_train.py — entrena el U-Net+CBAM (Fase 2) sobre los parches de cnn_data.py.
Split por TILE (espacial, no por parche). Pérdida: cross-entropy ENMASCARADA
(ignore_index=255) con pesos de clase balanceados. AMP para la RTX 500.

    run_producer.bat cnn_train.py --epochs 40
Salida: cnn_model.pt (mejor por val_acc).
"""
import argparse
import time
from pathlib import Path

import numpy as np
import torch
import torch.nn.functional as F
from torch.utils.data import DataLoader

from cnn_model import UNetCBAM
from cnn_data import PatchDS, PATCHDIR

HERE = Path(__file__).resolve().parent


def tile_of(p):
    return "_".join(p.stem.split("_")[:-2])      # r001c006_768_192 -> r001c006


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--epochs", type=int, default=40)
    ap.add_argument("--batch", type=int, default=8)
    ap.add_argument("--lr", type=float, default=1e-3)
    ap.add_argument("--val-frac", type=float, default=0.2)
    a = ap.parse_args()
    dev = "cuda" if torch.cuda.is_available() else "cpu"

    norm = np.load(PATCHDIR / "_norm.npz", allow_pickle=True)
    labels = [int(x) for x in norm["labels"]]
    n_cls, in_ch = len(labels), len(norm["feats"])
    files = sorted(p for p in PATCHDIR.glob("*.npz") if p.name != "_norm.npz")
    if not files:
        raise SystemExit("no hay parches — corre primero: cnn_data.py --prepare")

    tiles = sorted({tile_of(p) for p in files})
    rng = np.random.default_rng(0); rng.shuffle(tiles)
    valt = set(tiles[:max(1, int(len(tiles) * a.val_frac))])
    tr = [p for p in files if tile_of(p) not in valt]
    va = [p for p in files if tile_of(p) in valt]
    print(f"{len(files)} parches | {len(tr)} train / {len(va)} val | {len(tiles)} tiles | "
          f"{in_ch} canales, {n_cls} clases", flush=True)

    dl_tr = DataLoader(PatchDS(tr), batch_size=a.batch, shuffle=True, drop_last=True)
    dl_va = DataLoader(PatchDS(va), batch_size=a.batch)

    cnt = np.zeros(n_cls)
    for p in tr[:300]:
        y = np.load(p)["y"]; u, c = np.unique(y[y != 255], return_counts=True); cnt[u] += c
    w = torch.tensor(cnt.sum() / (cnt + 1), dtype=torch.float32, device=dev)
    w = w / w.mean()

    m = UNetCBAM(in_ch, n_cls).to(dev)
    opt = torch.optim.Adam(m.parameters(), a.lr)
    scaler = torch.amp.GradScaler("cuda", enabled=dev == "cuda")
    best = 0.0
    for ep in range(1, a.epochs + 1):
        m.train(); t0 = time.time(); tl = 0.0
        for x, y in dl_tr:
            x, y = x.to(dev), y.to(dev); opt.zero_grad()
            with torch.autocast(device_type=dev, enabled=dev == "cuda"):
                loss = F.cross_entropy(m(x), y, weight=w, ignore_index=255)
            scaler.scale(loss).backward(); scaler.step(opt); scaler.update(); tl += loss.item()
        m.eval(); correct = total = 0
        with torch.no_grad():
            for x, y in dl_va:
                with torch.autocast(device_type=dev, enabled=dev == "cuda"):
                    pr = m(x.to(dev)).argmax(1).cpu().numpy()
                yy = y.numpy(); mk = yy != 255
                correct += (pr[mk] == yy[mk]).sum(); total += mk.sum()
        acc = correct / max(total, 1)
        print(f"ep {ep:2d}  loss {tl/len(dl_tr):.3f}  val_acc {acc:.3f}  {time.time()-t0:.0f}s", flush=True)
        if acc > best:
            best = acc
            torch.save({"state": m.state_dict(), "labels": labels, "in_ch": in_ch,
                        "mean": norm["mean"], "std": norm["std"], "feats": norm["feats"]},
                       HERE / "cnn_model.pt")
    print(f"\nmejor val_acc {best:.3f} -> cnn_model.pt")


if __name__ == "__main__":
    main()
