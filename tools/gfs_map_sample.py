import datetime as dt, sys, io
from PIL import Image
sys.path.insert(0, ".")
from products.gfs_map import render
init = dt.datetime.strptime(sys.argv[1], "%Y%m%d%H").replace(tzinfo=dt.timezone.utc)
for f in [int(x) for x in sys.argv[2].split(",")]:
    png = render(init, f)
    im = Image.open(io.BytesIO(png)).convert("RGB")
    im.save(f"out/full_f{f:03d}.png")
    W, H = im.size
    im.crop((round(W * 0.10235), 0, round(W * (1 - 0.12485)), round(H * (1 - 0.368)))).save(f"out/slide_f{f:03d}.png")
    print(f, im.size)
