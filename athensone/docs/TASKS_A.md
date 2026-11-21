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
| A0 Skeleton + test harness | 0 | card, needs approval |
| A1 Map core: 3D, Light/Dark, offline style | 1 | card, needs approval |
| A2 Six layers + pill bar | 2 | card, needs approval |
| A3 Φούσκα έργου | 2 | card, needs approval |
| A4 Routing drawer + animated route | 2 | card, needs approval |
| A5 Mobile layout, reasons highlight, smooth buses | 3 | idea, card later |

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
  imports them only if they exist (dynamic `import()` in a try/catch), so A0 doesn't wait for B0.

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
