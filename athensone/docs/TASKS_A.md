# Tasks: Dev A (Αναστάσης) — Χάρτης & HUD

Board and cards for the Dev A track of [SPEC.md](SPEC.md). Workflow and rules: [`../../CLAUDE.md`](../../CLAUDE.md).
Base branch: `dev-a`. Every task: branch `agent/A<n>-<name>` in `.worktrees/A<n>`, merged into `dev-a` on
Αναστάσης's word. `dev-a` goes into `main` at phase 4 (freeze), together with `dev-b`.

Dev A owns (SPEC «Ιδιοκτησία αρχείων»): `web/citizen.html`, `web/css/hud.css`, `web/js/main.js`, `web/js/map.js`,
`web/js/layers/*.js`, `web/js/ui/layerbar.js`, `web/js/ui/workpopup.js`, `web/js/ui/routing.js`, and the tests for
them in `web/tests/`. Data comes **only** through `web/js/api.js` (Dev B); until Dev B's live endpoints exist,
`api.js` answers from `web/mock/`. Never call the backend or an external API from any other file.

**Tests:** `node --test web/tests/` from `athensone/` (Node 20+, no dependencies). Test the pure parts (camera,
style decisions, layer specs, state, numbers, labels) with plain fake objects for `map`, `document` and
`localStorage`. What only a browser can show (3D, animation, glass look) is checked by hand against the acceptance
criteria and recorded in the code report.

| Task | Phase | State |
|---|---|---|
| A0 Skeleton + test harness | 0 | done (merged into dev-a) |
| A1 Map core: 3D, Light/Dark, offline style | 1 | done (merged into dev-a) |
| A2 Six layers + pill bar | 2 | done (merged into dev-a) |
| A3 Φούσκα έργου | 2 | done (merged into dev-a) |
| A4 Routing drawer + animated route | 2 | done (merged into dev-a) |
| A5 Mobile layout, reasons highlight, smooth buses, A-35 bus | 3 | done (merged into dev-a) |
| A6 Integration polish & Dev B HUD styles | 3 | done (merged into dev-a) |

### A0: Skeleton + test harness (phase 0)
The folder layout of SPEC «Αρχιτεκτονική», empty but loading, so both devs can start in separate files.
**Files:** `web/citizen.html` (replace: markup + CDN + `<script type="module" src="js/main.js">`; keep the old page
as `web/citizen-legacy.html` until freeze), `web/css/hud.css`, `web/js/main.js`, `web/js/map.js`,
`web/js/layers/{env,access,works,transit,health,reports}.js`, `web/js/ui/{layerbar,workpopup,routing}.js`,
`web/package.json` (`{"type":"module","private":true}` so Node treats `web/js` as ES modules),
`web/tests/A0_skeleton.test.js`.
- Every module exports its functions and touches neither `document` nor `maplibregl` at import time (so Node can
  import it). `main.js` is the only file that runs code on load.
- Dev B's files (`js/api.js`, `js/ui/{points,report,stoa,workstab}.js`, `mock/*`) are **not** created here; `main.js`
  imports them only if they exist (dynamic `import()` in a try/catch), so A0 doesn't wait for B0. It mounts them
  as A-35 proposes (`mount({map, api, root, bus})`, shared `EventTarget` bus): **Αναστάσης confirms A-35 before A0**.

| Test | Given | Expected |
|---|---|---|
| `test_all_dev_a_modules_import_in_node` | import each Dev A module in Node | no error (no DOM/maplibre at import time) |
| `test_citizen_html_loads_maplibre_530` | read `web/citizen.html` | script + css from `cdn.jsdelivr.net/npm/maplibre-gl@5.3.0/dist/` |
| `test_citizen_html_has_single_module_entry` | same | exactly one `<script type="module" src="js/main.js">`, no inline script logic |

### A1: Map core — 3D, Light/Dark, offline style (phase 1)
SPEC F1, F9, «Engine και στυλ», «Offline fallback» 1–2.
**Files:** `web/js/map.js`, `web/js/main.js`, `web/css/hud.css`, `web/citizen.html`, `web/tests/A1_map.test.js`.
- `map.js` exports `CAMERA` (`center [23.7348, 37.9755]`, `zoom 15`, `pitch 55`, `bearing -15`, `maxPitch 70`),
  `STYLES` (`light` Liberty, `dark` Fiord URLs), `needs3dBuildings(style)`, `buildingsLayer()`, `offlineStyle(geo)`,
  `registerOverlay(fn)`, `addOverlays(map, state)`, `setTheme(map, theme, state)`, `createMap(container, state)`.
- `addOverlays()` runs on every `style.load`: adds the 3D layer when missing, then every registered overlay, then
  re-applies `state.visible[layerId]`.
- Style not loaded within 6 s, or a style/tiles `error` → `setStyle(offlineStyle(...))` (version 8, background +
  boundary/main-roads GeoJSON from `mock/`), and the overlays come back through `addOverlays()`.
- HUD: `.glass` exactly as SPEC «HUD», empty containers at the six HUD positions.

| Test | Given | Expected |
|---|---|---|
| `test_camera_matches_spec` | `CAMERA` | center, zoom, pitch, bearing, maxPitch as in SPEC |
| `test_needs_3d_when_no_fill_extrusion` | style JSON without a `fill-extrusion` layer | `true` |
| `test_no_3d_when_style_has_fill_extrusion` | style with one | `false` |
| `test_buildings_layer_spec` | `buildingsLayer()` | id `3d-buildings`, source `openmaptiles`, source-layer `building`, height `render_height`, base `render_min_height`, minzoom 14 |
| `test_add_overlays_restores_toggle_state` | fake map; `state.visible = {works: true, env: false}` | works layer visibility `visible`, env `none` |
| `test_set_theme_keeps_overlays` | fake map with overlays, `setTheme(map, "dark", state)`, fire `style.load` | `setStyle` called with the Fiord URL; every overlay re-added; toggle state unchanged |
| `test_offline_style_is_v8_background_only_base` | `offlineStyle(geo)` | `version: 8`, a `background` layer, no tile sources |
| `test_style_timeout_switches_offline` | fake map that never fires `style.load`, mocked timers advance 6 s | `setStyle` called with the offline style |
| `test_style_error_switches_offline` | fake map fires `error` | `setStyle` called with the offline style, once |

### A2: Six layers + pill bar (phase 2)
SPEC F2, HUD «Πάνω κέντρο», «Εξωτερικές πηγές» (layer look only; data is Dev B's).
**Files:** `web/js/layers/*.js`, `web/js/ui/layerbar.js`, `web/js/main.js`, `web/css/hud.css`,
`web/tests/A2_layers.test.js`.
- Each `layers/<name>.js` exports `id`, `label` (Greek, as on the chip), `register(map, api)` (adds its sources and
  layers, data from `api`), `layerIds` (every MapLibre layer it adds).
- Chips in this order: Θερμοκρασία/AQI (`env`, heatmap weighted on `temp_c` or `aqi`), Προσβασιμότητα/Ράμπες
  (`access`), Έργα (`works`, line + glow line with `line-blur`, orange in progress, blue planned), Τηλεματική ΟΑΣΑ
  (`transit` buses, polled every 20 s only while on), Μετρό/Προαστιακός (`transit` lines + stations in official
  line colours), Εφημερεύοντα (`health`). `reports` is always on (Waze pins), no chip.
- Chip on = filled colour, `aria-pressed="true"`; keyboard operable; horizontal scroll under 600 px.

| Test | Given | Expected |
|---|---|---|
| `test_six_chips_in_spec_order` | `layerbar.CHIPS` | the six ids and Greek labels, in SPEC order |
| `test_toggle_sets_visibility_on_all_layer_ids` | fake map, toggle `works` on | every id in `works.layerIds` set to `visible` |
| `test_toggle_updates_state_and_aria` | fake DOM chip, click twice | `state.visible.works` true → false; `aria-pressed` follows |
| `test_works_colour_by_status` | the works line paint | `in_progress` orange, `planned` blue (match expression) |
| `test_works_glow_layer_has_line_blur` | works layers | a second line layer with `line-blur > 0` |
| `test_env_heatmap_weight_uses_temp_or_aqi` | env layer, mode `temp` / `aqi` | `heatmap-weight` reads `temp_c` / `aqi` |
| `test_bus_polling_only_when_on` | mocked timers, transit off then on | `api.transit` called 0 times while off, every 20 s while on |
| `test_layers_get_data_only_through_api` | grep Dev A files | no `fetch(` outside `api.js` |

### A3: Φούσκα έργου (phase 2)
SPEC F4, «Φούσκα έργου (map popup)».
**Files:** `web/js/ui/workpopup.js`, `web/js/layers/works.js`, `web/css/hud.css`, `web/tests/A3_workpopup.test.js`.
- Pure helpers: `statusLabel(status)`, `paidPct(paid, contract)`, `guaranteeCountdown(handover, guaranteeEnd, today)`
  → `{daysLeft, pctLeft}`, `diavgeiaUrl(ada)`, `popupHtml(props, today)`.
- Click on a works line → `maplibregl.Popup` with class `glass` at the click point. «Ανέφερε πρόοδο» calls the
  report flow with `work_id` (Dev B's `ui/report.js`; if it isn't there yet, the button is hidden).
- Unknown values (no `guarantee_end`, no `amount_paid_eur`) show «άγνωστο», never 0 or a guess.

| Test | Given | Expected |
|---|---|---|
| `test_status_labels_greek` | `planned` / `in_progress` / `completed` | Προγραμματισμένο / Σε εξέλιξη / Ολοκληρωμένο |
| `test_paid_pct` | paid 30 000, contract 120 000 | 25 |
| `test_guarantee_countdown_mid` | handover 2026-01-01, end 2027-01-01, today 2026-07-02 | `daysLeft` 183, `pctLeft` ≈ 50 |
| `test_guarantee_countdown_expired` | today after end | `daysLeft` 0, `pctLeft` 0 |
| `test_guarantee_unknown` | no `guarantee_end` | text «άγνωστο», no bar |
| `test_diavgeia_link` | ada `Ψ1ΑΒΩ6Μ-123` | `https://diavgeia.gov.gr/decision/view/Ψ1ΑΒΩ6Μ-123` |
| `test_popup_has_contractor_euros_ada` | a mock works feature | HTML contains contractor, both € amounts, the ΑΔΑ link |
| `test_popup_escapes_html` | contractor `<img onerror=…>` | rendered as text, no element |

### A4: Routing drawer + animated route (phase 2)
SPEC F5, «Routing», HUD «Κάτω κέντρο». Route cost per profile is Dev B's (`/routing`); A draws what comes back.
**Files:** `web/js/ui/routing.js`, `web/js/main.js`, `web/css/hud.css`, `web/tests/A4_routing.test.js`.
- Bottom sheet with handle; from/to by search or map click; three profiles Αμαξίδιο (`wheelchair`), Καρότσι
  (`stroller`), Δροσερότερη (`cool`); last profile in `localStorage` and preselected.
- Route source with `lineMetrics: true`; `line-gradient` advanced by `requestAnimationFrame` over ~1.2 s; then
  `fitBounds` with bottom padding = drawer height + 24 px.
- Label under the route: duration, distance, reason (`reasons[].text` joined, e.g. «αποφεύγει 2 έργα, −2°C σκιά»).

| Test | Given | Expected |
|---|---|---|
| `test_profiles_three_in_order` | `PROFILES` | wheelchair, stroller, cool with Greek labels |
| `test_profile_saved_and_restored` | fake `localStorage`, pick `cool`, re-init | `cool` preselected |
| `test_route_source_has_line_metrics` | `routeSource(geojson)` | `lineMetrics: true` |
| `test_gradient_progress` | `gradientAt(0)`, `gradientAt(0.5)`, `gradientAt(1)` | valid `line-gradient` expressions; drawn part ends at 0 / 0.5 / 1 |
| `test_animation_duration_1200ms` | mocked rAF clock | progress reaches 1 at ~1200 ms, not before 1100 |
| `test_fit_bounds_padding_leaves_drawer` | drawer 300 px high | `fitBounds` bottom padding ≥ 324 |
| `test_route_label` | 1 520 m, 1 260 s, two reasons | «21′ · 1,5 km · αποφεύγει 2 έργα, −2°C σκιά» |
| `test_route_label_no_reasons` | `reasons: []` | duration and distance only, no dangling separator |

### A5: Mobile 390 px layout, reasons highlight, smooth buses & A-35 bus (phase 3)
SPEC Phase 3 («Κινητό layout, highlight των reasons στον χάρτη, λεία κίνηση λεωφορείων»), F6 `flyTo` + temporary highlight, Acceptance criterion (390 px mobile layout without HUD overlaps), `A-35` (approved by Αναστάσης: `mount({ map, api, root, bus })` + shared `EventTarget` `bus`), `A-37` (`pm25` env weighting), plus pre-freeze review leftovers (WCAG 2.5.3 `#theme-toggle`, `routing.js` `localStorage`/race guards, `workpopup.js` corner tips).
**Files:** `web/css/hud.css`, `web/citizen.html`, `web/js/main.js`, `web/js/map.js`, `web/js/layers/transit.js`, `web/js/layers/env.js`, `web/js/ui/routing.js`, `web/js/ui/workpopup.js`, `web/tests/A5_polish.test.js`.
- **Smooth bus movement (`layers/transit.js`):** export `interpolateBuses(prevFC, nextFC, t)` (linear interpolation for buses matching by `properties.id`/`id`; new buses pass straight through); when a 20 s bus poll returns new positions, animate smoothly via `requestAnimationFrame` and cancel any in-flight rAF when a newer poll arrives or buses are toggled off.
- **Route `reasons` highlight (`ui/routing.js`):** export `highlightReasons(map, reasons, lookup)`; draws/updates a dedicated highlight layer (`route-reasons-highlight`) for returned `reasons[{text, layer, feature_id}]`, clears it when `reasons` is empty or route clears, and restores it across `style.load`.
- **Shared `EventTarget` `bus` & Dev B `mount(ctx)` (`main.js`, `ui/workpopup.js`, `ui/routing.js`, per `A-35`):**
  - `main.js` creates `const bus = new EventTarget()`, mounts loaded Dev B UI modules (`points.js`, `report.js`, `stoa.js`, `workstab.js`) with `mod.mount({ map, api, root, bus })` when `typeof mod?.mount === "function"`, and loads offline base geometry from `api.offlineBase?.()` / `api.base?.()` into `state.offlineGeo` (no direct `fetch`).
  - `bus` event `map:flyto` (`{ lon, lat, label }`) → `map.flyTo({ center: [lon, lat], zoom: 17, pitch: 60 })` + temporary highlight marker/layer.
  - `bus` event `route:request` (`{ to: [lon, lat] }`) → sets destination in `routing.js` and triggers route calculation.
  - `workpopup.js` «Ανέφερε πρόοδο» dispatches `new CustomEvent("report:open", { detail: { work_id } })` on `bus` (in addition to `reportModule` fallback) and renders the button when `bus` or `reportModule` is available.
- **Mobile 390 px HUD layout (`hud.css`, `ui/routing.js`):** at `<= 600 px` (including 390 px), zero overlap across `#hud-tabs`, `#hud-points`, `#hud-layerbar`, `#hud-offline`, `#hud-report`, `#hud-routing`, `#hud-stoa` (routing drawer collapses cleanly on narrow screens; safe margins for bottom-left `+` and bottom-right Stoa bubble).
- **Pre-freeze polish:**
  - Fix WCAG 2.5.3 `label-content-name-mismatch` on `#theme-toggle` in `citizen.html` (remove mismatched static `aria-label` so visible Greek label is the accessible name, or include visible text).
  - Support `"pm25"` mode in `layers/env.js` alongside `"temp"` and `"aqi"` (`A-37`).
  - Fix `routing.js` review leftovers: access `globalThis.localStorage` inside `try/catch` (sandboxed iframe `SecurityError`), and ignore stale out-of-order async `api.routing()` responses via a request sequence counter.
  - Theme MapLibre corner-anchor popup tips (`-top-left`, `-top-right`, `-bottom-left`, `-bottom-right`) in `hud.css`.

| Test | Given | Expected |
|---|---|---|
| `test_bus_interpolation_midpoint` | previous & next bus FeatureCollections, `t = 0.5` | matching bus `id` at exact midpoint `[lon, lat]`; newly appearing bus passed through unchanged |
| `test_bus_animation_stops_on_toggle_off` | mocked rAF, poll updates buses then toggle off | `cancelAnimationFrame` called and no further `setData` updates after toggle off |
| `test_reasons_highlight_renders_matching_features` | `highlightReasons(map, reasons, lookup)` then `[]` | adds/populates `route-reasons-highlight` layer with matched features; clears to 0 features on `[]` |
| `test_bus_flyto_moves_map_to_spec_camera` | dispatch `map:flyto` `{ lon, lat, label }` on `bus` | `map.flyTo` called with `{ center: [lon, lat], zoom: 17, pitch: 60 }` |
| `test_bus_mounts_dev_b_ui_modules` | fake Dev B module exporting `mount(ctx)` | `bootstrap()` calls `mount({ map, api, root, bus })` with an `EventTarget` `bus` |
| `test_workpopup_dispatches_report_open_on_bus` | popup with `bus`, click «Ανέφερε πρόοδο» | `report:open` event dispatched on `bus` with `detail.work_id` |
| `test_theme_toggle_wcag_label_in_name` | read `web/citizen.html` `#theme-toggle` | no `aria-label` that omits the visible Greek button text (WCAG 2.5.3) |
| `test_routing_ignores_stale_async_response_and_storage_security_error` | throwing `localStorage` getter + slow req #1 resolving after fast req #2 | no uncaught `SecurityError`; req #2 route stays drawn and req #1 is ignored |

### A6: Integration polish & Dev B HUD styles (phase 3.5, pre-freeze)
Aligns Dev A's HUD stylesheet, map layers, and `main.js` wiring with Dev B's completed `B0–B10` modules on `origin/dev-b` (strictly Dev A files only; zero Dev B files touched).
**Files:** `web/css/hud.css`, `web/js/main.js`, `web/js/layers/access.js`, `web/js/layers/reports.js`, `web/js/layers/transit.js`, `web/js/ui/workpopup.js`, `web/tests/A6_integration.test.js`.
- **Glassmorphism CSS & animations for Dev B's 4 UI panels (`web/css/hud.css`):**
  - `[hidden] { display: none !important; }` rule so native `hidden` panels stay hidden even when styled with `display: flex`.
  - **Points (`points.js`):** `.points-pill`, `@keyframes points-pulse` (`600ms`) on `.points-pill.pulse`, rising `@keyframes points-float-up` (`600ms`) on `.points-float`, `.points-bar` / `.points-bar-fill`, `.points-panel` positioned absolutely below `#hud-points` (`right: 0`), `.points-history`, `.points-rewards`, `.points-redeem`, `.points-note`, `.points-status`.
  - **Report (`report.js`):** circular `.report-fab` («+»), absolutely positioned `.report-menu` and `.report-panel` above `#hud-report` (`bottom: calc(100% + 10px); left: 0`), `.report-preview`, light/dark + 390 px mobile rules.
  - **Stoa AI (`stoa.js`):** `.stoa-bubble`, `.stoa-panel` positioned absolutely above `#hud-stoa` (`bottom: calc(100% + 10px); right: 0;`) with `.glass` surface and `pointer-events` guard so the closed `visibility: hidden` panel never blocks map clicks, plus `.stoa-log`, `.stoa-msg`, `.stoa-user`, `.stoa-bot`, `.stoa-cite`, `.stoa-form`.
  - **Works tab (`workstab.js`):** `.workstab-panel` positioned absolutely below `#hud-tabs` (`top: calc(100% + 8px); left: 0;`) so appending it inside `#hud-tabs` never distorts the top-left pill, plus `.workstab-header`, `.workstab-filters`, `.workstab-filter`, `.workstab-search`, `.workstab-list`, `.workstab-card`, `.workstab-status-badge`, `.workstab-ada-link`, `.workstab-seed-badge`, `.workstab-card-actions`, `.workstab-focus`, `.workstab-report`.
- **`api.status` offline badge wiring (`main.js`, `layers/access.js`):**
  - `access.js` does not call `state.onOffline()` because `api.access()` is a static pre-downloaded OSM file by design (`SPEC.md` «Εξωτερικές πηγές»).
  - `main.js` listens to `api.status` `"source"` events (when `api?.status?.addEventListener` exists) and toggles `#hud-offline` based on `state.offline || api.isOffline?.()`.
- **Live report pins refresh (`layers/reports.js`, `main.js`):**
  - `reports.js` matches `"congestion"` alongside `"traffic"` / `"συμφόρηση"` (matching `B0`/`B6` category IDs) and exports `refresh(map, api, state)`.
  - `main.js` refreshes `reports` pins on `bus` `"points:earned"` so a newly submitted Waze report appears on the map immediately.
- **Work popup SEED & pin coordinates (`ui/workpopup.js`):**
  - When `props.seed` is truthy or `props.ada` starts with `"SEED-"` (`A-14`), omit the external `diavgeia.gov.gr` link and render plain ΑΔΑ text + `SEED · δοκιμαστικό` badge.
  - Include `lngLat: event.lngLat` in the `"report:open"` `CustomEvent` detail so the draggable report pin lands on the clicked street.
  - Return `null` from `guaranteeCountdown` when `today < handover` (or `status !== "completed"` only? No: keep `guaranteeCountdown` pure and clamp `daysLeft` to `totalDays` or keep existing mid/expired tests green — note: `test_popup_has_contractor_euros_ada` passes `in_progress` with valid dates, so only clamp `daysLeft <= totalDays` when `today < handover`).
- **Transit line IDs & per-poll gen (`layers/transit.js`):**
  - Include `["get", "id"]` and `"PROASTIAKOS"` in `lineColorExpression()` (matching `B0`/`B3` `transit.geojson`).
  - Increment `busPollGenByMap` at the start of each `updateBuses` poll so a slow earlier poll can never overwrite a newer poll (A5 review leftover).

| Test | Given | Expected |
|---|---|---|
| `test_hud_css_styles_all_dev_b_panels_and_animations` | read `web/css/hud.css` | defines `.points-pill.pulse` + `.points-float` (`600ms`), `.report-fab`/`.report-menu`/`.report-panel`, `.stoa-bubble`/`.stoa-panel` (`position: absolute`), `.workstab-panel` (`position: absolute`), and `[hidden]` rule |
| `test_reports_layer_matches_congestion_and_refreshes` | `reports.register` + `reports.refresh` with `category: "congestion"` | `circle-color` match expression includes `"congestion"`, and `refresh()` updates `reports-source` |
| `test_access_mock_source_does_not_trigger_offline_badge` | `access.register(map, apiReturningMock, state)` | `state.onOffline` is NOT called for static pre-downloaded `access` data |
| `test_main_syncs_offline_badge_with_api_status` | `bootstrap()` with fake `api.status` EventTarget + `api.isOffline()` | `#hud-offline` unhides when `api.isOffline()` becomes `true` and re-hides when `false` (while map is online) |
| `test_workpopup_suppresses_diavgeia_link_for_seed_work` | `popupHtml({ ..., ada: "SEED-ΑΔΑ-001", seed: true })` | no `<a href="https://diavgeia.gov.gr/...">` link; contains `SEED-ΑΔΑ-001` and `SEED` badge text |
| `test_workpopup_report_open_includes_click_lnglat` | click `"works-line"` at `{ lng: 23.73, lat: 37.97 }`, click «Ανέφερε πρόοδο» | `report:open` event detail includes both `work_id` and `lngLat` |
| `test_transit_ignores_stale_bus_poll_and_matches_proastiakos` | two overlapping polls (#1 slow, #2 fast) + rail layer paint | stale poll #1 does not overwrite poll #2's bus coords; `line-color` expression handles `PROASTIAKOS` |

### A10: Layer «Υπηρεσίες Δήμου» (phase 6, after freeze) — **merged** into `dev-a` and `main`
**Requested by Evgenii (Dev B owner) on 22 Nov after freeze, built by Dev B's agents on Dev A files: Αναστάσης to
review before the pitch.** Data: `api.pois()` (B14, `GET /api/map/pois`): GeoJSON Points, properties `{id, name,
category, address, open_now, distance_km, source, official: true}`; categories today `friendship_club` (Λέσχες
Φιλίας, the former ΚΑΠΗ: unverified rename) and `library`. Offline mock: `web/mock/pois.geojson` (3 fictional POIs).
**Files:** `web/js/layers/pois.js` (new), `web/js/ui/layerbar.js` (+1 chip), `web/js/main.js` (+1
`registerOverlay`), `web/tests/A10_pois_layer.test.js` (new), and **the test writer updates the chip-count asserts**
`web/tests/A2_layers.test.js:441`, `web/tests/A7_ux_upgrades.test.js:189` and `:229` from 6 to 7 (owner-approved,
A-40: SPEC lists six layers; this seventh is an addition).
- `layers/pois.js` like `layers/health.js`: `id = "pois"`, `label = "Δήμος"`, `layerIds = ["pois-points"]`,
  `register(map, api, state)` adds a geojson source + circle layer (hidden unless `state.visible.pois`), loads
  `api.pois()`, calls `state.onOffline()` when `source !== "live"`. Colour per category: `friendship_club` and
  `library` each their own colour, anything else a default.
- `popupHtml(props)` (exported, pure): name (escaped), Greek category label (`friendship_club` «Λέσχη Φιλίας»,
  `library` «Βιβλιοθήκη», else the raw id), address or «άγνωστο», open now «Ανοιχτό τώρα» / «Κλειστό τώρα» /
  «Ωράριο: άγνωστο» for `true`/`false`/`null`, an «επίσημο» badge, and «δοκιμαστικό» when `props.source === "mock"`.
  In `register`, a click on `pois-points` opens a `maplibregl.Popup` with it (only when `globalThis.maplibregl`
  exists; nothing at import time).
- Chip added **last** in `layerbar.CHIPS` (after Εφημερεύοντα), `aria-pressed` like the others. The 390 px mobile
  layout must still not overflow horizontally (the bar already scrolls; check A5 tests stay green).

| Test | Given | Expected |
|---|---|---|
| `pois layer exports id, label, layerIds` | import `layers/pois.js` | `id === "pois"`, `label === "Δήμος"`, `layerIds` = `["pois-points"]`; no `document`/`maplibregl` touched at import |
| `register adds source and hidden layer` | fake map, fake api `pois()` → 2 features, `state.visible = {}` | one geojson source, one circle layer with `visibility: "none"`, source data set to the 2 features |
| `register visible when state says so` | `state.visible.pois = true` | layer `visibility: "visible"` |
| `register calls onOffline for mock data` | `api.pois()` → `source: "mock"` | `state.onOffline` called once |
| `register survives api failure` | `api.pois()` rejects | no throw; source has an empty collection |
| `popupHtml shows Greek category and open state` | `{name: "Λέσχη Φιλίας Παγκρατίου", category: "friendship_club", address: "Χ 1", open_now: true, source: "live"}` | contains «Λέσχη Φιλίας», «Ανοιχτό τώρα», «επίσημο», not «δοκιμαστικό» |
| `popupHtml unknowns` | `address: null, open_now: null` | «άγνωστο» and «Ωράριο: άγνωστο» |
| `popupHtml escapes the name` | `name: "<img src=x onerror=1>"` | no `<img` in the output |
| `popupHtml labels mock` | `source: "mock"` | «δοκιμαστικό» |
| `layerbar has the Δήμος chip last` | `layerbar.CHIPS` | 7 chips, last `id === "pois"`, `label === "Δήμος"` |
