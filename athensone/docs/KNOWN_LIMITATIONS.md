# Known limitations (read before the judges ask)

## Data and Stoa
- **Works data is a snapshot** (`data/stoa/works.json`, 21 Nov 2026): 10 real Municipality of Athens decisions
  verified on Διαύγεια + 2 clearly marked SEED records. It is not a live connection. The refresh script
  (`scripts/fetch_works.py`) calls the documented open APIs of Διαύγεια (`/opendata/search.json`) and ΚΗΜΔΗΣ
  (`/khmdhs-opendata/contract`, no key) and now merges without overwriting, but it was **not run** in the final
  build environment (network blocked).
- **No completion certificates are published** for the real records, so every real guarantee is **UNKNOWN**. Only the
  SEED record shows a computed clock. This is the honest state of public data, and Stoa says so.
- **Geometry of real works is representative.** Decisions name districts or the whole municipality, not street
  segments; the lines on the map are our drawing and are labelled as such in every match.
- **District lookup** needs the AthensGov CKAN portal or a saved snapshot. Offline, district contracts are shown as
  PROXIMITY (weaker), not as a district match.
- **No PDF/OCR extraction yet.** Citations for real records point to the decision's metadata (ΑΔΑ, type, amount,
  contractor from `extraFieldValues`), page 1. There are no verbatim contract quotes for real records; SEED
  quotes are synthetic and marked. Next step: PyMuPDF text layer, then OCRmyPDF/Tesseract (`ell`) for scans, with
  page numbers and a low-confidence flag.
- **Legal rule:** 15 months is the general rule of Art. 171 ν. 4412/2016 as replaced by Art. 85 ν. 4782/2021;
  the contract can set another period (shorter is allowed for works ≤ €250,000 excl. VAT). Start = day after the
  completion certificate. Not checked with Legal Services. Stoa never states liability.
- A guarantee-return decision (W-DIAV-009) is treated as *evidence* that the period ended (INFERRED), not as a date.

## Platform
- **Sandbox is mocked** without `SANDBOX_KEY` (in-memory: restarting the server clears City requests; use
  demo reset). The live sandbox path is unchanged but was not exercised here.
- **Operator identity is self-declared** (name + role typed in the console) behind one shared `OPERATOR_KEY`.
  The audit trail records what was declared. Production needs municipal SSO and server-side roles.
- **No rate limiting** on public endpoints (report submission, tracker, «Διορθώθηκε;»). The tracker id is an
  unguessable random id for map reports, but `REQ-…` ids are sequential in the mock.
- `POST /api/reports/{id}/confirm` (citizen "is it fixed?") is public, as before; anyone with the id can reopen.
- SQLite single file; fine for a demo. Schema maps directly to PostgreSQL/PostGIS.
- The legacy citizen page (`citizen-legacy.html`) reads `/api/reports/{id}`, which now needs the operator key when
  one is set.
- Other modules (navigation, transit, environment, points, Ask Stoa) were not changed in this pass beyond keeping
  their tests green; parking, cleaning and events are listed as roadmap in `/api/layers`, not faked.
