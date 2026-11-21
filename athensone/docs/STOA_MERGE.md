# AthensOne × Stoa × Smart Map: one product

**One-liner (EL):** Μία πόλη, ένας χάρτης: ο πολίτης αναφέρει, η AI τεκμηριώνει, ο Δήμος αποφασίζει, και πριν στείλει συνεργείο βλέπει αν ο ανάδοχος οφείλει ακόμη την επισκευή.

**One-liner (EN):** One map for Athens. Residents report, AI documents, a human decides, and before the City sends its own crew it sees whether a contractor may still owe the repair under guarantee.

## Why combining them makes it stronger, not just bigger

| Piece | Alone | Combined |
|---|---|---|
| AthensOne loop (ask → route → photo report → operator approves) | Reactive: every report costs a crew visit | Every report is checked against works history first |
| Stoa (Diavgeia + ΚΗΜΔΗΣ → works by street → guarantee clock) | Proactive radar, but no reason to open it daily | Opens itself when a complaint lands on a guaranteed street, so engineers use it every day |
| Athens One smart map (7 layers) | A wide but shallow concept | The shared base: reports, cool places, works & guarantees are **live**; parking, waste and events are shown as roadmap, not faked |

The connecting moment for the demo: *a cracked sidewalk is reported → the operator sees "possibly under guarantee until 15/12/2026, contractor X, [ΑΔΑ], quote highlighted" → instead of a municipal crew, a draft dossier to the contractor, which a human reviews and signs.* That's the "reactive and proactive in one tool" line from the Stoa playbook, now built.

## What was added to the repo

| File | What |
|---|---|
| `app/works.py` | Stoa serving layer: loads works records, deterministic guarantee clock (art. 171, 15-month default labelled INFERRED), tiers A/B/?, radar, report↔works matching (≤25 m + category gate), dossier draft |
| `data/works_seed.json` | 5 **fictional** records (SEED-ΑΔΑ-…, "Δείγμα Οδός …"). Covers Tier A, Tier B (default term), ENDED, UNKNOWN, far-future |
| `app/main.py` | `/api/works`, `/api/works/geojson`, `/api/works/radar?days=`, `/api/works/{id}`, `/api/reports/{id}/dossier`, `/api/layers`; every report now carries `guarantee` |
| `web/operator.html` | Radar panel (30/90/180 days, € involved, coverage), works lines on the map, guarantee card with quote + formula, "draft dossier" button, approve button relabelled when a guarantee may apply |
| `web/citizen.html` | Layer chips (Αναφορές, Δροσερά μέρη, Έργα & εγγυήσεις live; Στάθμευση/Αποκομιδή/Εκδηλώσεις "σύντομα"), "what was spent on this street" popup, SEED/LIVE-CACHE banner |
| `seed.py` | Adds a cracked-sidewalk report on "Δείγμα Οδός Α" for the Stoa moment |
| `tests/test_smoke.py` | Guarantee rules, radar, layers, report→guarantee→dossier |

## Plugging in real Stoa data (the one thing that makes it real)

Write the pipeline output to `data/stoa/works.json` (or set `STOA_WORKS_PATH`). Same shape as the seed file, with `"source": "LIVE-CACHE"` and the snapshot date. The app picks it up without a restart, and the banners switch from SEED to LIVE-CACHE.

Minimum per record: `id`, `works_type` (sidewalk|ramp|paving|asphalt|lighting), `resolution` ("street" or "district"), `street`, `contractor`, `amount_paid_eur`, `completion_date`, `guarantee_months` (each `{value, label, source:{ada,page}, quote}`), `final_acceptance`, `geometry` (LineString from OSM). Unverified quote → `label: "UNKNOWN"`; the app then shows no date instead of guessing.

**Realistic scope for this weekend:** one person runs the Stoa ingest for **one district (Pangrati's)** only: Diavgeia works decisions from the last ~3 years → snippets → local model → quote check → hand-confirm the 3–4 demo streets. Even 10–20 real, verified records beat 3,000 unverified ones on stage. If it isn't ready by Sunday 10:00, pitch on SEED and say so.

## Pitch changes (5–6 min)

1. **Maria** (unchanged, 50 s).
2. **Live demo** (2.5 min): the existing loop, then one extra beat (30 s): the operator opens the cracked-sidewalk report → Stoa card → "possibly under guarantee, quote from the decision" → draft dossier → "a person signs; nothing is sent".
3. **One map** (30 s): toggle layers; "three live today, three need City data. We show them as next, we don't fake them."
4. **Money** (45 s): keep SAVINGS.md, and add *"works worth €X may still be under guarantee"* **only** from real LIVE-CACHE numbers. On SEED, give no number.
5. **Next 90 days**: pilot in one Δημοτική Κοινότητα with Public Works + Legal + the 1595/Novoville team.

Judge Q: *"Is the contractor really liable?"* → "We say *possibly within the guarantee period*, with the source sentence. Public Works and Legal Services decide." Confirm art. 171 wording with a mentor before the pitch.

## Cuts (do not build this weekend)
Parking, waste routing, events, Give & Share, Your Voice: roadmap chips only. Ask Stoa, DCAT/NGSI-LD and the replicate demo are P2, only if the radar runs on real data by Sunday morning.
