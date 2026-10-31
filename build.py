"""Build every briefing graphic into an output folder.

Each product is independent: if one source is down, its previous image (already
copied into the output folder by the workflow) is left in place, and the
failure is recorded in status.json.

Usage: python build.py OUT_DIR [product ...]
"""
import json
import sys
import traceback
from pathlib import Path

from products import climatology, nws_lead, satellite
from products.common import now_utc

PLAIN = {
    "satellite": satellite.build,
    "nws_lead": nws_lead.build,
    "precip_ltg_climo": climatology.precip_ltg,
    "tc_activity": climatology.tc_activity,
    "tc_origin": climatology.tc_origin,
}
BROWSER = ["meteograms", "sounding_climo"]


def main():
    out = Path(sys.argv[1] if len(sys.argv) > 1 else "site")
    out.mkdir(parents=True, exist_ok=True)
    only = set(sys.argv[2:])
    status_path = out / "status.json"
    try:
        status = json.loads(status_path.read_text())
    except Exception:  # noqa: BLE001
        status = {}

    def run(name, fn, *args):
        if only and name not in only:
            return
        t = now_utc().strftime("%Y-%m-%d %H:%MZ")
        try:
            note = fn(out, *args)
            status[name] = {"ok": True, "updated": t, "note": str(note)}
            print(f"[ OK ] {name}: {note}")
        except Exception as e:  # noqa: BLE001
            prev = status.get(name, {})
            status[name] = {"ok": False, "tried": t, "error": f"{type(e).__name__}: {e}",
                            "updated": prev.get("updated")}
            print(f"[FAIL] {name}: {e}")
            traceback.print_exc()

    for name, fn in PLAIN.items():
        run(name, fn)

    if not only or only & set(BROWSER):
        from playwright.sync_api import sync_playwright

        from products import browser_products as bp
        with sync_playwright() as p:
            browser = p.chromium.launch()
            run("meteograms", bp.meteograms, browser)
            run("sounding_climo", bp.sounding_climo, browser)
            browser.close()

    status_path.write_text(json.dumps(status, indent=2))
    rows = "".join(
        f"<tr><td>{k}</td><td>{'OK' if v.get('ok') else 'FAILED'}</td><td>{v.get('updated') or '-'}</td>"
        f"<td>{v.get('note') or v.get('error', '')}</td></tr>" for k, v in sorted(status.items()))
    files = "".join(f'<li><a href="{f.name}">{f.name}</a></li>'
                    for f in sorted(out.iterdir()) if f.suffix in (".png", ".gif"))
    (out / "index.html").write_text(
        "<!doctype html><meta charset=utf-8><title>KSC briefing graphics</title>"
        "<style>body{font-family:sans-serif;margin:24px}td,th{border:1px solid #ccc;padding:4px 8px}"
        "table{border-collapse:collapse}</style><h1>KSC briefing graphics</h1>"
        f"<p>Last run {now_utc():%Y-%m-%d %H:%MZ}</p><table><tr><th>Product</th><th>Status</th>"
        f"<th>Last good update</th><th>Note</th></tr>{rows}</table><h2>Files</h2><ul>{files}</ul>")
    (out / ".nojekyll").write_text("")
    # never fail the job just because one source was down
    return 0


if __name__ == "__main__":
    sys.exit(main())
