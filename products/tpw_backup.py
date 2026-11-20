"""Backup precipitable water loop: the CIMSS MIMIC-TPW2 North Atlantic animation
(110W-10E, equator-60N: Gulf, Caribbean and the Atlantic out to Africa), trimmed of its
white margins, with each frame's date/time and the inch/mm color scale kept."""
import io

from PIL import Image, ImageChops

from .common import get

SRC = ("https://tropic.ssec.wisc.edu/real-time/mtpw2/webAnims/tpw_nrl_colors/natl/"
       "mimictpw_natl_latest.gif")
OUT_NAME = "tpw_backup_loop.gif"


def build(out):
    src = Image.open(io.BytesIO(get(SRC, timeout=120).content))
    frames = []
    for k in range(getattr(src, "n_frames", 1)):
        src.seek(k)
        frames.append(src.convert("RGB"))
    # one trim box for all frames (the white page margin around map, title and color bar)
    white = Image.new("RGB", frames[0].size, "white")
    box = ImageChops.difference(frames[-1], white).point(lambda v: 255 if v > 20 else 0).getbbox()
    if box:
        box = (max(0, box[0] - 4), max(0, box[1] - 4), min(frames[0].width, box[2] + 4), min(frames[0].height, box[3] + 4))
        frames = [f.crop(box) for f in frames]
    pal = [f.quantize(colors=255, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE) for f in frames]
    pal[0].save(out / OUT_NAME, save_all=True, append_images=pal[1:],
                duration=[120] * (len(pal) - 1) + [1500], loop=0, optimize=True)
    frames[-1].save(out / "tpw_backup_last.png")
    return f"{len(frames)} frames, {frames[0].size[0]}x{frames[0].size[1]}"
