# Backlog

Later improvements, not work to do now. Each with its reason.

- Licence-plate blurring (deface does faces only). Pitch as "next step".
- Swipe verification, predictive maintenance (H3 + scikit-learn), weekly district brief (Instructor), Greek voice
  reports (faster-whisper + Krikri), heat-buddy matching, building shadows (SunCalc), Aequitas audit: pilot phase,
  per the Build Plan.
- T1: confirm on a non-resolved report is allowed (A-7); restrict in the pilot. Answering confirm twice overwrites.
- T2: daily cap uses SQLite UTC `date('now')` (Athens day starts 2–3 h earlier); cap hit is silent. Duplicate
  report submission doesn't mint a token.
- T3: `_shaded_minutes()` omits the busy-road/rest penalties `navigate(heat=True)` uses; minutes may differ slightly.
- T9: a works-type question with an extra content word ("Ποια έργα ασφαλτόστρωσης ολοκληρώθηκαν;", "… στην Αθήνα")
  refuses, because unknown words count as a street name; needs a street gazetteer. Demo: ask by street name.
- T9: `verify()` checks dates/amounts as a set per answer, so a rephraser could swap two real dates on the same card.
  Only matters with the optional rephrase on (off by default); fix by checking each sentence against its own field.
- T5: when CenterFace runs and finds 0 faces, Haar isn't tried as a second check (by design: fewer false blurs).
- T5: `test_original_never_on_disk` re-detects with threshold 0.5, not the app's 0.2 (blur still gives 0 at 0.2).
- T5: CenterFace model licence (MIT, from memory): open the Star-Clouds/CenterFace LICENSE before the final push.
- T10: `_rings()` ignores polygon holes; `_registry()` reads column names from the first row only; WKT parser
  accepts junk Z/M tokens and unclosed 3-point rings. All low; City data today has none of these.
- B0: several CKAN sensors share a neighbourhood centroid in `web/mock/env.json` (stacked heatmap weight);
  `reports_count` in `works.geojson` doesn't match the report pins; `test_reports_rounded_and_anonymous` doesn't
  check the contract keys. The in-progress SEED work has a guarantee date (popup should show the countdown only for
  `completed`). Low; the live endpoints replace the mocks.
- B5: if CKAN is unreachable and nothing is cached, one `/api/map/env` refresh makes 270 failed CKAN calls (fetch the
  station list once per refresh); `ENV_BBOX` not validated; `?bbox=%20` gives 422 while `?bbox=` gives the full grid.
- B1: `points()` is cached under one key per device; mock fallback answers are not filtered by `bbox` or `status`;
  FastAPI 422 returns `detail` as a list of objects rather than a string.
- B2: `data/stoa/works.json` not committed (ΚΗΜΔΗΣ rate-limited 429 on bulk pull, and `works.py` prefers it over SEED
  unless `STOA_WORKS_PATH` is pinned in `tests/conftest.py`); `scripts/fetch_works.py` has no 429 retry.
- B3: if 1 of 8 polled OASA bus routes succeeds and others fail, `get_buses()` returns only the live route; runtime
  `data/transit/last.json` not in `.gitignore`.
- B4: Ministry of Health `.doc` has two duty windows (08:00–08:00 next day vs 08:00–23:00), so hospital `hours` is
  `null` until the window parser is added; snapshot `updated_at` uses response time; runtime `data/onduty/` caches not
  in `.gitignore`; spot-check hospital phone numbers in `data/onduty/hospitals.json`.
- B6: `ui/report.js` accepts both `api.postReport` and `api.sendReport`; Athens bounding-box check not enforced on
  `POST /api/map/reports`; `bbox=nan` returns empty rather than 422; Russian-plate Haar cascade is best-effort on Greek
  plates.
- B7: history dates in `ui/points.js` use `h.ts.slice(0, 10)` (UTC date).
- B8: `city_ask` does not forward `center` to `/api/ask`, so «Δροσερά μέρη κοντά» uses `DEMO_START`; works questions for
  streets outside SEED fall through to the City answer.
- B9: if every wheelchair candidate touches an obstacle, the least-bad candidate is returned without a `blocked: true`
  flag (needs both owners if added to the contract); `env` reasons use `feature_id` `"shade"` / `"busy_road"`; second
  `routing.candidates()` call for the `reasons` baseline doubles live Valhalla latency.
- B10: `formatEur(value)` formats `0` or negative amounts if passed (backend and mocks use `null` for unknown); `Escape`
  listener on `root` only fires when focus is inside `root`.
- B11: `works_map._open_reports()` counts sandbox requests only (not SQLite-only `work_progress` rows in `map_reports`);
  `routing_map._open_reports()` reads legacy `store.all_reports()` rather than `map_reports`; offline queue `flush()` in
  `ui/report.js` emits `points:earned` on `bus` but not `report:created`.
- B12: when the sandbox is down, `routing_map._open_reports()` drops linked `obstacle` map reports (missing `"submitted"`
  default in `status.get(row["city_request_id"])`); duplicate `obstacle`/`damage` map reports within 50 m / 30 min have
  `city_request_id = None` and increment `works_map` `reports_count`.
- B13: check the 11 `service_guide.QUERIES` against the live sandbox registry (top hit = right service?) once the key
  is in; tests are offline. In mock mode `POST /api/ask` texts with a catalogue keyword (e.g. «δέντρο») now get that
  mock service instead of `svc-mock-1`. No UI calls `api.serviceFor()` yet (report.js could show it after submit).
- B14: only `friendship_club` and `library` POI categories are verified; get the sandbox OpenAPI spec for the rest.
  No map layer calls `api.pois()` yet (Dev A).
- B15: no map layer calls `api.resolved()` yet (Dev A); future-dated `resolved_at` values are kept.
- Dev B: find the sandbox's other POI categories (ΚΕΠ, cooling rooms, nurseries, ...) from its OpenAPI spec or a
  live `GET /api/pois?radius_km=5` with the key, then add the verified ones to `pois_map.DEFAULT_CATEGORIES`.
- A10: done (layer «Δήμος»). Αναστάσης to review; check 390 px and Dark-mode contrast of `#7c3aed`/`#475569` in a
  browser; `.pois-popup` and B17's `.report-service` have no CSS yet (`hud.css`, Dev A). Verify the ΚΑΠΗ → Λέσχες
  Φιλίας rename before saying it on stage.
- B16: legacy `POST /api/report` has no Δήμος bbox check (SPEC: existing calls unchanged); `ENV_BBOX` is a rectangle,
  so points in neighbouring municipalities inside it pass; `zoneinfo` needs the `tzdata` package on Windows (new
  dependency, owner approval); `works_map._linked` is one query per map report.
- B17: «Εμπόδιο» reports have no subtype in the form, so they never show a service; the «n €» cost wording is ours.
