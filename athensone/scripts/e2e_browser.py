"""Browser acceptance test of the central demo workflow (citizen → operator → Stoa → dossier → tracker).

Needs a running server in DEMO mode and Playwright (dev only, not a runtime dependency):
    pip install playwright && python -m playwright install chromium     # once
    MOCK=1 uvicorn app.main:app --port 8000                              # in another terminal
    python scripts/e2e_browser.py --base http://127.0.0.1:8000 [--chrome /usr/bin/google-chrome] [--shots out/]

Exits non-zero on the first failed check. Map tiles may fail offline; that is reported, not fatal.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://127.0.0.1:8000")
    ap.add_argument("--chrome", default=None, help="path to a Chrome/Chromium binary (else Playwright's)")
    ap.add_argument("--shots", default=None, help="folder for screenshots")
    a = ap.parse_args()
    from playwright.sync_api import sync_playwright

    shots = Path(a.shots) if a.shots else None
    if shots:
        shots.mkdir(parents=True, exist_ok=True)
    errors: list[str] = []
    ok = lambda cond, msg: (print(("PASS " if cond else "FAIL ") + msg), cond)[1]  # noqa: E731
    with sync_playwright() as p:
        kw = {"executable_path": a.chrome, "args": ["--no-sandbox"]} if a.chrome else {}
        br = p.chromium.launch(**kw)
        ctx = br.new_context(viewport={"width": 1440, "height": 2400}, locale="el-GR")
        pg = ctx.new_page()
        pg.on("pageerror", lambda e: errors.append(f"citizen: {e}"))
        r = pg.request.post(a.base + "/api/admin/demo-seed")
        if not ok(r.ok, "demo seed"):
            return 1
        pg.goto(a.base + "/web/citizen.html")
        pg.wait_for_selector(".report-fab", timeout=20000)
        pg.click(".report-fab")
        pg.click('button[data-category="damage"]')
        if not ok(pg.is_visible('input[name="subtype"][value="sidewalk"]'), "damage shows the subtype picker"):
            return 1
        pg.check('input[name="subtype"][value="sidewalk"]')
        pg.fill('textarea[name="note"]', "Σπασμένη πλάκα (δοκιμή E2E)")
        pg.click('.report-panel button[type="submit"]')
        pg.wait_for_timeout(2500)
        toast = pg.inner_text("#hud-toast")
        if not ok("MR-" in toast and "Παρακολούθηση" in toast, f"report saved with tracking id: {toast[:80]!r}"):
            return 1
        if shots:
            pg.screenshot(path=str(shots / "1-citizen.png"))

        op = ctx.new_page()
        op.on("pageerror", lambda e: errors.append(f"operator: {e}"))
        op.goto(a.base + "/web/operator.html")
        op.wait_for_selector(".ticket", timeout=15000)
        tickets = op.query_selector_all(".ticket")
        if not ok(len(tickets) >= 3, f"operator inbox shows {len(tickets)} cases"):
            return 1
        op.locator(".ticket", has_text="23.7330").first.click()
        op.wait_for_selector(".cand-card", timeout=10000)
        txt = op.inner_text("#dWorks")
        ok("Ψ0ΣΝΩ6Μ-5ΙΖ" in txt and "ΩΡΙΩΝ" in txt, "Stoa shows the real Diavgeia decision and contractor")
        ok("ΑΓΝΩΣΤ" in txt, "missing completion date is shown as unknown, not invented")
        op.fill("#opActor", "E2E Μηχανικός")
        op.click("text=Έναρξη διερεύνησης Stoa")
        op.wait_for_timeout(1200)
        op.click("text=✔ Αποδοχή αντιστοίχισης >> nth=0")
        op.wait_for_timeout(1200)
        with ctx.expect_page() as newp:
            op.click("text=Φάκελος Εγγύησης")
        d = newp.value
        d.wait_for_load_state()
        dt = d.inner_text("body")
        ok("ΔΕΝ ΕΧΕΙ ΑΠΟΣΤΑΛΕΙ" in dt and "Παράρτημα τεκμηρίων" in dt, "dossier opens with disclaimer and appendix")
        ok("Δεν συντάχθηκε" in dt, "no claim draft while the guarantee is unknown")
        if shots:
            op.screenshot(path=str(shots / "2-operator.png"))
            d.screenshot(path=str(shots / "3-dossier.png"), full_page=True)
        tr = ctx.new_page()
        tr.goto(a.base + "/web/track.html")
        tr.wait_for_timeout(1500)
        ok("MR-" in tr.inner_text("#out"), "citizen tracker lists the report")
        br.close()
    real = [e for e in errors if "tile" not in e.lower()]
    ok(not real, f"no page errors ({len(real)})")
    for e in real:
        print("  ", e[:300])
    return 0 if not real else 1


if __name__ == "__main__":
    sys.exit(main())
