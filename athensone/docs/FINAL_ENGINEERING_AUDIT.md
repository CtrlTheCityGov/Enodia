# AthensOne · Final engineering audit (22 Nov 2026, before the 12:00 freeze)

Scope: the central report → operator → Stoa → decision → citizen workflow, its data, and the reliability of the demo.
Method: read the code paths, then ran them through FastAPI's TestClient, a real server and headless Chrome.
Every finding below has a fix in this change set unless it says **OPEN**.

## Implementation map (what actually runs)

| Module | Backend | Storage | Frontend | Data | End-to-end |
|---|---|---|---|---|---|
| Citizen map reports («+») | `POST/GET /api/map/reports` (`app/routers/map_reports.py`) | SQLite `map_reports` | `web/js/ui/report.js` | live (local DB) | ✅ |
| Legacy photo report | `POST /api/report` (`app/main.py`) | SQLite `reports` + sandbox | `web/citizen-legacy.html` | live / mock sandbox | ✅ |
| City requests | AthensGov sandbox client (`app/sandbox.py`) | sandbox (mock = in memory) | operator | mock without `SANDBOX_KEY` | ✅ mock; live untested here |
| **Cases, duplicates, workflow, audit** (new) | `/api/cases/*` (`app/routers/cases.py`, `app/cases.py`) | SQLite `cases`, `case_links`, `case_events`, `match_reviews`, `dossiers` | `web/operator-case.js` | live | ✅ |
| **Category normalisation** (new) | `app/categories.py` | stored on the case | report subtype picker | rules | ✅ |
| **Stoa matching** (new) | `app/stoa_match.py` | – | case panel | `data/stoa/works.json` | ✅ |
| **Guarantee engine** (new) | `app/guarantee.py` | – | case panel, dossier | same | ✅ |
| **Evidence dossier** (new) | `app/dossier.py`, `GET /api/cases/{id}/dossiers/{d}` | SQLite `dossiers` (snapshot per generation) | opens in new tab, print → PDF | same | ✅ |
| **Citizen tracker** (new) | `GET /api/track/{id}` | – | `web/track.html` | live | ✅ |
| Works ingestion | `scripts/fetch_works.py`, `app/works_src.py`, **`app/stoa_ingest.py`** (new merge) | `data/stoa/works.json` | – | 10 real Diavgeia + 2 SEED, snapshot 21 Nov | parsers tested on fixtures; **live fetch not run here** (network blocked) |
| Ask Stoa, radar, works layer | `app/stoa_ask.py`, `/api/works/*` | works.json | operator, citizen | same | ✅ (unchanged) |
| Navigation, transit, env, health, points | existing routers | various caches | citizen HUD | live with cached fallbacks | unchanged; existing tests pass |

## Findings

| # | Severity | Finding | Fix |
|---|---|---|---|
| F-1 | Critical | A citizen «Ζημιά» report became sandbox category `other`; Stoa only looked up sandbox categories, so **a damaged sidewalk from the new map never reached Stoa**. | `app/categories.py`: one normalisation layer (citizen subtype → keywords → fallback, confidence, review flag, original kept). Map form gained «Τι έχει ζημιά;». |
| F-2 | Critical | Duplicates **disappeared**: the map flow stored the report but created no City request, and the legacy flow dropped photo + note and only upvoted. | Every submission is kept and linked to the open canonical case (`case_links`), support count shown, the operator can reverse a merge (own City request + own case). |
| F-3 | High (data) | `W-DIAV-009` stored the issue date of a *guarantee-return* decision (type 2.4.7.1) as a **CITED completion date**. Verified against `diavgeia.gov.gr/opendata/decisions/ΨΓΟ3Ω6Μ-ΔΚ6.json`. | Completion set to UNKNOWN; recorded as `final_acceptance_evidence` (INFERRED) → REQUIRES_HUMAN_REVIEW. Logged in `works.json → corrections`. |
| F-4 | High (data) | 3 records mistyped as `sidewalk` (road surfacing, street lighting, vehicle access control); W-SEED-001 («Μητροπόλεως») drawn on top of the real Ermou record. | Types corrected from decision titles; SEED-001 moved ~90 m south; all logged. |
| F-5 | High | Matching treated any works line within 25 m as the match. District- and city-wide framework contracts are drawn as *representative* segments, so proximity looked like responsibility. The "(τμήμα X)" suffix is ours, not the decision's. | `app/stoa_match.py`: scope read from the title (street / district / neighbourhood / municipality), match types EXACT → PROXIMITY with evidence and uncertainty lists; annotation and representative geometry are stated as uncertainties; human accept/reject stored as a correction log. |
| F-6 | High | Approving was one click with no name, no reason, no legal step; nothing stopped a "claim" on an unknown guarantee. | Auditable workflow (`app/cases.py`): stages NEW → … → CITIZEN_NOTIFIED, actor required, reason for consequential steps, role gate for engineer / Legal, contractor referral only with an accepted match **and** a dossier that supports a claim. Old endpoints kept for compatibility and logged. Test `A8` updated accordingly. |
| F-7 | High | Guarantee clock: fixed 15 months labelled INFERRED, no ≤ €250k caveat, start on the certificate day instead of the next day, no conflict handling. | `app/guarantee.py`: Art. 171 as replaced by ν. 4782/2021 art. 85; basis labels (CONTRACTUALLY_VERIFIED / OFFICIALLY_DOCUMENTED / LEGAL_DEFAULT / INFERRED / UNKNOWN), states (ACTIVE / EXPIRED / UNKNOWN / REQUIRES_HUMAN_REVIEW), no date without a certificate. |
| F-8 | High | `scripts/fetch_works.py` **overwrote** `works.json`, which would erase the verified records and corrections on the next refresh. | `app/stoa_ingest.py`: field-level merge (never downgrade, conflicts recorded, missing records kept, provenance), timestamped backup; `--replace` to opt out. |
| F-9 | Medium | Tests wrote into the demo database and photo folder. | `ATHENSONE_DB` / `ATHENSONE_PHOTO_DIR`; `tests/conftest.py` uses a temp folder. |
| F-10 | Medium | Operator console loaded data only after the map's `load` event: with a blocked CDN/tiles (venue Wi-Fi) the console stayed **empty**. | Data loads independently; map calls guarded; MapLibre 5.3.0 vendored as an offline fallback (BSD-3, `THIRD_PARTY.md`). |
| F-11 | Medium | Operator inbox rebuilt every 5 s, so clicks could miss. | Rebuild only on change. |
| F-12 | Medium | Citizen had no way to follow a map report. | Tracking id in the confirmation toast, «Οι αναφορές μου» page, public tracker with no internal data, «Διορθώθηκε;» loop. |
| F-13 | Medium (security) | `/api/admin/reset`, CSV export and report reads were open even with `OPERATOR_KEY` set; key compared with `!=`. Operator page never sent the key. | Protected; constant-time compare; console asks for the key once per tab. Demo seeding only in `DEMO_MODE` + mock sandbox. |
| F-14 | Low | Note length unbounded on map reports. | 2000-char limit. |
| F-15 | **OPEN** | Operator identity is self-declared (name + role in the console) behind one shared key. Fine for a demo, not for production. | Documented in `KNOWN_LIMITATIONS.md` / `SECURITY.md`. |
| F-16 | **OPEN** | District lookup needs the AthensGov CKAN portal (or a saved snapshot in `data/ckan/`). Offline, district-scoped contracts fall back to PROXIMITY (honest, weaker). | Run once online with `CKAN_MODE=live` to save snapshots. |
| F-17 | **OPEN** | No PDF/OCR document extraction yet: quotes exist only where a record carries one; real records have metadata-level citations. | See `KNOWN_LIMITATIONS.md`. |

## Tests (run 22 Nov 2026, ~04:00 Athens)

| Suite | Run | Passed | Failed | Skipped |
|---|---|---|---|---|
| Python `pytest` (all, offline) | 208 | 208 | 0 | 0 |
| JS `node --test web/tests/*.test.js` | 106 | 106 | 0 | 0 |
| Browser `scripts/e2e_browser.py` (headless Chrome, real server) | 10 checks | 10 | 0 | – |

- Baseline before changes: 181/182 Python (1 failed only because `deface` was not installed: `pip install --no-deps deface==1.5.0`), 106/106 JS.
- New: `tests/test_C1_casework.py` (26 tests): categories, guarantee edge cases (missing date, contract term, legal default ≤ €250k, expired, conflicts, guarantee return), matching types, duplicate link + unlink, legacy duplicate kept, role/reason/actor enforcement, blocked referral, full audited SEED flow, tracker privacy, operator key, demo determinism, ingestion merge.
- One existing test changed: `web/tests/A8_track_a.test.js` pinned the removed one-click buttons; it now checks the new workflow controls (F-6). No test was skipped or disabled.
- Live integrations tested: **none** in this environment (Διαύγεια, ΚΗΜΔΗΣ, CKAN, tiles and CDN are blocked here). Διαύγεια decisions ΨΓΟ3Ω6Μ-ΔΚ6 and Ψ0ΣΝΩ6Μ-5ΙΖ were checked through a web fetch. Everything else used fixtures.
