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

## Full app, wave 1 and 2 (start after T11 and T12 are merged)

Every module (A-23): backend `app/modules/<name>/` (models on `Base`, pure `service.py`, `router.py` under
`/api/<name>`), Alembic migration `alembic/versions/<name>_*.py`, frontend `frontend/src/modules/<name>/`, tests
`tests/test_T<n>_<name>.py` + Vitest beside the module, a `README.md` in the module folder. Points are granted
only through the points service, only after a human or a second resident verifies (Proposal §4). No location
tracking; locations only on things people post on purpose. Data that doesn't exist yet shows "σύντομα" (coming),
never invented values.

| Task | Module | State |
|---|---|---|
| T13 | Docker Compose deploy | waits for T11 |
| T14 | Χαρτογράφοι Προσβασιμότητας | waits for T11, T12 |
| T15 | Your Voice (proposals and votes) | waits for T11, T12 |
| T16 | Give & Share | waits for T11, T12 |
| T17 | What's On | waits for T11, T12 |
| T18 | Points, spend side | waits for T11, T12 |
| T19 | Smart Clean | waits for T11, T12 |
| T20 | Smart Parking | waits for T11, T12 |
| T21 | Operator console + "what was spent on my street" | waits for T11, T12 |

### T13: Docker Compose deploy
**Files:** `docker-compose.yml`, `backend.Dockerfile`, `frontend/Dockerfile`, `frontend/nginx.conf`, `.env.example`,
`deploy/README.md`, `tests/test_T13_deploy.py`. Services: `db` (postgis/postgis:16-3.4, volume, healthcheck),
`api` (uvicorn, runs `alembic upgrade head` first, `DATABASE_URL` to db), `web` (nginx serving `frontend/dist`,
proxying `/api`, `/open311`, `/ngsi-ld`, `/dcat`, `/photos` to api). Secrets only from `.env`.

| Test | Given | Expected |
|---|---|---|
| `test_compose_parses` | `docker-compose.yml` loaded as YAML | services db, api, web; api depends on db healthy |
| `test_no_secret_in_compose` | the file | no literal key/password values, only `${VAR}` |
| `test_api_image_runs_migrations` | `backend.Dockerfile` + entry command | `alembic upgrade head` before uvicorn |
| `test_nginx_proxies_api_paths` | `nginx.conf` | `/api/`, `/open311/`, `/ngsi-ld/`, `/dcat/`, `/photos/` proxied |
| `test_postgres_smoke` (skipped unless `TEST_DATABASE_URL`) | a Postgres URL | smoke loop passes on Postgres |

### T14: Χαρτογράφοι Προσβασιμότητας (accessibility mappers)
Residents mark ramps, benches, tactile paving, obstacles; a second resident verifies (Project Sidewalk label
types, MIT: taxonomy only). Verified points feed Navigate (obstacles excluded, benches as rest stops).
- `POST /api/mappers/points` {kind, lat, lng, note?, photo?} (photo through `privacy.py`); `POST …/{id}/confirm`
  {agree: bool} by a different token; verified at 2 agreeing answers, rejected at 2 disagreeing.
- `GET /api/mappers/points?bbox&status` GeoJSON. Verified obstacles join `active_hazards()` exclusions; verified
  benches join env rest points. +3 points to the mapper on verification (daily cap 10).

| Test | Given | Expected |
|---|---|---|
| `test_add_point_pending` | a ramp point | status pending, no points yet |
| `test_same_token_cannot_confirm` | mapper confirms own point | 403 |
| `test_two_agree_verifies_and_pays` | 2 other tokens agree | verified; mapper +3 once |
| `test_two_disagree_rejects` | 2 disagree | rejected, no points |
| `test_verified_obstacle_excluded_in_route` | verified obstacle on route | in Valhalla exclude list |
| `test_photo_blurred` | point with EXIF photo | stored copy has no EXIF |
| `test_daily_cap_10` | 11 verifications in a day | 30 points |

### T15: Your Voice (proposals and votes)
Proposals pinned on the map, time-boxed votes, official status. Decidim (AGPL) is not copied; a link-out field
`decidim_url` is allowed.
- `POST /api/voice/proposals` {title, body, lat?, lng?, district}; operator `PATCH …/{id}` status
  (submitted|under_review|accepted|rejected|done) with a public note; `POST …/{id}/vote` once per token, only while
  `open_until` is in the future; `GET` list with counts. +5 points per vote (cap 1/day), never for proposing.

| Test | Given | Expected |
|---|---|---|
| `test_vote_once_per_token` | same token votes twice | one vote |
| `test_vote_after_close_rejected` | `open_until` past | 409 |
| `test_status_change_needs_operator` | citizen PATCH | 403 |
| `test_counts_by_district` | votes in 2 districts | per-district counts, no tokens |
| `test_vote_points_capped` | 3 votes a day | 5 points |

### T16: Give & Share
Post an item with a photo; hand-over only at partner points (Friendship Club, library), never a home address.
- `POST /api/share/items` {title, category, photo, partner_point_id}; `POST …/{id}/request`; both sides confirm
  hand-over → +15 each (cap 2/day). Partner points: Friendship Clubs from the sandbox POIs + `data/share_partners.json`.
- Social-services role can request items first (flag `priority`).

| Test | Given | Expected |
|---|---|---|
| `test_item_needs_partner_point` | no partner point | 422 |
| `test_no_address_fields_accepted` | body with `address` | 422 or ignored, never stored |
| `test_handover_both_confirm_pays_both` | both confirm | +15 each, once |
| `test_one_side_confirm_pays_nothing` | one confirms | no points |
| `test_photo_blurred` | EXIF photo | stored without EXIF |

### T17: What's On
Municipal and partner events on map and calendar with verified accessibility info and reminders.
- `GET /api/events?from&to&bbox&accessible=1`; source: CKAN if an events dataset exists (search `package_search?q=εκδηλώσεις`),
  else `data/events_seed.json` labelled SEED. Accessibility fields (`step_free`, `toilet_wheelchair`, `seats`) shown
  only when verified (by T14 data or source), else UNKNOWN. iCal export `GET /api/events/{id}.ics`.

| Test | Given | Expected |
|---|---|---|
| `test_seed_events_labelled` | no CKAN | `source` SEED on every event |
| `test_filter_accessible` | `accessible=1` | only events with verified `step_free` true |
| `test_unknown_accessibility` | no data | fields "UNKNOWN", not false |
| `test_ics_export_valid` | one event | valid VCALENDAR with DTSTART/LOCATION |

### T18: Points, spend side
Rewards from the Proposal: City perks in kind, partner rewards, donations, tiers, 12-month expiry.
- `GET /api/points/rewards` (from `data/rewards.json`, partner-funded flagged); `POST /api/points/redeem`
  {reward_id} → a negative ledger row and a one-time code; `POST /api/points/donate` {target: club|grocery|pb_project};
  balance now excludes rows older than 12 months (A-10 revisited); account delete `DELETE /api/points/me` removes
  history (Proposal: delete any time).

| Test | Given | Expected |
|---|---|---|
| `test_redeem_reduces_balance` | 100 points, reward 50 | balance 50, code returned |
| `test_redeem_insufficient` | 10 points, reward 50 | 409, no row |
| `test_donate_moves_points` | donate 20 | −20 row, target total +20 |
| `test_points_expire_after_12_months` | a row 13 months old | not in balance |
| `test_delete_account_removes_history` | DELETE me | no rows for that token |

### T19: Smart Clean
Collection day and time by address, bulky pickup booking, bin problems, recycling map.
- Schedules from CKAN if a dataset exists (search "απορρίμματα", "ανακύκλωση"), else the layer says "σύντομα".
  Recycling points from OSM (`amenity=recycling`, add to `fetch_env.py`). `POST /api/clean/bulky` booking request
  (date window, item type, partner pickup point or kerb, no free-text address stored beyond the street);
  `POST /api/clean/bins` report → goes through the existing report flow (category `bin`).

| Test | Given | Expected |
|---|---|---|
| `test_schedule_unknown_says_coming` | no dataset | `status` "coming", no invented times |
| `test_recycling_points_from_osm` | features with recycling | GeoJSON points |
| `test_bulky_booking_created` | valid request | 201, status requested |
| `test_bin_report_uses_report_flow` | bin photo | sandbox request created, photo blurred |

### T20: Smart Parking
Municipal garages, disabled spaces, controlled-parking zones, one-tap "car on ramp" report. Street availability
only where sensors exist, never guessed.
- Garages and disabled spaces from CKAN if present, else OSM (`amenity=parking`, `parking_space=disabled`,
  add to `fetch_env.py`); `available` only from a live source, else null + "σύντομα". `POST /api/parking/ramp-block`
  → report flow with category `illegal_parking_ramp` and the hazard into routing.

| Test | Given | Expected |
|---|---|---|
| `test_availability_null_without_sensor` | OSM garage | `available` null |
| `test_disabled_spaces_layer` | OSM data | GeoJSON points |
| `test_ramp_block_creates_hazard` | one-tap report | hazard in `/api/hazards` |

### T21: Operator console + "what was spent on my street"
- `GET /api/console/kpis?district&from&to`: reports, median hours to triage, duplicates caught, reopen rate,
  guarantee claims drafted, verified points actions, mapped points (all computed by code from the DB).
- `GET /api/works/street?name=` public page data: every works card on that street with euros, contractor,
  guarantee clock, ΑΔΑ links (SEED labelled). Frontend: operator dashboard page + public street page.
- Weekly district brief stays "next" (Proposal); no LLM here.

| Test | Given | Expected |
|---|---|---|
| `test_kpis_counts` | seeded reports | numbers equal a hand count |
| `test_kpis_district_filter` | district param | only that district |
| `test_street_page_cites_ada` | SEED street | every card has its ΑΔΑ, SEED label |
| `test_street_unknown_empty` | unknown street | empty list, no error |
