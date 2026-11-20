"""Backup precipitable water loop: the CIMSS MIMIC-TPW2 North Atlantic animation cut to
100W-0 (Gulf, Caribbean and the Atlantic out to Africa), equator to 60N. Each frame keeps
its date/time title, latitude/longitude labels and the inch/mm color scale."""
import io

from PIL import Image, ImageChops, ImageDraw

from .common import get

SRC = ("https://tropic.ssec.wisc.edu/real-time/mtpw2/webAnims/tpw_nrl_colors/natl/"
       "mimictpw_natl_latest.gif")
OUT_NAME = "tpw_backup_loop.gif"
SRC_W, SRC_E = -110.0, 10.0     # longitude span of the CIMSS 'natl' map
CUT_W, CUT_E = -100.0, 0.0      # what the slide shows


# map area of the CIMSS 'natl' frame (1000 x 470): x 54-899, y 23-446 (borders just outside)
X0, X1, Y0, Y1 = 54, 900, 23, 447


def build(out):
    src = Image.open(io.BytesIO(get(SRC, timeout=120).content))
    raw = []
    for k in range(getattr(src, "n_frames", 1)):
        src.seek(k)
        raw.append(src.convert("RGB"))
    x0, y0, x1, y1 = X0, Y0, X1, Y1
    px = (x1 - x0) / (SRC_E - SRC_W)
    cx0, cx1 = round(x0 + (CUT_W - SRC_W) * px), round(x0 + (CUT_E - SRC_W) * px)
    W, H = raw[0].size
    frames = []
    for fr in raw:
        left = fr.crop((0, 0, x0, H))                 # latitude labels
        mid = fr.crop((cx0, 0, cx1 + 1, H))           # map + longitude labels below it
        right = fr.crop((x1 + 1, 0, W, H))            # color bar
        title = fr.crop((x0 + 1, 0, x1, y0 - 1))      # date/time title above the map
        canvas = Image.new("RGB", (left.width + mid.width + right.width, H), "white")
        canvas.paste(left, (0, 0))
        canvas.paste(mid, (left.width, 0))
        canvas.paste(right, (left.width + mid.width, 0))
        d = ImageDraw.Draw(canvas)
        # re-centre the title over the narrower map
        d.rectangle((left.width, 0, left.width + mid.width, y0 - 1), fill="white")
        tb = ImageChops.difference(title, Image.new("RGB", title.size, "white")).getbbox()
        if tb:
            t = title.crop(tb)
            canvas.paste(t, (left.width + (mid.width - t.width) // 2, tb[1]))
        # map frame edges where the map was cut, and blank the half-cut edge labels below it
        d.line((left.width, y0, left.width, y1), fill="black", width=1)
        d.line((left.width + mid.width - 1, y0, left.width + mid.width - 1, y1), fill="black", width=1)
        d.rectangle((0, y1 + 2, left.width + 28, H), fill="white")
        d.rectangle((left.width + mid.width - 22, y1 + 2, left.width + mid.width + 14, H), fill="white")
        frames.append(canvas)
    white = Image.new("RGB", frames[-1].size, "white")
    box = ImageChops.difference(frames[-1], white).point(lambda v: 255 if v > 20 else 0).getbbox()
    if box:
        box = (max(0, box[0] - 4), max(0, box[1] - 4), min(white.width, box[2] + 4), min(white.height, box[3] + 4))
        frames = [f.crop(box) for f in frames]
    pal = [f.quantize(colors=255, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE) for f in frames]
    pal[0].save(out / OUT_NAME, save_all=True, append_images=pal[1:],
                duration=[120] * (len(pal) - 1) + [1500], loop=0, optimize=True)
    frames[-1].save(out / "tpw_backup_last.png")
    return f"{len(frames)} frames, {frames[0].size[0]}x{frames[0].size[1]}; map x {x0}-{x1}, cut {cx0}-{cx1}"
