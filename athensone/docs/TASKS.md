# Tasks

Board and cards. The main checkout's copy is current. Workflow and rules: `../../CLAUDE.md`.

| Task | Owner | State |
|---|---|---|
| T1 "Is it fixed?" loop | A | approved, on integrate |
| T2 Points wallet, earn side | B | approved, on integrate |
| T3 Heat alert banner | C | approved, on integrate |
| T4 Ask Stoa, cited answers | D | approved, on integrate |
| T5 Better face blur | B | approved with leftovers, on main |

Baseline before T1–T4: `8 passed` (Python 3.14, offline test command).

### T1: "Is it fixed?" loop (owner A)
Idea from FixMyStreet's questionnaire (AGPL: state design only, no code). The sandbox only knows
submitted / received / in_progress / resolved / rejected, so the confirmation lives in our SQLite.
**Files:** `app/store.py`, `app/main.py`, `web/citizen.html`, `docs/DEMO_SCRIPT.md`, `tests/test_T1_fixed.py`.
- `store.py`: table `confirmations(request_id, asked_at, answered_at, fixed INTEGER, photo TEXT)`.
- `POST /api/reports/{id}/resolve` inserts a row with `asked_at`; the citizen's status card shows "Is it fixed? Yes / No, photo".
- New `POST /api/reports/{id}/confirm` with `fixed` (bool) and optional photo, which goes through `privacy.py` first.
- `fixed=false` → `sb.update_request(id, status="in_progress", note="Ο πολίτης αναφέρει ότι δεν διορθώθηκε")`; the hazard comes back into routing.
- `/api/equity` adds `reopen_rate` per district.

| Test | Given | Expected |
|---|---|---|
| `test_resolve_asks_confirmation` | a report, resolved | a confirmation row with `asked_at`, `answered_at` null |
| `test_confirm_false_reopens_report` | resolved report, confirm `fixed=false` | status `in_progress`, note as above |
| `test_confirm_false_hazard_back` | same | the report is in `/api/hazards` again |
| `test_reopen_rate_in_equity` | one report in a district, reopened | that district's `reopen_rate` is 1.0 (100 %) |
| `test_confirm_true_keeps_resolved` | resolved, confirm `fixed=true` | status stays `resolved`, hazard stays gone |
| `test_confirm_photo_blurred_no_exif` | confirm with a JPEG carrying EXIF GPS | stored photo has no EXIF |
| `test_confirm_unknown_report_404` | unknown id | 404 |

### T2: Points wallet, earn side (owner B)
Append-only ledger we write ourselves (loyalty-ledger has no licence: idea only).
**Files:** `app/store.py`, `app/main.py`, new `app/points.py`, `web/citizen.html`, `tests/test_T2_points.py`.
- Table `points_ledger(id, account, district, action, ref_id, points, verified_by, created_at, UNIQUE(account, action, ref_id))`.
- No login: random pseudonymous token in a cookie on first use. Report creation stores the token next to the report, only in our DB.
- Grants inside existing actions: operator approve **+10**, engineer opens the Stoa dossier **+30**, citizen confirms the fix **+5** (after T1). Daily cap: 3 approved reports per account.
- `GET /api/points/me` → balance (`SUM(points)`), tier (Γείτονας 0+, Φίλος της Γειτονιάς 500/12 months, Πρέσβης 2,000), last 10 entries. `GET /api/points/districts` → total per district vs the shared target.
- Citizen page: balance chip in the header, district progress bar. Rankings only by district, never by person.

| Test | Given | Expected |
|---|---|---|
| `test_approve_twice_pays_once` | approve the same report twice | one +10 row |
| `test_balance_is_ledger_sum` | several grants | balance = sum of rows |
| `test_daily_cap_three_reports` | 4 approved reports, one account, one day | 30 points, not 40 |
| `test_dossier_bonus_30` | dossier opened for a report | +30 to the reporter |
| `test_token_never_sent_to_sandbox` | create a report with a cookie token | the sandbox mock never receives the token |
| `test_points_me_without_cookie` | no cookie | a new token is set, balance 0, tier Γείτονας |
| `test_districts_totals` | grants in two districts | per-district totals, no account ids |

### T3: Heat alert banner (owner C)
Everything exists: Open-Meteo, `ckan.nearest_air()`, cool places, `/api/navigate`.
**Files:** `app/main.py`, `app/config.py`, `web/citizen.html`, `tests/test_T3_heat.py`.
- `GET /api/heat?lat&lng` → `hot`, `temp_c`, the temperature source, nearest cool place, shaded minutes to it. Threshold `config.HEAT_C` (33 °C).
- Citizen page calls it on load; if hot, top banner "35°C now. Λέσχη Φιλίας, 6′ με σκιά" + "Take me there" → Navigate in heat mode.
- `HEAT_FORCE=1` for a winter demo; the banner then says "δοκιμαστικό".

| Test | Given | Expected |
|---|---|---|
| `test_heat_hot_from_station` | fake station 34.5 °C | `hot` true, source is the station |
| `test_heat_cool_place_matches` | same | cool place = first `/api/cool-places` item |
| `test_heat_not_hot` | fake 25 °C | `hot` false |
| `test_heat_force_labelled` | `HEAT_FORCE=1`, 18 °C | `hot` true, `forced` true |
| `test_heat_no_data` | weather off, no station | `hot` false, `temp_c` null, source UNKNOWN; no error |

### T4: Ask Stoa, cited answers (owner D)
Our own retrieve-then-verify rule (citation-rag is proprietary).
**Files:** `app/works.py` or new `app/stoa_ask.py`, `app/main.py`, `web/operator.html`, `tests/test_T4_stoa_ask.py`.
- `POST /api/stoa/ask` with `q`. Retrieve: accent-insensitive match on street names and works types in `works.all_cards()`, up to 3 cards.
- Answer by template from card fields (contractor, euros, completion, guarantee clock with its formula). Every sentence ends with `[ΑΔΑ …]`.
- Optional model rephrase (Krikri); afterwards check that every ΑΔΑ and number in the output exists in the cards, else return the template.
- No card → "Δεν βρήκα τεκμηριωμένα στοιχεία για αυτό." Refuses rather than guesses.
- Operator page: question box above the Stoa radar.

| Test | Given | Expected |
|---|---|---|
| `test_ask_sample_street_cites_ada` | "Δείγμα Οδός Α" | answer contains `SEED-ΑΔΑ-003` and `15/12/2026` |
| `test_ask_accent_insensitive` | same street without accents / upper case | same cards |
| `test_ask_unknown_street_refuses` | a street with no records | the refusal text, no ΑΔΑ |
| `test_every_sentence_cited` | any matched answer | every sentence ends with `[ΑΔΑ …]` |
| `test_rephrase_with_bad_number_falls_back` | fake rephraser adds a number not in the cards | template answer returned |
| `test_max_three_cards` | a works type matching many cards | ≤ 3 cards |

### T5: Better face blur (owner B, if time)
**Files:** `app/privacy.py`, `requirements.txt`, `THIRD_PARTY.md`, `tests/test_T5_blur.py`. Needs approval: new dependency `deface` (MIT).
- Try CenterFace through deface first, fall back to the current OpenCV Haar cascade.
- Order stays: blur → strip metadata → store → AI. The original is never written to disk. Plates: "next step" in the pitch.

| Test | Given | Expected |
|---|---|---|
| existing photo tests | | still pass |
| `test_face_image_faces_ge_1` | a test image with a face | `faces ≥ 1` |
| `test_deface_missing_falls_back` | deface import fails | Haar path used, no error |
| `test_original_never_on_disk` | a report with a photo | no un-blurred file in `data/photos/` |


## Fix round (after review of T1–T4; branches start from `integrate/T1-T4`, 33 tests passing)

| Task | Owner | State |
|---|---|---|
| T6 T1 leftovers + "+5 for confirming the fix" (A-4) | A | approved, on integrate |
| T7 T2 leftovers | B | approved, on integrate |
| T8 T3 leftovers | C | approved, on integrate |
| T9 T4 leftovers | D | approved with leftovers, on integrate |

### T6: Fix confirmation points and reopen history (owner A)
From A-4, A-8 and the T1 review. **Files:** `app/main.py`, `web/operator.html`, `tests/test_T6_fix_t1.py`.
- After a confirm, grant **+5** (`action="fix_confirmed"`, `ref_id`=request id, `verified_by="system"`) through `points.grant`/the T2 helper, **only to the reporter's own token** (the caller's `ao_token` equals the account stored for that report) (A-17). Once per report (ledger UNIQUE).
- Re-resolving a report that was once reopened must not erase it from `reopen_rate` (keep the reopen in history; don't overwrite it).
- Operator equity table shows a `reopen_rate` column (percent, "—" when null). No test for the HTML; keep it accessible.

| Test | Given | Expected |
|---|---|---|
| `test_confirm_true_by_reporter_pays_5` | report made with cookie X, resolved, X confirms `fixed=true` | X gets one +5 `fix_confirmed` row |
| `test_confirm_twice_pays_once` | same, confirm again | still one +5 row |
| `test_confirm_by_other_token_pays_nothing` | cookie Y confirms X's report | no row for Y or X |
| `test_confirm_false_pays_nothing` | X confirms `fixed=false` | no `fix_confirmed` row |
| `test_reopen_survives_re_resolve` | resolve → confirm false → resolve again | that district's `reopen_rate` is still 1.0 |

### T7: Points fixes (owner B)
From A-9 and the T2 review. **Files:** `app/points.py`, `app/main.py`, `tests/test_T7_fix_t2.py`. Read `DISTRICT_TARGET` with `os.getenv` in `points.py` (not `config.py`, so T8 doesn't conflict).
- `DISTRICT_TARGET` from the environment, default 5000.
- No +30 dossier bonus when the report is `rejected`.
- `is_valid_token()` accepts only the format the server mints (exactly what `points` generates); anything else gets a fresh token.

| Test | Given | Expected |
|---|---|---|
| `test_district_target_from_env` | `DISTRICT_TARGET=100` | `/api/points/districts` target is 100 |
| `test_district_target_default_5000` | unset | target 5000 |
| `test_dossier_on_rejected_report_pays_nothing` | a rejected report with a works record, dossier opened | no +30 row |
| `test_malformed_token_replaced` | cookie `ao_token=abc` | response sets a new valid token; no ledger row uses `abc` |

### T8: Heat fixes (owner C)
From A-12 and the T3 review. **Files:** `app/main.py`, `tests/test_T8_fix_t3.py`.
- `minutes` is `null` and no routing call is made when `hot` is false.
- Non-finite `lat`/`lng` (`inf`, `nan`) → 422/400, never 500.
- A station dict without `name` and without `station_id` doesn't crash (`source` falls back to "AthensGov σταθμός").

| Test | Given | Expected |
|---|---|---|
| `test_not_hot_no_minutes_no_route` | fake 25 °C, routing patched to fail if called | `minutes` null, routing not called |
| `test_hot_still_has_minutes` | fake 34.5 °C | `minutes` is a number |
| `test_inf_lat_is_client_error` | `lat=inf` | status 400 or 422 |
| `test_station_without_name_or_id` | fake station `{temp_c: 34.5}` only | 200, `hot` true, `source` starts with "AthensGov" |

### T9: Ask Stoa verify fixes (owner D)
From the T4 review. **Files:** `app/stoa_ask.py`, `tests/test_T9_fix_t4.py`.
- `verify()` compares dates as whole dates and amounts as whole numbers (not split pieces in one pool).
- `verify()` rejects a rephrase that drops "πιθανώς εντός" wording present in the template.
- Sentence split doesn't break on Greek abbreviations (`Α.Ε.`, `Ο.Ε.`, initials).
- A query with an unknown street name and a known works type refuses (doesn't answer on the type alone).

| Test | Given | Expected |
|---|---|---|
| `test_swapped_date_falls_back` | rephraser turns 15/12/2026 into 12/15/2026 | template returned |
| `test_changed_amount_falls_back` | rephraser changes an amount to another whose pieces are all in the cards | template returned |
| `test_dropped_guarantee_wording_falls_back` | rephraser removes "πιθανώς εντός" | template returned |
| `test_abbreviation_not_split` | contractor name with "Α.Ε." | every sentence still ends with `[ΑΔΑ …]` |
| `test_unknown_street_with_known_type_refuses` | "Οδός Ανύπαρκτη πεζοδρόμιο" | the refusal text |

## Real-data round

| Task | Owner | State |
|---|---|---|
| T10 City districts and air stations from CKAN | E | approved (advisor default A-21), running |

### T10: City districts and air stations from CKAN (owner E)
Checked live on Sat 21 Nov: all 5 datasets answer, and `env-all-stations` has fresh rows (AQI, temperature, PM) up to
today, but `air_latest()` returns 0 stations and `district_of()` returns None. Why: the station registry has no
coordinates (only address, `neighbourhood_id`, `municipal_district_id`); the districts dataset has only `id` and
`name`, no geometry. The geometry is in `neighbourhoods-athens` (datastore `0283af02-…`, 144 rows): `polygon_geo` as
**WKT** (`POLYGON ((lon lat, …))`), `position_lat`/`position_lon` (centre) and `municipal_district_id`. All values
come back as strings.
**Files:** `app/ckan.py`, `tests/test_T10_ckan_geo.py`, `tests/fixtures/ckan/` (new, small hand-made fixtures).
- `_geom()` also parses WKT `POINT`, `POLYGON`, `MULTIPOLYGON` strings.
- `district_of(lat, lng)`: neighbourhood polygon containing the point → its `municipal_district_id` → the district
  `name` from `municipal-districts-athens`. Keep the old path for a dataset that does ship geometry.
- Env stations without coordinates get their neighbourhood's `position_lat`/`position_lon` and
  `"location": "neighbourhood_centre"` (A-21), so screens can say "περίπου". Stations with real coordinates get
  `"location": "exact"`.
- Numbers that arrive as strings are converted (`_num`).
- Tests fake `ckan._call` / `_fetch_url` (monkeypatch) with fixtures; no network.

| Test | Given | Expected |
|---|---|---|
| `test_wkt_polygon_parsed` | `"POLYGON ((23.74 37.96, 23.75 37.96, 23.75 37.97, 23.74 37.96))"` | GeoJSON Polygon with those rings |
| `test_wkt_multipolygon_parsed` | a 2-part MULTIPOLYGON | GeoJSON MultiPolygon, 2 parts |
| `test_district_of_point_in_neighbourhood` | fixture neighbourhood (district 2) around Plateia Varnava 37.9667, 23.7437 | "2ο Δημοτικό Διαμέρισμα Αθήνας" |
| `test_district_of_point_outside` | a point outside every fixture polygon | None, no error |
| `test_station_placed_at_neighbourhood_centre` | registry row with no coordinates, neighbourhood with centre | station lat/lng = centre, `location` "neighbourhood_centre" |
| `test_air_latest_has_items` | fixtures: 2 stations, 4 measurement rows | 2 items, newest row per station, `temp_c` and `aqi` numbers |
| `test_nearest_air_varnava` | fixture station centre 0.5 km from Varnava | that station, `distance_km` ≈ 0.5 |
| `test_station_without_neighbourhood_skipped` | registry row whose neighbourhood is unknown | not in items, no error |

## Full app, wave 0 (foundation)

| Task | Owner | State |
|---|---|---|
| T11 Backend re-architecture | advisor/agents | approved (A-22..A-24), running |
| T12 React frontend | advisor/agents | approved (A-22, A-23, A-25), running |

### T11: Backend into routers + SQLAlchemy/Alembic
**Files:** `app/` (all), `alembic.ini`, `alembic/`, `requirements.txt`, `tests/test_T11_arch.py`. **No existing test may be
changed**; they import `app.main.app`, `app.store`, `app.points`, `app.ckan`, `app.works`, `app.privacy`, `app.config`
and must keep passing as they are.
- `app/main.py` keeps `app` (FastAPI) but only wires things: middleware, exception handlers, static mounts, routers.
- Endpoints move into `app/api/<area>.py` routers (meta, ask, places/navigate/heat, city, reports/confirm, works +
  stoa ask, points, interop: Open311/NGSI-LD/DCAT, admin). Same paths, methods, bodies and responses.
- `app/db.py`: SQLAlchemy 2.0 engine from `DATABASE_URL` (default `sqlite:///<DATA_DIR>/athensone.db`), declarative
  `Base`, `get_session()` dependency, `init_db()`. Postgres URLs (`postgresql+psycopg://…`) work without code changes.
- `app/store.py` and the points store keep their public functions and signatures, now on SQLAlchemy models
  (`app/models.py`: reports, confirmations, points_ledger, report_accounts).
- Alembic: `alembic/` with a baseline migration creating those tables; `init_db()` runs create_all for SQLite dev/tests.
- Module discovery (A-23): `app/modules/__init__.py` imports every subpackage of `app/modules/` that has a `router`
  and includes it under `/api/<name>`; models of every module register on `Base`. Ship one tiny example module
  `app/modules/_example/` that tests use (excluded from production by its leading underscore unless `ENABLE_EXAMPLE=1`).

| Test | Given | Expected |
|---|---|---|
| all existing tests | unchanged | pass |
| `test_routes_unchanged` | the app's routes | every path+method that existed on main still exists (list from main's `app.routes`, kept in the test) |
| `test_database_url_respected` | `DATABASE_URL=sqlite:///<tmp>/x.db` | tables are created in that file |
| `test_alembic_baseline_matches_models` | run `alembic upgrade head` on an empty SQLite file | the tables and columns equal the models' |
| `test_module_discovery` | `ENABLE_EXAMPLE=1` | `/api/_example/ping` answers 200 |
| `test_module_without_router_ignored` | a module package without `router` | app starts, no error |
| `test_openapi_has_tags` | `/openapi.json` | each router's tag is present |

### T12: React frontend
**Files:** `frontend/` (new), `app/main.py` only to mount `frontend/dist` at `/app/` when it exists (inside a
`# --- T12 ---` block), `tests/test_T12_frontend_mount.py`. Don't touch `web/` (A-25).
- Vite + React 18 + TypeScript (strict) + react-router + MapLibre GL (BSD-3) + `openapi-typescript` client generated
  from `/openapi.json` into `src/api/schema.ts` (script `npm run gen:api`, reads a saved `openapi.json` so it works
  offline). No CSS framework: CSS modules with the colour tokens from `web/app.css`.
- Pages with parity to today: Citizen (`/app/`: ask with sources, cool places, map, navigate with profiles and heat
  mode, report with photo, my report status timeline + "Is it fixed?", points chip + district bars, heat banner),
  Operator (`/app/operator`: reports list grouped, approve/reject/resolve, AI draft, Stoa card + radar + Ask Stoa,
  equity table with reopen rate), AI register (`/app/ai-register`).
- Module routes (A-23): `src/modules/<name>/index.tsx` exporting `{path, title, element, area: "citizen"|"operator"}`,
  picked up with `import.meta.glob`; navigation built from them.
- Greek UI text as today; WCAG 2.2 AA (labels, focus, contrast, keyboard).
- Tests: Vitest + Testing Library + `vitest-axe` on each page with a mocked API; `npm run build` succeeds.

| Test | Given | Expected |
|---|---|---|
| `frontend: citizen renders ask box` | mocked API | a labelled question field and the cool-places list |
| `frontend: ask shows sources` | `/api/ask` mock with 2 sources | 2 source links rendered |
| `frontend: heat banner when hot` | `/api/heat` hot, forced | banner with "δοκιμαστικό" |
| `frontend: operator approve calls API` | click Approve | POST `/api/reports/{id}/approve` |
| `frontend: module route discovered` | a test module in `src/modules/` | its route and nav entry exist |
| `frontend: no axe violations` | each page, mocked API | 0 violations |
| `test_frontend_mounted_when_built` (pytest) | a fake `frontend/dist/index.html` | `GET /app/` returns it |
| `test_frontend_absent_ok` (pytest) | no `dist` | app starts; `/app/` 404; old `/web/` still works |
