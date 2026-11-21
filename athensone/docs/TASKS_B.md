# Tasks: Dev B (Evgenii) — Δεδομένα & backend

Board for the Dev B track of [SPEC.md](SPEC.md). Workflow and rules: [`../../CLAUDE.md`](../../CLAUDE.md).
Base branch: `dev-b`. Every task: branch `agent/B<n>-<name>` in `.worktrees/B<n>`, merged into `dev-b` on Evgenii's
word. Cards get a full test list (like [TASKS_A.md](TASKS_A.md)) before they start.

Dev B owns (SPEC «Ιδιοκτησία αρχείων»): `web/js/api.js`, `web/mock/*`, `web/js/ui/{report,points,stoa,workstab}.js`,
the backend (`app/`, `tests/`, `scripts/`, `data/`). Existing routes don't change (SPEC rule); new ones are added.
The real routes vs the SPEC's short names: [SPEC.md, Παράρτημα](SPEC.md#παράρτημα-spec--υπάρχον-backend).

| Task | Phase | What | State |
|---|---|---|---|
| B0 Contracts + first mocks | 0 | Lock the SPEC contracts against the Παράρτημα; `web/mock/*` (env, access, works with 10–15 real works, transit, health, points, stoa) realistic enough for the demo; offline boundary + main roads for A1 | **first: Dev A needs the mocks** |
| B1 `api.js` | 1 | Only door to the backend; live → `localStorage` cache → `mock/`; `source: live\|cache\|mock`; maps the real routes to SPEC shapes; offline report queue sent on `online` | card to write |
| B2 Works adapters | 2 | Διαύγεια + ΚΗΜΔΗΣ, join on ΑΔΑ/ΑΔΑΜ, curated geocoding; `/api/works/geojson` gains SPEC fields (`amount_paid_eur`, `guarantee_end`, `reports_count`, …) | card to write |
| B3 `/api/transit` | 2 | ΟΑΣΑ telematics (buses), GTFS/OSM metro + suburban lines and stations | card to write |
| B4 On-duty pharmacies/hospitals | 2 | New endpoint (path decision: `/api/health` is taken, see Q-1) | card to write |
| B5 Env grid | 2 | Open-Meteo forecast + air-quality on a grid over the Δήμος, `temp_c`, `aqi`, `pm25` per point | card to write |
| B6 Report flow «+» | 2 | `ui/report.js`; `/api/report` accepts `category`, `work_id`, optional photo; plate blur; public location rounded ~10 m; points per SPEC rules | card to write |
| B7 Points pill + panel | 2 | `ui/points.js`, pulse + «+N»; SPEC rewards; `/points/redeem` (Nice) | card to write |
| B8 Stoa citations + flyTo | 2 | `/api/stoa/ask` returns `citations[{label, lon, lat, kind}]`; `ui/stoa.js` | card to write |
| B9 Route cost per profile | 2 | wheelchair / stroller / cool from the same layers the map shows; `reasons[{text, layer, feature_id}]` | card to write |
| B10 Works tab (F8) | 3 | `ui/workstab.js`, crowdsourced progress | later |
