"""Lead (first) graphicast on the NWS Melbourne home page."""
import re
from urllib.parse import urljoin

from .common import get, get_image

PAGE = "https://www.weather.gov/mlb/"


def build(out):
    html = get(PAGE).text
    m = re.search(r'(?:src|href)=["\']([^"\']*images/mlb/graphicast/[^"\']+\.(?:png|jpg|gif))', html, re.I)
    if not m:
        raise RuntimeError("no graphicast image found on NWS MLB page")
    url = urljoin(PAGE, m.group(1))
    im = get_image(url).convert("RGB")
    im.save(out / "nws_mlb_lead.png", optimize=True)
    return url
