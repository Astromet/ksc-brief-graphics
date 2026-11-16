"""Experiment: fit MAG west-atl map projection to GFS 1000-500 thickness and overlay it."""
import io, json, sys, datetime as dt
import numpy as np, requests
from PIL import Image
from scipy import ndimage, optimize
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pygrib

UA = {"User-Agent": "KSC-brief-graphics (github.com/Astromet/ksc-brief-graphics)"}
cyc, fh, ymd = int(sys.argv[1]), int(sys.argv[2]), sys.argv[3]
mag = "https://mag.ncep.noaa.gov/data/gfs/{c:02d}/west-atl/{p}/gfs_west-atl_{f:03d}_{p}.gif"
thk_gif = Image.open(io.BytesIO(requests.get(mag.format(c=cyc, f=fh, p="1000_500_thick"), headers=UA, timeout=60).content)).convert("RGB")
wnd_gif = Image.open(io.BytesIO(requests.get(mag.format(c=cyc, f=fh, p="10m_wnd_precip"), headers=UA, timeout=60).content)).convert("RGB")
thk_gif.save("out/thk.png"); wnd_gif.save("out/wnd.png")
A = np.asarray(thk_gif).astype(int); B = np.asarray(wnd_gif).astype(int)
brown = lambda M: (M[..., 0] == 139) & (M[..., 1] == 71) & (M[..., 2] == 38)
ca, cb = brown(A), brown(B)
print("coast pixels", ca.sum(), cb.sum(), "overlap", (ca & cb).sum())
# map frame: rows/cols containing coastline/anything non-white within
nonwhite = (B.sum(-1) < 750)
print("size", B.shape)
url = ("https://nomads.ncep.noaa.gov/cgi-bin/filter_gfs_0p25.pl?"
       f"file=gfs.t{cyc:02d}z.pgrb2.0p25.f{fh:03d}&lev_1000_mb=on&lev_500_mb=on&var_HGT=on&subregion="
       "&leftlon=-125&rightlon=-30&toplat=55&bottomlat=-10"
       f"&dir=%2Fgfs.{ymd}%2F{cyc:02d}%2Fatmos")
r = requests.get(url, headers=UA, timeout=120); r.raise_for_status()
open("out/hgt.grb2", "wb").write(r.content)
g = pygrib.open("out/hgt.grb2")
z = {m.level: m for m in g}
z500, lats, lons = z[500].data()
z1000 = z[1000].values
th = (z500 - z1000) / 10.0
lons = np.where(lons > 180, lons - 360, lons)
print("thick range", th.min(), th.max(), lats.min(), lats.max(), lons.min(), lons.max())
np.savez("out/thick.npz", th=th, lats=lats, lons=lons)
red = ((A[..., 0] == 255) & (A[..., 1] == 0) & (A[..., 2] == 0)) | ((A[..., 0] == 0) & (A[..., 1] == 0) & (A[..., 2] == 255))
dist = ndimage.distance_transform_edt(~red)
levels = np.arange(480, 606, 6)
cs = plt.contour(lons, lats, th, levels=levels)
paths = []
for lev, segs in zip(cs.levels, cs.allsegs):
    for s in segs:
        if len(s) > 5:
            paths.append(s)
allpts = np.concatenate(paths)
plt.close("all")
rng = np.random.default_rng(0)
sub = allpts[rng.choice(len(allpts), min(300, len(allpts)), replace=False)]
pts = sub
H, W = red.shape
def merc(lat): return np.degrees(np.log(np.tan(np.pi / 4 + np.radians(lat) / 2)))
def proj(p, kind):
    ax, bx, ay, by = p
    Y = pts[:, 1] if kind == "eq" else merc(pts[:, 1])
    return ax * pts[:, 0] + bx, by - ay * Y
def score(p, kind):
    x, y = proj(p, kind)
    m = (x >= 0) & (x < W - 1) & (y >= 0) & (y < H - 1)
    if m.sum() < 200: return 99.0
    d = ndimage.map_coordinates(dist, [y[m], x[m]], order=1)
    return float(np.mean(np.minimum(d, 15)))
best = None
for kind in ("eq", "merc"):
    for ax in np.arange(12, 30, 1.0):
        for ay in np.arange(12, 30, 1.0):
            # anchor: lon -80 near image center x, lat 20 near center y; scan offsets
            for cx in np.arange(W * 0.2, W * 0.8, 30):
                for cy in np.arange(H * 0.2, H * 0.9, 30):
                    Y20 = 20 if kind == "eq" else merc(20)
                    p = (ax, cx + 80 * ax, ay, cy + ay * Y20)
                    s = score(p, kind)
                    if best is None or s < best[0]:
                        best = (s, kind, p)
print("coarse", best)
pts = allpts
s0, kind, p0 = best
res = optimize.minimize(lambda p: score(p, kind), p0, method="Nelder-Mead", options={"xatol": 0.01, "fatol": 1e-4, "maxiter": 4000})
print("fine", kind, res.fun, list(res.x))
# also try other kind from fitted
other = "merc" if kind == "eq" else "eq"
res2 = optimize.minimize(lambda p: score(p, other), res.x, method="Nelder-Mead", options={"maxiter": 4000})
print("other", other, res2.fun, list(res2.x))
json.dump({"kind": kind, "p": list(res.x), "score": res.fun, "other": [other, res2.fun, list(res2.x)]}, open("out/fit.json", "w"))
# overlay check on the thickness GIF and the wind GIF
def draw(base, name, kind, p):
    ax_, bx, ay, by = p
    Y = lats if kind == "eq" else merc(lats)
    X, YY = ax_ * lons + bx, by - ay * Y
    fig = plt.figure(figsize=(W / 100, H / 100), dpi=100)
    a = fig.add_axes([0, 0, 1, 1]); a.imshow(base); a.set_xlim(0, W); a.set_ylim(H, 0); a.axis("off")
    c = a.contour(X, YY, th, levels=levels, colors="magenta", linestyles="dashed", linewidths=1.2)
    a.clabel(c, fmt="%d", fontsize=9)
    fig.savefig(f"out/{name}", dpi=100); plt.close(fig)
draw(thk_gif, "check_thk.png", kind, res.x)
draw(wnd_gif, "check_wnd.png", kind, res.x)
