# Security & privacy notes

**Done**
- Photos: size cap (15 MB), MIME/format/dimension validation, faces + plates blurred and EXIF stripped before
  anything is written; the original is never stored; fail-closed (503) if blurring fails (`app/privacy.py`).
- Public location rounded to ~10 m (map reports) and ~100 m on the citizen tracker; reporter is a random cookie
  pseudonym, never returned or sent to the sandbox.
- Operator endpoints (`/api/cases/*`, `/api/reports*` reads, CSV export, reset, demo seed, Stoa review log) require
  `X-Operator-Key` when `OPERATOR_KEY` is set; constant-time comparison. Demo seeding only with `DEMO_MODE=1` and
  the mock sandbox.
- Public tracker returns stage, coarse location, support count and the city's public message only: no notes,
  names, contractor or guarantee details.
- Backend validates categories, subtypes, coordinates (finite, Athens bounds on the legacy path), note length,
  workflow transitions, roles, actor and reasons; the frontend is not trusted.
- SQL uses parameters everywhere; dossier HTML is escaped; operator UI builds DOM nodes (no `innerHTML` with data).
- No CORS middleware: the API is same-origin only. No secrets in the repo; `.env` is git-ignored (`.env.example`).

**Not done (see KNOWN_LIMITATIONS.md)**: real user accounts/SSO and server-side roles, rate limiting, CSRF tokens
(mitigated today by no cookies on operator auth: the key travels in a header), retention policy for photos/reports
(suggested: delete photos 12 months after resolution), dependency vulnerability scan (run `pip-audit` before deploy).

**Deployment checklist:** set `OPERATOR_KEY` (long random), `DEMO_MODE=0`, a real `SANDBOX_KEY`, run behind HTTPS,
back up `ATHENSONE_DB` and the photo folder daily.
