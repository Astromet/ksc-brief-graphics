import json, re
from .viewers import REFS, REFS_VIEW, BROWSER_UA, VW, VH

def explore(out, browser):
    ctx = browser.new_context(viewport={"width": VW, "height": VH}, device_scale_factor=1, user_agent=BROWSER_UA)
    page = ctx.new_page()
    page.goto(f"{REFS}#viewport={REFS_VIEW}&fieldset=members:cref", wait_until="domcontentloaded", timeout=120000)
    page.wait_for_function("() => { const t = document.querySelector('.mpv-time'); const c = document.querySelector('.cal-text');"
                           " return t && c && /\\(F\\d+\\)/.test(t.textContent) && /\\d{2}Z/.test(c.value); }", timeout=120000)
    page.wait_for_timeout(8000)
    info = {"cycle": page.eval_on_selector(".cal-text", "e => e.value"), "time": page.inner_text(".mpv-time")}
    page.screenshot(path=str(out / "viewer.png"))
    page.click(".cal-text"); page.wait_for_timeout(1500)
    page.screenshot(path=str(out / "calendar.png"))
    info["clocks"] = page.evaluate("() => [...document.querySelectorAll('td[data-date]')].slice(-3).map(t => t.dataset.date + ': ' + [...t.querySelectorAll('text')].map(x => x.textContent).join(','))")
    info["fieldsets"] = page.evaluate("() => [...document.querySelectorAll('select option, .mpv-fieldset option')].map(o=>o.textContent).slice(0,80)")
    info["body"] = page.inner_text("body")[:3000]
    (out / "info.json").write_text(json.dumps(info, indent=1))
    return info["cycle"]
