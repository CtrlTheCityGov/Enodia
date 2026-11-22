# Architecture

```
 Citizen (web/citizen.html, ES modules, MapLibre)          Operator (web/operator.html + operator-case.js)
   + → category/subtype, pin, note, photo                     inbox · case · Stoa · decisions · audit · dossier
          │ POST /api/map/reports                                   │ /api/cases/*  (X-Operator-Key)
          ▼                                                         ▼
 FastAPI app (app/main.py + app/routers/*)
   privacy.process_photo()  → blurred, EXIF-free JPEG only (fail-closed)
   categories.normalise()   → city category + Stoa works types + confidence + review flag
   cases.find_canonical()   → open City request ≤ 50 m, same category?  link : create
   sandbox (AthensGov API or mock)  ← City requests, status history
   cases (SQLite): cases · case_links · case_events · match_reviews · dossiers
   stoa_match.match()       → candidates: match type, distance, scope, evidence, uncertainty, confidence
   guarantee.evaluate()     → period basis, start, expiry, state, limitations (deterministic)
   dossier.build/render     → printable HTML (Save as PDF), every fact with ΑΔΑ / label / quote
   /api/track/{id}          → public status only
          ▲
 data/stoa/works.json  ← scripts/fetch_works.py (Διαύγεια + ΚΗΜΔΗΣ open APIs) → stoa_ingest.merge_datasets()
```

**Principles.** AI proposes, rules validate, people decide. Every answer carries a source or says UNKNOWN. The
system records decisions; it never sends anything to a contractor. Pure functions for the engines
(`categories`, `stoa_match`, `guarantee`, `stoa_ingest`, `dossier.build`) so they are unit-tested without I/O.

**Workflow** (`app/cases.py ACTIONS`): NEW → TRIAGED → STOA_INVESTIGATION → EVIDENCE_REVIEW → ENGINEER_DECISION →
LEGAL_REVIEW → APPROVED_ACTION → RESOLVED → CITIZEN_NOTIFIED (or REJECTED). Accept/reject match and dossier need
role *engineer*; Legal approval needs role *legal*; referral to a contractor needs an accepted match and a dossier
that supports a claim (known completion date). Reasons are required for consequential actions.

**Storage.** One SQLite file (`ATHENSONE_DB`, default `data/athensone.db`). Tables are created on start
(`CREATE TABLE IF NOT EXISTS`, additive column migrations). Backup = copy the file and `data/photos/` while the
server is stopped; restore = copy back. Works data is a JSON file with timestamped backups on every refresh.

**Frontend.** No build step. MapLibre 5.3.0 from jsDelivr with a vendored copy as offline fallback. All operator
rendering uses DOM nodes/textContent (no HTML injection of report text).
