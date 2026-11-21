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
