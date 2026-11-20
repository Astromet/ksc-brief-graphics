"""Backup precipitable water loop: CIMSS MIMIC-TPW2 global animation cropped to the Gulf,
Caribbean and Atlantic basin east to Africa and south to 20S, enlarged for the slide,
with each frame's date/time and the inch/mm color scale kept."""
import io

from PIL import Image, ImageDraw

from .common import font, get

SRC = ("https://tropic.ssec.wisc.edu/real-time/mtpw2/webAnims/tpw_nrl_colors/global2/"
       "mimictpw_global2_latest.gif")
OUT_NAME = "tpw_backup_loop.gif"
# global2 frame (1000 x 470), equirectangular: x = X0 + lon_east_of_0 * PX ; y = Y0 - lat * PY
X0, PX = 853.0, 2.35      # x of 0 deg longitude (Pacific-centred map, 20E at the left edge)
Y0, PY = 233.5, 2.344     # y of the equator
LON_W, LON_E, LAT_N, LAT_S = -100.0, 20.0, 45.0, -20.0
SCALE = 3
TITLE_BOX = (270, 0, 700, 21)      # "Total Precipitable Water  YYYY-MM-DD HHMM UTC"
BAR_BOX = (903, 18, 995, 454)      # color scale with inch and mm labels


def _crop_box():
    return (round(X0 + LON_W * PX), round(Y0 - LAT_N * PY), round(X0 + LON_E * PX), round(Y0 - LAT_S * PY))


def frame(src_rgb):
    box = _crop_box()
    mw, mh = (box[2] - box[0]) * SCALE, (box[3] - box[1]) * SCALE
    m = src_rgb.crop(box).resize((mw, mh), Image.LANCZOS)
    t = src_rgb.crop(TITLE_BOX)
    t = t.resize((t.width * 2, t.height * 2), Image.LANCZOS)
    b = src_rgb.crop(BAR_BOX)
    bh = mh
    b = b.resize((round(b.width * bh / b.height), bh), Image.LANCZOS)
    W, H = mw + b.width + 10, mh + t.height + 6
    out = Image.new("RGB", (W, H), "white")
    out.paste(t, ((mw - t.width) // 2, 2))
    out.paste(m, (0, t.height + 6))
    out.paste(b, (mw + 10, t.height + 6))
    ImageDraw.Draw(out).rectangle((0, t.height + 6, mw - 1, H - 1), outline="black", width=2)
    return out


def build(out):
    src = Image.open(io.BytesIO(get(SRC, timeout=120).content))
    frames = []
    for k in range(getattr(src, "n_frames", 1)):
        src.seek(k)
        frames.append(frame(src.convert("RGB")))
    pal = [f.quantize(colors=255, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE) for f in frames]
    pal[0].save(out / OUT_NAME, save_all=True, append_images=pal[1:],
                duration=[120] * (len(pal) - 1) + [1500], loop=0, optimize=True)
    frames[-1].save(out / "tpw_backup_last.png")
    return f"{len(frames)} frames, {frames[0].size[0]}x{frames[0].size[1]}"
