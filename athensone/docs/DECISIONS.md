# Decisions

`A-n` = decided by Evgenii. `Q-n` = open; agents don't build on an open question.

- **A-1** (Sat 21 Nov) The cards T1–T4 in TASKS.md are approved as drafted from the Build Plan, test lists included
  ("ok start building stuff").
- **A-2** Agent steps run in Antigravity: tests Gemini 4 Hydrogen, code Claude Opus 5.5 inside Antigravity, review
  Gemini 4 Argon. Claude CLI only as fallback (Claude Code account at ~89 % weekly usage).
- **A-3** Each task adds its new tests in its own file `tests/test_T<n>_<name>.py` and its code in a marked
  `# --- T<n> ---` block in shared files, so the four parallel branches merge mechanically.
- **A-4** T2 does not wire the "+5 for confirming the fix" grant, because the confirm endpoint comes from T1. T2
  exposes a `points.grant(...)` helper; the +5 hook is added after both T1 and T2 are merged (follow-up T6).
- **A-5** Points token: random, set as an HttpOnly cookie `ao_token` on first use; stored only in our SQLite; never
  sent to the sandbox, never logged.

## Open

- **A-18** (Sat 21 Nov, "do them") T5 approved: add `deface` 1.5.0 (MIT) with the OpenCV Haar fallback kept. Its deps pull opencv-python 5 (no CascadeClassifier) next to our headless 4.x pin: install must keep OpenCV 4; onnxruntime is not pulled (CenterFace then runs on cv2.dnn).

## Sat 21 Nov, after the T1–T4 code ("continue" = advisor's recommendations accepted)

- **A-6** T1 `reopen_rate` = reopened ÷ reports resolved in that district; `None` when none resolved.
- **A-7** T1 confirm is allowed on any existing report tonight (no 409). Leftover: restrict to resolved in the pilot.
- **A-8** T1 follow-up: show `reopen_rate` in the operator equity table.
- **A-9** T2 district target from env `DISTRICT_TARGET`, default 5000; lower it on stage so the bar moves.
- **A-10** T2 12-month window applies to the tier only; balance is all-time until redemption exists.
- **A-11** T2 cookie without `Secure` for the local HTTP demo; `Secure` before the pilot.
- **A-12** T3 `minutes` is `null` when not hot (no Valhalla call on cool page loads).
- **A-13** T3 banner styles stay inline in `citizen.html` tonight.
- **A-14** T4 `sources` = `[{ada}]`, Diavgeia link only when `data_source != "SEED"`.
- **A-15** T4 Krikri settings move to `config.py` after the merge.
- **A-16** T4 keeps partial street matching ("Ερμού" matches "Οδός Ερμού (τμήμα)").
- **A-17** (advisor default, Evgenii may change) The +5 for confirming a fix goes only to the reporter's own token,
  once per report. Stops anyone farming +5 by confirming other people's reports.
- **A-19** ("ok continue") T5 CenterFace threshold 0.2 (deface CLI default): more recall on small or turned faces.
- **A-20** ("ok continue") `deface` is installed by a separate README line, `pip install --no-deps deface==1.5.0`,
  so `requirements.txt` can never pull OpenCV 5.
- **A-21** (advisor default, Evgenii may change) Air stations with no coordinates in the City registry are placed at
  their neighbourhood's centre and flagged `"location": "neighbourhood_centre"` ("περίπου" on screen). Rejected:
  geocoding each address through Nominatim (outside service, rate limits, more to explain).

## Sat 21 Nov evening: full app ("all modules", "full re-architecture")

- **A-22** Stack changes (supersedes "no new framework" in CLAUDE.md): FastAPI split into routers; SQLAlchemy 2 +
  Alembic with `DATABASE_URL` (SQLite by default and in tests, PostgreSQL 16 + PostGIS in Docker Compose);
  React 18 + Vite + TypeScript + MapLibre GL frontend in `athensone/frontend/`; Docker Compose for the full stack.
- **A-23** Modules are self-contained so they can be built in parallel: backend `app/modules/<name>/`
  (`models.py`, `service.py`, `router.py`), discovered automatically (no shared registry file to edit); frontend
  `frontend/src/modules/<name>/` (routes discovered with `import.meta.glob`).
- **A-24** Geometry in the database is stored as plain lat/lng columns (works on SQLite and Postgres);
  PostGIS types only where a module needs spatial indexing, behind the same service functions.
- **A-25** The old `web/*.html` pages stay served until the React app reaches parity (T12), then redirect to it.
- **A-26** ("the main feature is the Google Maps alternative for Athens; all features are around it") AthensOne is a
  map app: the map is the home screen, and every module is a layer, a search result, a place panel or a route on it.
  Modules plug into the map through layer/panel extension points (A-23).
- **A-27** (advisor default) Basemap: MapLibre vector tiles, OpenFreeMap style by default (free, no key, OSM data);
  production points `MAP_STYLE_URL` at a self-hosted Protomaps PMTiles extract of Attica. Greek labels first.
  Rejected: `tile.openstreetmap.org` raster tiles (its usage policy forbids app traffic), Google/Mapbox (keys, cost,
  data leaves the EU).
- **A-28** (advisor default) Search: our own index of OSM names, addresses and POIs for Athens (Greek, Greeklish,
  English, accent-insensitive) in the DB, plus our own layers (cool places, works, services). Rejected for now:
  public Nominatim/Photon as the main search (rate limits, every query leaves our servers); Photon self-hosted is the
  scale-up path.
- **A-29** (advisor default, T11 questions) `test_routes_unchanged` checks the live routes through `/openapi.json`
  plus direct requests for routes outside the schema (FastAPI 0.165 wraps included routers in `app.routes`); the
  test writer changes it. `psycopg[binary]` (LGPL-3.0, library use) is added with T13, not T11.
- **A-30** (Sat 21 Nov, night) `docs/SPEC.md` («Προδιαγραφές Citizen Map», from `SPEC.pdf`) is the project's canon;
  it wins over everything else. Two tracks: Dev A (Αναστάσης, map & HUD, branch `dev-a`, board `TASKS_A.md`) and
  Dev B (Evgenii, data & backend, branch `dev-b`, board `TASKS_B.md`), each with its own agent loop (`CLAUDE.md`,
  `agents/`). The frontend is plain ES modules + CDN with no build step (SPEC), which replaces the React/Vite plan
  of A-22–A-25 and A-23's module discovery; T11–T23 cards are dropped. `PROPOSAL.pdf`, `BUILD_PLAN.pdf`, `PLAN.md`,
  `TASKS.md`, `STOA_MERGE.md` and `DEMO_SCRIPT.md` were removed as superseded; code comments that cite them still
  resolve in git history (`git show 18e6f2f:athensone/docs/TASKS.md`).
- **Q-1** (closed by A-33) Path for the SPEC's new `GET /health` (on-duty pharmacies/hospitals): `/api/health`
  is already the server-status route used by tests. Proposal: `GET /api/onduty?date=`.
- **A-31** (Sat 21 Nov, night) Track B may use Claude (Claude Code CLI, Opus) for the **code** step of some tasks:
  `CLAUDE_STEPS=code agents/drive.sh B<n>`. Tests and review stay on Gemini in Antigravity. Default picks: B1 `api.js`,
  B6 report flow (privacy), B8 Stoa citations, B9 route cost per profile; the rest run fully in Antigravity.
- **A-32** (Sat 21 Nov, night) New track-B endpoints live in their own module `app/routers/<name>.py` with
  `router = APIRouter()`; `app/main.py` includes every module there automatically (block `# --- B: routers`).
  Tasks never edit `main.py` for a new endpoint, so B2–B5 can run in parallel. Shared helpers they need go in
  their own `app/<name>.py`, not in `main.py`.
- **A-33** (advisor default, closes Q-1) Endpoints with the SPEC's shapes live under `/api/map/`: `/api/map/works`,
  `/api/map/transit`, `/api/map/health` (on-duty pharmacies/hospitals), `/api/map/env`. `/api/health` stays the
  server status. Existing routes keep their shapes; `api.js` (B1) picks the `/api/map/` route where one exists.
- **A-34** (advisor default) The SPEC's `user_id` is the existing points token: a random pseudonym in the `ao_token`
  cookie (T2), never in a URL, never sent to the sandbox, never logged. `/api/map/points*` read it from the cookie;
  `api.js` sends `credentials: "same-origin"` and ignores `user_id`.
- **A-35** (proposal, needs Αναστάσης) Dev B's UI modules (`ui/report.js`, `ui/points.js`, `ui/stoa.js`,
  `ui/workstab.js`) each export `mount(ctx)` with `ctx = {map, api, root, bus}`: the MapLibre map, the `api.js`
  module, the HUD container element for that module (from `main.js`), and an `EventTarget` shared by all modules.
  Events on `bus`: `points:earned` `{delta, reason}`, `report:open` `{work_id?, lngLat?}`, `map:flyto`
  `{lon, lat, label}`, `route:request` `{to:[lon,lat]}`. `main.js` (Dev A) creates `bus` and calls `mount()`.
- **A-36** (advisor default) SPEC points rules apply to the new map flow as new actions next to the T2 ones:
  `map_report` 5, `confirm_other` 2, `work_progress_photo` 15, `city_confirmed` +20; cap 10 map reports/day; no
  points for a report within 50 m and 30 min of another of the same category. The T2 actions (operator approve 10,
  dossier 30, fix confirmed 5) stay for the existing routes, so their tests keep passing.
- **A-37** (Evgenii, Sat 21 Nov) Every env point carries `aqi_scale`: `eaqi` (Open-Meteo European AQI 0–100+) or
  `city_1_6` (AthensGov station class 1–6). The scales are not converted; the heatmap (Dev A) and the cool route (B9)
  weigh air by `pm25` (µg/m³ on both sources). Report `category` ids and Stoa citation `kind`s are the B6/B8 ones,
  in the mocks too.
