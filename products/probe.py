"""Debug: check other sources for today's 12Z KXMR sounding."""
from .common import get, now_utc


def run(out):
    t = now_utc()
    d = t.strftime("%Y%m%d")
    urls = {
        "spc_gif": f"https://www.spc.noaa.gov/exper/soundings/{t:%y%m%d}12_OBS/XMR.gif",
        "spc_list": f"https://www.spc.noaa.gov/exper/soundings/{t:%y%m%d}12_OBS/",
        "iem": f"https://mesonet.agron.iastate.edu/json/raob.py?ts={d}1200&station=KXMR",
        "uwyo": f"https://weather.uwyo.edu/wsgi/sounding?datetime={t:%Y-%m-%d}%2012:00:00&id=74794&src=UNKNOWN&type=TEXT:LIST",
        "cod": "https://weather.cod.edu/analysis/raob/",
    }
    lines = []
    for k, u in urls.items():
        try:
            r = get(u, tries=1, timeout=40)
            body = r.content
            (out / f"probe_{k}.bin").write_bytes(body)
            lines.append(f"{k}: {r.status_code} {len(body)} bytes {r.headers.get('Content-Type')} | "
                         + body[:300].decode("latin1").replace("\n", " "))
        except Exception as e:  # noqa: BLE001
            lines.append(f"{k}: FAILED {e}")
    (out / "probe.txt").write_text("\n".join(lines))
    return "\n".join(lines)
