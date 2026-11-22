# Demo guide · Report → Stoa → decision (≈ 5 minutes)

## 0. Setup (once, on the presenting laptop)

```bash
cd athensone
python -m venv .venv
.venv/bin/pip install -r requirements.txt          # Windows: .venv\Scripts\pip install -r requirements.txt
.venv/bin/pip install --no-deps deface==1.5.0      # better face blur (see requirements.txt note)
```
Optional, while online, so district matching works offline later: start once with `CKAN_MODE=live` and open the
operator console (snapshots are saved to `data/ckan/`).

## 1. Start (every rehearsal and the real run)

```bash
bash scripts/run_demo.sh                 # macOS/Linux
powershell -ExecutionPolicy Bypass -File scripts\run_demo.ps1     # Windows
```
It starts the server on http://127.0.0.1:8000 with the mock sandbox, `DEMO_MODE=1`, `STOA_TODAY=2026-11-22`
(same guarantee numbers every time), and seeds two cases. Open two windows side by side:

- Citizen: http://127.0.0.1:8000/web/citizen.html
- Operator: http://127.0.0.1:8000/web/operator.html

**Reset at any time:** «↺ Επαναφορά demo» (operator header) or `curl -X POST http://127.0.0.1:8000/api/admin/demo-seed`.

Expected after reset: two cases in the inbox, both «Ζημιά · Πεζοδρόμιο».
| Case | Where | Stoa shows | Guarantee |
|---|---|---|---|
| REQ-1001 | Ερμού (37.9757, 23.7330) | **real** Διαύγεια decision Ψ0ΣΝΩ6Μ-5ΙΖ, ΩΡΙΩΝ Α.Τ.Ε., €200.023,43 paid | **Άγνωστη**: completion certificate not published → no date, dossier asks for it |
| REQ-1002 | Υμηττού (37.9693, 23.7462) | **SEED** record W-SEED-002 (labelled «SEED · όχι πραγματικό έργο») | Πιθανώς ενεργή έως 15/05/2027 (contract term + certificate, both synthetic) |

## 2. The story (say this, click this)

1. **Citizen map.** "Μαρία walks down Ermou and sees broken paving." Press **+** → **Ζημιά** → choose
   **Πεζοδρόμιο** → drag the pin onto the existing red pin on Ermou (it must land within 50 m) → note → (photo
   optional) → **Αποστολή**. Toast: «Αναφορά MR-… καταχωρήθηκε · Συνδέθηκε με υπάρχουσα αναφορά στο ίδιο σημείο».
   *Point out:* faces and plates are blurred on the server before anything is stored.
2. **Operator inbox.** REQ-1001 now shows «👥 2 αναφορές». "Duplicates don't vanish; they strengthen the case."
3. Open REQ-1001. Show **«Αναφορές πολιτών για αυτό το σημείο · 2»** (and «Αποσύνδεση» = reversible merge).
4. **Classification:** «Πεζοδρόμιο · μέθοδος citizen_subtype · 90%».
5. Fill «Ποιος αποφασίζει», press **🔎 Έναρξη διερεύνησης Stoa**.
6. **The key moment:** the Stoa card. Real ΑΔΑ link to Διαύγεια (open it), contractor, payment, ΑΔΑΜ,
   each with its source. The match says **«Μόνο γεωγραφική εγγύτητα / Δ.Κ.»**, not "this is the contractor's fault",
   and *why*: the decision covers the 1st–3rd districts; the Ermou segment is our drawing.
7. **Guarantee: Άγνωστη.** "We don't invent a date. The completion certificate isn't public, so Stoa says so and
   tells the engineer what to request." Accept the match → **📄 Φάκελος Εγγύησης**: the dossier opens with
   «ΔΕΝ ΕΧΕΙ ΑΠΟΣΤΑΛΕΙ», the evidence appendix, the missing items, and **no claim draft**.
   Try **⚖️ Παραπομπή σε ανάδοχο** → refused: evidence insufficient. *This refusal is a feature.*
8. **Contrast with the complete case:** open REQ-1002 (SEED, clearly labelled). Start Stoa → accept → dossier:
   computed clock «15/02/2026 → έναρξη 16/02/2026 + 15 μήνες (όρος σύμβασης) = 15/05/2027», quotes with page,
   and a **draft** claim marked as not an issued notice.
9. **Human approval:** **Παραπομπή σε ανάδοχο** with a reason → stage «Νομική». Switch «Ρόλος» to
   **Νομική Υπηρεσία** → **Έγκριση**. Then **Επιλύθηκε** → **Ενημέρωση πολίτη** with a message.
   Open «Ιστορικό ενεργειών (audit)»: every step with name, role, time and reason.
10. **Back to the citizen:** «Οι αναφορές μου» (top-left on the map) → status «Αποκαταστάθηκε», the city's message,
    «Διορθώθηκε; Ναι / Όχι». No contractor names, no internal notes.

## 3. Troubleshooting

| Symptom | Fix |
|---|---|
| Map is grey / no tiles | Venue network. The vendored MapLibre still loads; the console works without the map. Keep going. |
| New report not linked as duplicate | Pin was > 50 m away or a different subtype. Use «Αποσύνδεση»/reset and retry; or show the link with REQ-1001's existing support count. |
| «Δεν επιτρέπεται: this action requires role 'legal'» | Change «Ρόλος» to Νομική Υπηρεσία. That gate is intentional. |
| 403 «operator authorization required» | `OPERATOR_KEY` is set: the console asks for it once per tab. |
| Numbers differ from this guide | `STOA_TODAY` not set; use `run_demo.sh`. |
| Port 8000 busy | `PORT=8010 bash scripts/run_demo.sh`. |

Automated check of this flow: `python scripts/e2e_browser.py --base http://127.0.0.1:8000` (needs Playwright).
