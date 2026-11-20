import sys
from pathlib import Path
sys.path.insert(0, ".")
import importlib
mod, fn = sys.argv[1].split(":")
out = Path("out"); out.mkdir(exist_ok=True)
print(getattr(importlib.import_module(f"products.{mod}"), fn)(out))
