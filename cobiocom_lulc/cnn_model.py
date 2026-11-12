"""
cnn_model.py — U-Net 2D con atención CBAM para la Fase 2 (refinar el mapa del RF con
contexto espacial). Pensado para caber en la RTX 500 (4 GB): base de canales modesta,
profundidad 4, entrenamiento con mixed-precision (AMP).

CBAM = Convolutional Block Attention Module (Woo et al. 2018): atención de CANAL
(qué bandas importan) + atención ESPACIAL (dónde) — justo lo que pediste ("poner atención
a las características + contexto").
"""
import torch
import torch.nn as nn
import torch.nn.functional as F


class ChannelAttention(nn.Module):
    def __init__(self, ch, r=8):
        super().__init__()
        self.mlp = nn.Sequential(nn.Linear(ch, max(ch // r, 4)), nn.ReLU(inplace=True),
                                 nn.Linear(max(ch // r, 4), ch))

    def forward(self, x):
        b, c, _, _ = x.shape
        avg = self.mlp(F.adaptive_avg_pool2d(x, 1).view(b, c))
        mx = self.mlp(F.adaptive_max_pool2d(x, 1).view(b, c))
        return torch.sigmoid(avg + mx).view(b, c, 1, 1)


class SpatialAttention(nn.Module):
    def __init__(self):
        super().__init__()
        self.conv = nn.Conv2d(2, 1, 7, padding=3, bias=False)

    def forward(self, x):
        avg = x.mean(dim=1, keepdim=True)
        mx = x.max(dim=1, keepdim=True)[0]
        return torch.sigmoid(self.conv(torch.cat([avg, mx], dim=1)))


class CBAM(nn.Module):
    def __init__(self, ch):
        super().__init__()
        self.ca, self.sa = ChannelAttention(ch), SpatialAttention()

    def forward(self, x):
        x = x * self.ca(x)
        x = x * self.sa(x)
        return x


class ConvBlock(nn.Module):
    """2× (conv-BN-ReLU) + CBAM."""
    def __init__(self, cin, cout):
        super().__init__()
        self.net = nn.Sequential(
            nn.Conv2d(cin, cout, 3, padding=1, bias=False), nn.BatchNorm2d(cout), nn.ReLU(inplace=True),
            nn.Conv2d(cout, cout, 3, padding=1, bias=False), nn.BatchNorm2d(cout), nn.ReLU(inplace=True))
        self.cbam = CBAM(cout)

    def forward(self, x):
        return self.cbam(self.net(x))


class UNetCBAM(nn.Module):
    def __init__(self, in_ch, n_classes, base=32, depth=4):
        super().__init__()
        self.depth = depth
        chs = [base * (2 ** i) for i in range(depth + 1)]        # p.ej. 32,64,128,256,512
        self.enc = nn.ModuleList()
        c = in_ch
        for cout in chs[:-1]:
            self.enc.append(ConvBlock(c, cout)); c = cout
        self.pool = nn.MaxPool2d(2)
        self.bottleneck = ConvBlock(chs[-2], chs[-1])
        self.up = nn.ModuleList()
        self.dec = nn.ModuleList()
        for i in range(depth, 0, -1):
            self.up.append(nn.ConvTranspose2d(chs[i], chs[i - 1], 2, stride=2))
            self.dec.append(ConvBlock(chs[i], chs[i - 1]))       # skip concatenado
        self.head = nn.Conv2d(base, n_classes, 1)

    def forward(self, x):
        skips = []
        for blk in self.enc:
            x = blk(x); skips.append(x); x = self.pool(x)
        x = self.bottleneck(x)
        for up, dec, skip in zip(self.up, self.dec, reversed(skips)):
            x = up(x)
            x = dec(torch.cat([x, skip], dim=1))
        return self.head(x)


if __name__ == "__main__":
    import time
    dev = "cuda" if torch.cuda.is_available() else "cpu"
    for patch, batch in [(256, 8), (256, 6), (256, 4), (128, 8)]:
        try:
            torch.cuda.empty_cache() if dev == "cuda" else None
            m = UNetCBAM(in_ch=36, n_classes=10).to(dev)
            opt = torch.optim.Adam(m.parameters(), 1e-3)
            scaler = torch.cuda.amp.GradScaler(enabled=(dev == "cuda"))
            x = torch.randn(batch, 36, patch, patch, device=dev)
            y = torch.randint(0, 10, (batch, patch, patch), device=dev)
            t0 = time.time()
            with torch.autocast(device_type=dev, enabled=(dev == "cuda")):
                out = m(x); loss = F.cross_entropy(out, y)
            scaler.scale(loss).backward(); scaler.step(opt); scaler.update()
            mem = torch.cuda.max_memory_allocated() / 1e9 if dev == "cuda" else 0
            print(f"patch {patch} batch {batch}: OK  {time.time()-t0:.2f}s/step  pico VRAM {mem:.2f} GB")
            del m, opt, x, y, out, loss
            torch.cuda.reset_peak_memory_stats() if dev == "cuda" else None
        except RuntimeError as e:
            print(f"patch {patch} batch {batch}: OOM/err {str(e)[:60]}")
            torch.cuda.empty_cache() if dev == "cuda" else None
