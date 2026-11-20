import datetime as dt, sys, io
from PIL import Image
sys.path.insert(0, ".")
from products.gfs_map import render
init = dt.datetime.strptime(sys.argv[1], "%Y%m%d%H").replace(tzinfo=dt.timezone.utc)
for f in [int(x) for x in sys.argv[2].split(",")]:
    im = Image.open(io.BytesIO(render(init, f))).convert("RGB")
    W, H = im.size
    c = im.crop((round(W * 0.10235), 0, round(W * (1 - 0.12485)), round(H * (1 - 0.368))))
    c = c.resize((1780, 992))  # as the slide shows it (8.90 x 4.96 M EMU)
    from PIL import ImageDraw
    k = 1780 / 989.2
    x, y = (625.5 - 131) * k, 306.5 * 992 / 647.2
    d = ImageDraw.Draw(c); d.ellipse((x - 11, y - 11, x + 11, y + 11), fill="black", outline="white", width=3)
    d.text((x + 16, y - 30), "KSC", fill="black")
    c.save(f"out/slide_f{f:03d}.png")
