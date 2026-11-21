"""Accessibility check with axe-core (WCAG 2.0/2.1/2.2 A + AA rules) on every page.

    npm install                      # installs axe-core into node_modules (once)
    pip install playwright && playwright install chromium
    uvicorn app.main:app --port 8000 &   python seed.py --reset
    python scripts/a11y_check.py [--base http://localhost:8000]

Exits 1 if any serious or critical violation is found. Map tiles are third-party images and are ignored.
"""
import argparse
import asyncio
import json
import sys
from pathlib import Path

from playwright.async_api import async_playwright

PAGES = ["/web/citizen.html", "/web/operator.html", "/web/ai-register.html"]
AXE = Path(__file__).resolve().parent.parent / "node_modules" / "axe-core" / "axe.min.js"


async def main(base, chrome):
    if not AXE.exists():
        sys.exit("axe-core missing: run `npm install` in the repo root")
    bad = 0
    async with async_playwright() as p:
        kw = {"executable_path": chrome, "args": ["--no-sandbox"]} if chrome else {}
        b = await p.chromium.launch(**kw)
        for path in PAGES:
            page = await b.new_page(viewport={"width": 420 if "citizen" in path else 1280, "height": 900})
            await page.goto(base + path)
            await page.wait_for_timeout(2500)
            await page.add_script_tag(path=str(AXE))
            res = await page.evaluate("""async () => (await axe.run(document, {
                runOnly: {type: 'tag', values: ['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa', 'wcag22aa']},
                exclude: [['.maplibregl-canvas-container']]})).violations""")
            print(f"\n{path}: {len(res)} violation type(s)")
            for v in res:
                print(f"  [{v['impact']}] {v['id']}: {v['help']} ({len(v['nodes'])} element(s))")
                for n in v["nodes"][:3]:
                    print("      ", n["target"], "-", n.get("failureSummary", "").replace("\n", " ")[:160])
                bad += v["impact"] in ("serious", "critical")
            await page.close()
        await b.close()
    print("\nOK: no serious/critical violations" if not bad else f"\n{bad} serious/critical violation type(s)")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://localhost:8000")
    ap.add_argument("--chrome", default=None, help="path to a Chrome binary (optional)")
    a = ap.parse_args()
    asyncio.run(main(a.base, a.chrome))
