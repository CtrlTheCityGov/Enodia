# Navigation: best route for *this* person, not just the shortest

**Hard rules (never traded off):** step-free costing for the chosen profile (Valhalla `pedestrian`:
wheelchair / walker / stroller → `type: wheelchair`, visually impaired → `type: blind`) and every open
reported hazard excluded (`exclude_locations`).

**Soft preferences (ranked, explainable, no AI):**

| Toggle | Metric along the route (sampled every 15 m) | Data |
|---|---|---|
| 🌳 Σκιά | % within 12 m of a tree or inside a park | OSM trees, tree rows, parks (canopy proxy; building shadows not yet) |
| 🍃 Μακριά από κίνηση | % within 20 m of trunk/primary/secondary roads | OSM roads (noise/exhaust proxy, not a sensor) |
| 🪑 Στάσεις | rest points within 30 m; **longest stretch without one** | OSM benches, drinking water, wheelchair toilets + Friendship Clubs/libraries from AthensGov |
| 🌡 Καύσωνας | raises the shade + rest weights | manual, or automatic at ≥ 33 °C from Open-Meteo (`HEAT_C`) |

**How:** `/api/navigate` asks Valhalla for the best route + 2 alternates, plus one more with busy
roads excluded (`exclude_polygons`). It scores each one and picks the lowest
`minutes × (1 + w_shade·(1−shade) + w_air·busy + rest_penalty)`. Routes > 1.4× the fastest are dropped
(`max_detour`). The app draws the winner, shows the others dashed, and says why in one Greek sentence
("100% σκιά αντί 24%, … με 1′ περισσότερο"). The user can tap any alternative.

**Before the demo:** `python scripts/fetch_env.py --bbox 37.955,23.725,37.980,23.760` (Pangrati, ~1 min)
→ `data/env/features.json`; banners switch from SEED to OSM. Without it, SEED data (fictional, around
Plateia Varnava) is used and labelled.

**Next (pitch, not built):** building shadows by time of day (SunCalc + OSM building heights, as in the
Shaadiest prototype), slope from elevation, live air quality from the City's environmental stations
(CKAN), night mode with lit streets (`use_lit`).
