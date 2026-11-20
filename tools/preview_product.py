"""Run one product function into out/ for a preview: python tools/preview_product.py module:function"""
import importlib, sys, traceback
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
out = Path("out"); out.mkdir(exist_ok=True)
mod, fn = sys.argv[1].split(":")
f = getattr(importlib.import_module(f"products.{mod}"), fn)
try:
    if mod in ("viewers", "hrrr_radar", "browser_products"):
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            b = p.chromium.launch(args=["--use-angle=swiftshader", "--enable-unsafe-swiftshader",
                                        "--ignore-gpu-blocklist", "--enable-webgl"])
            print(f(out, b)); b.close()
    else:
        print(f(out))
except Exception:
    traceback.print_exc(); (out / "error.txt").write_text(traceback.format_exc())
