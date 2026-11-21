# Tasks: Dev B (Evgenii) — Δεδομένα & backend

Board for the Dev B track of [SPEC.md](SPEC.md). Workflow and rules: [`../../CLAUDE.md`](../../CLAUDE.md).
Base branch: `dev-b`. Every task: branch `agent/B<n>-<name>` in `.worktrees/B<n>`, merged into `dev-b` on Evgenii's
word. Code step on Claude (A-31): B1, B6, B8, B9 (`CLAUDE_STEPS=code agents/drive.sh B<n>`); the rest
fully in Antigravity. Cards get a full test list (like [TASKS_A.md](TASKS_A.md)) before they start.

Dev B owns (SPEC «Ιδιοκτησία αρχείων»): `web/js/api.js`, `web/mock/*`, `web/js/ui/{report,points,stoa,workstab}.js`,
the backend (`app/`, `tests/`, `scripts/`, `data/`). Existing routes don't change (SPEC rule); new ones are added.
The real routes vs the SPEC's short names: [SPEC.md, Παράρτημα](SPEC.md#παράρτημα-spec--υπάρχον-backend).

| Task | Phase | What | State |
|---|---|---|---|
| B0 Contracts + first mocks | 0 | Lock the SPEC contracts against the Παράρτημα; `web/mock/*` (env, access, works with 10–15 real works, transit, health, points, stoa) realistic enough for the demo; offline boundary + main roads for A1 | **running** (approved by Evgenii, Sat 21 Nov) |
| B1 `api.js` | 1 | Only door to the backend; live → `localStorage` cache → `mock/`; `source: live\|cache\|mock`; maps the real routes to SPEC shapes; offline report queue sent on `online` | card to write |
| B2 Works adapters | 2 | Διαύγεια + ΚΗΜΔΗΣ, join on ΑΔΑ/ΑΔΑΜ, curated geocoding; `/api/map/works` with every SPEC field | **running** |
| B3 `/api/map/transit` | 2 | ΟΑΣΑ telematics (buses), GTFS/OSM metro + suburban lines and stations | **running** |
| B4 On-duty pharmacies/hospitals | 2 | `/api/map/health` (A-33) | **running** |
| B5 Env grid | 2 | Open-Meteo forecast + air-quality on a grid over the Δήμος, `temp_c`, `aqi`, `pm25` per point | **running** |
| B6 Report flow «+» | 2 | `ui/report.js`; `/api/report` accepts `category`, `work_id`, optional photo; plate blur; public location rounded ~10 m; points per SPEC rules | card to write |
| B7 Points pill + panel | 2 | `ui/points.js`, pulse + «+N»; SPEC rewards; `/points/redeem` (Nice) | card to write |
| B8 Stoa citations + flyTo | 2 | `/api/stoa/ask` returns `citations[{label, lon, lat, kind}]`; `ui/stoa.js` | card to write |
| B9 Route cost per profile | 2 | wheelchair / stroller / cool from the same layers the map shows; `reasons[{text, layer, feature_id}]` | card to write |
| B10 Works tab (F8) | 3 | `ui/workstab.js`, crowdsourced progress | later |

### B0: Contracts + first mocks (phase 0)
SPEC «Backend contracts», «Εξωτερικές πηγές» (Fallback column), «Offline fallback», «Demo script». Every file in
`web/mock/` has **exactly the SPEC response shape** of its endpoint, so `api.js` (B1) can return it as is, and is
realistic enough that the demo runs on it with the Wi-Fi off. Dev A builds against these files from now on.
**Files:** `web/mock/{env.json, access.geojson, works.geojson, transit.geojson, health.geojson, reports.geojson,
points.json, stoa.json, base.geojson, README.md}`, `scripts/build_mocks.py` (one-off builder; may read `data/` and download once
from OSM/Overpass or Διαύγεια, never at test time), `THIRD_PARTY.md` (data sources), `tests/test_B0_mocks.py`.
- Every file carries top-level `snapshot` (date) and `note` (where the data comes from, what is real, what is
  invented). GeoJSON is a `FeatureCollection` in WGS84 inside the Δήμος Αθηναίων bbox (lon 23.68–23.80,
  lat 37.95–38.03).
- `env.json`: GeoJSON points on a grid over the Δήμος (≥ 20), `temp_c`, `aqi`, `pm25`, `updated_at`; a visibly
  hotter/worse zone so the Δροσερότερη route has something to avoid.
- `access.geojson`: real OSM features (`kerb=lowered`, `wheelchair=*`, `ramp=yes`, `tactile_paving=yes`) around
  Σύνταγμα–Μοναστηράκι–Πλάκα; property `kind` ∈ {kerb_lowered, wheelchair, ramp, tactile_paving} plus the OSM id.
- `works.geojson`: 10–15 works, LineStrings on real streets, every contract field (`id, title, status, contractor,
  amount_contract_eur, amount_paid_eur, ada, adam, start_date, end_date, guarantee_end, reports_count`), `status` ∈
  {planned, in_progress, completed}. A work is real only if its ΑΔΑ was found on diavgeia.gov.gr (`source_url` set);
  otherwise `ada` starts with `SEED-` and `seed: true`. **Never** a made-up ΑΔΑ that looks real. At least one
  `in_progress` work lies on the Σύνταγμα → Μοναστηράκι walk (demo step 4).
- `transit.geojson`: `{lines, stations, buses}` (three FeatureCollections). Metro M1/M2/M3 + Προαστιακός lines
  in the centre with official colours (`color`, comment with source), stations with `name`, `lines[]`, `elevator`
  (bool or null if unknown), including Σύνταγμα and Μοναστηράκι; a few buses with `line`, `bearing`.
- `health.geojson`: points with `kind` ∈ {φαρμακείο, νοσοκομείο}, `name`, `address`, `phone`, `hours`,
  `specialties[]`, `on_duty` (bool); real hospitals of central Athens; pharmacies' on-duty flags marked invented in
  `note`. At least one on-duty pharmacy within 500 m of Σύνταγμα (demo step 5).
- `reports.geojson`: points with `category` (συμφόρηση / συμβάν / εμπόδιο / ζημιά / πρόοδος έργου), `created_at`,
  `confirmations`; coordinates rounded to 4 decimals (~10 m, SPEC «Privacy»); no ids of people, no photos.
- `points.json`: `{balance, district:{name, progress_pct, goal}, history:[{ts, delta, reason}], rewards:[{id, title,
  cost}]}`, deltas from SPEC «Κανόνες πόντων»; no `user_id`.
- `stoa.json`: `[{question, answer_md, citations:[{label, lon, lat, kind}]}]`, including the demo question «Ποιο
  φαρμακείο εφημερεύει κοντά μου;»; every citation `label` appears in `answer_md`.
- `base.geojson`: Δήμος boundary polygon (from the CKAN districts in `data/ckan/`) + a handful of main roads as
  LineStrings, for A1's offline style.

| Test | Given | Expected |
|---|---|---|
| `test_all_mock_files_exist_and_parse` | `web/mock/` | the 9 files exist and parse as JSON |
| `test_every_mock_has_snapshot_and_note` | each file (top level; for `stoa.json` a wrapper object is not allowed, so it lives in `web/mock/README.md`) | `snapshot` is an ISO date, `note` non-empty |
| `test_geojson_is_wgs84_in_athens` | every Feature in every GeoJSON file (incl. `transit` sub-collections) | all coordinates inside lon 23.68–23.80, lat 37.95–38.03 |
| `test_env_points_have_contract_fields` | `env.json` | ≥ 20 Points, each with numeric `temp_c`, `aqi`, `pm25` and ISO `updated_at` |
| `test_env_has_hot_zone` | `env.json` | max `temp_c` − min `temp_c` ≥ 2 |
| `test_access_kinds_present` | `access.geojson` | each of the 4 kinds appears at least once; every feature has an OSM id |
| `test_works_count_and_fields` | `works.geojson` | 10–15 features, all 12 contract fields present, `status` in the allowed set |
| `test_works_money_and_dates_consistent` | each work | `amount_paid_eur` ≤ `amount_contract_eur` when both known; `guarantee_end` ≥ `end_date` when both known |
| `test_works_ada_real_or_seed` | each work | either `source_url` starts with `https://diavgeia.gov.gr/` or (`ada` starts with `SEED-` and `seed` is true) |
| `test_works_on_demo_route` | Σύνταγμα [23.7348, 37.9755] → Μοναστηράκι [23.7257, 37.9761] | ≥ 1 `in_progress` LineString within 150 m of that segment |
| `test_transit_has_three_collections` | `transit.geojson` | keys `lines`, `stations`, `buses`, each a FeatureCollection, each non-empty |
| `test_transit_lines_have_colours` | metro/suburban lines | every line has `name` and a `#rrggbb` `color` |
| `test_transit_demo_stations` | stations | Σύνταγμα and Μοναστηράκι present; `elevator` is bool or null |
| `test_health_fields_and_kinds` | `health.geojson` | both kinds present; `name, address, phone, hours, specialties, on_duty` on every feature |
| `test_health_on_duty_near_syntagma` | pharmacies with `on_duty` true | ≥ 1 within 500 m of Σύνταγμα |
| `test_reports_rounded_and_anonymous` | `reports.geojson` | coordinates have ≤ 4 decimals; no property named like `user`, `token`, `email`, `photo` |
| `test_points_contract_and_sum` | `points.json` | contract keys; `0 ≤ progress_pct ≤ 100`; `balance` = sum of `history[].delta`; no `user_id` |
| `test_stoa_citations_in_answer` | `stoa.json` | every citation `label` occurs in its `answer_md`; every citation has numeric `lon`, `lat` |
| `test_stoa_pharmacy_demo_question` | the «Ποιο φαρμακείο εφημερεύει κοντά μου;» entry | its first citation is within 20 m of an on-duty pharmacy in `health.geojson` |
| `test_base_has_boundary_and_roads` | `base.geojson` | ≥ 1 (Multi)Polygon and ≥ 3 LineStrings |

### Common to B2–B5 (adapters)
- Each new endpoint is a module `app/routers/<name>.py` (A-32) under the prefix **`/api/map/`** (A-33) and returns
  the SPEC «Backend contracts» shape exactly, plus a top-level `source` (`live` | `cache` | `snapshot`) and
  `updated_at`. Existing routes don't change.
- The external call lives in its own adapter `app/<name>_src.py`: one function per upstream call, `httpx` with a
  10 s timeout, in-memory TTL cache, and the last good answer written to `data/<name>/last.json`. Upstream down →
  serve `last.json` with `source: "snapshot"`; nothing at all → an empty FeatureCollection with
  `source: "unavailable"`, HTTP 200, never a guess. `api.js` (B1) then falls back to `web/mock/`.
- The URLs in SPEC «Εξωτερικές πηγές» were written without an online check. The **implementer verifies them online
  first** and records in the code report what each returned; real responses are saved as test fixtures in
  `tests/fixtures/B<n>/`. Tests are fully offline: they patch the adapter's HTTP function to return the fixtures.
- Config (URLs, TTLs, line lists) goes in `app/config.py` inside a `# --- B<n> ---` block, from env vars with
  defaults. Data sources and licences go in `THIRD_PARTY.md`.

### B2: Works from Διαύγεια + ΚΗΜΔΗΣ (phase 2)
SPEC F4, «Εξωτερικές πηγές» Έργα, contract `GET /works`.
**Files:** `app/works_src.py`, `app/routers/works_map.py`, `scripts/fetch_works.py`, `data/stoa/works.json`
(output), `app/config.py` (B2 block), `THIRD_PARTY.md`, `tests/fixtures/B2/*`, `tests/test_B2_works.py`.
- `fetch_works.py` (run by hand, online): Διαύγεια OpenData search for Δήμος Αθηναίων decisions about public works
  (αναθέσεις, πληρωμές), ΚΗΜΔΗΣ OpenData for the matching contracts (ανάδοχος, ποσά, ΑΔΑΜ), join on ΑΔΑ/ΑΔΑΜ,
  street geocoded from the decision text by a curated street → LineString table (Nominatim only as a hint, by
  hand). Output in the `data/works_seed.json` schema (every field `{value, label: CITED|UNKNOWN, source:{ada}}`)
  to `data/stoa/works.json`, which `works.py` already prefers. 10–15 works in the centre.
- `GET /api/map/works?bbox=&status=` → SPEC fields from `works.all_cards()`; `status` derived from dates
  (`planned` before start, `in_progress`, `completed` after end); `guarantee_end` from `works.clock()`;
  `reports_count` = open reports within 30 m of the line. Unknown fields are `null`, never 0.

| Test | Given | Expected |
|---|---|---|
| `test_map_works_contract_fields` | SEED dataset | FeatureCollection; every feature has the 12 SPEC fields |
| `test_map_works_bbox_filter` | bbox around one work only | exactly that work |
| `test_map_works_status_filter` | `status=in_progress` | only in-progress works |
| `test_status_from_dates` | `STOA_TODAY` before start / between / after end | planned / in_progress / completed |
| `test_unknown_amount_is_null` | a work whose `amount_paid_eur` is UNKNOWN | `amount_paid_eur` is `null` |
| `test_reports_count_near_line` | 2 open reports within 30 m of a work, 1 at 100 m | `reports_count` 2 |
| `test_diavgeia_parser_fixture` | saved Διαύγεια search response | parsed decisions with ΑΔΑ, subject, date, amount |
| `test_khmdhs_join_on_ada` | saved ΚΗΜΔΗΣ fixture + Διαύγεια fixture | contractor and contract amount joined to the right ΑΔΑ |
| `test_existing_works_routes_unchanged` | `/api/works/geojson`, `/api/works/radar` | same keys as before B2 |

### B3: `/api/map/transit` — metro, suburban, OASA buses (phase 2)
SPEC F2 Τηλεματική + Μετρό/Προαστιακός, contract `GET /transit`.
**Files:** `app/transit_src.py`, `app/routers/transit.py`, `scripts/fetch_transit.py`, `data/transit/static.json`
(output), `app/config.py` (B3 block), `THIRD_PARTY.md`, `tests/fixtures/B3/*`, `tests/test_B3_transit.py`.
- Static lines + stations: OASA/STASY GTFS if reachable, else OSM `route=subway|train|light_rail` via Overpass;
  built once by `fetch_transit.py` into `data/transit/static.json`. Lines carry `name`, `ref`, official `color`
  (source in a comment); stations `name`, `lines[]`, `elevator` (OSM `elevator`/`wheelchair`, else `null`).
- Buses: OASA telematics (`getBusLocation` per route code, `getStopArrivals` for waits) for the route codes in
  `config.TRANSIT_ROUTES` that cross the bbox; cached 20 s (SPEC polling); `line`, `route_code`, `bearing`,
  `updated_at` per bus.

| Test | Given | Expected |
|---|---|---|
| `test_transit_contract` | static file + bus fixture | `{lines, stations, buses}` each a FeatureCollection, plus `source` |
| `test_transit_bbox_filters_stations_and_buses` | bbox around Σύνταγμα | Σύνταγμα in, Πειραιάς out; buses outside bbox dropped |
| `test_line_colours_hex` | static lines | every line has a `#rrggbb` `color` |
| `test_bus_location_parser_fixture` | saved `getBusLocation` response | buses with lon/lat floats, line, bearing |
| `test_bus_cache_20s` | two calls 5 s apart, patched clock | upstream called once |
| `test_oasa_down_serves_snapshot` | upstream raises | last good buses, `source: "snapshot"` |
| `test_nothing_available_empty_200` | upstream raises, no snapshot | 200, empty `buses`, `source: "unavailable"` |

### B4: `/api/map/health` — on-duty pharmacies and hospitals (phase 2)
SPEC F2 Εφημερεύοντα, contract `GET /health` (served as `/api/map/health`, A-33; `/api/health` stays the server
status). **Files:** `app/onduty_src.py`, `app/routers/onduty.py`, `data/onduty/hospitals.json` (curated: real
central-Athens hospitals, address, phone, coordinates, source per row), `app/config.py` (B4 block),
`THIRD_PARTY.md`, `tests/fixtures/B4/*`, `tests/test_B4_onduty.py`.
- Pharmacies: the Φαρμακευτικός Σύλλογος Αττικής on-duty list for `date` (scraper, once a day, cached to
  `data/onduty/pharmacies-<date>.json`), addresses geocoded once and cached. Hospitals: the curated file + the
  Υπουργείο Υγείας daily εφημερίες announcement → `on_duty` and `specialties` per hospital.
- A source that can't be fetched or parsed gives `on_duty: null` (unknown) for its rows, never a guess; the
  response says which source failed.

| Test | Given | Expected |
|---|---|---|
| `test_onduty_contract` | fixtures | GeoJSON points with `kind, name, address, phone, hours, specialties, on_duty` |
| `test_api_health_unchanged` | `GET /api/health` | still the server-status object (`ok`, `mock`, …) |
| `test_pharmacy_parser_fixture` | saved on-duty page | pharmacies with name, address, hours |
| `test_hospital_announcement_parser_fixture` | saved announcement | the right hospitals `on_duty` true with specialties |
| `test_geocode_cached` | same address twice | geocoder called once |
| `test_source_down_on_duty_null` | pharmacy source raises | pharmacies (from last cache) with `on_duty: null`, failed source named |
| `test_date_param` | `?date=2026-11-22` | the adapter asked for that date |

### B5: `/api/map/env` — temperature / AQI grid (phase 2)
SPEC F2 Θερμοκρασία/AQI, «Εξωτερικές πηγές», contract `GET /env`.
**Files:** `app/envgrid_src.py`, `app/routers/envgrid.py`, `app/config.py` (B5 block), `THIRD_PARTY.md`,
`tests/fixtures/B5/*`, `tests/test_B5_envgrid.py`.
- A fixed grid over the Δήμος (step `config.ENV_GRID_M`, default 600 m), one Open-Meteo forecast call and one
  air-quality call for all grid points (multi-coordinate request), cached 15 min. Per point `temp_c`, `aqi`
  (European AQI), `pm25`, `updated_at`. Where a City CKAN station (`ckan.nearest_air`) is within 300 m, its values
  win and the point says `station`.
- `?bbox=minLon,minLat,maxLon,maxLat` keeps only points inside.

| Test | Given | Expected |
|---|---|---|
| `test_env_contract` | fixtures | GeoJSON points with `temp_c, aqi, pm25, updated_at`, plus `source` |
| `test_grid_covers_dimos` | default config | ≥ 20 points, all inside the Δήμος bbox |
| `test_bbox_param_spec_format` | `bbox=23.72,37.97,23.74,37.98` | only points inside |
| `test_single_upstream_call_per_kind` | full grid | one forecast call, one air-quality call |
| `test_cache_15min` | two calls 10 min apart | upstream called once per kind |
| `test_station_overrides_model` | CKAN station 100 m from a grid point | that point uses the station's values, `station` set |
| `test_open_meteo_down_snapshot` | upstream raises after one good call | last good grid, `source: "snapshot"` |
