# AthensOne AI — Προδιαγραφές Citizen Map

Nov 21, 2026 · @gribonoff · Markdown export of [`SPEC.pdf`](SPEC.pdf). **This document is the project's canon:
if anything else in the repo disagrees with it, the spec wins.** Paths like `web/…` are relative to `athensone/`.

## Επισκόπηση

Το `web/citizen.html` γίνεται ένας full-screen 3D χάρτης της Αθήνας σε στυλ Google Maps + Waze, με MapLibre GL JS
5.3.0 και OpenFreeMap (χωρίς API keys). Ο στόχος είναι ένα λειτουργικό demo για το Apps4Athens 3.0 (21–22
Νοεμβρίου 2026), με δύο developers.

Ο πολίτης βλέπει σε έναν χάρτη ό,τι συμβαίνει στη γειτονιά του: περιβάλλον, προσβασιμότητα, συγκοινωνίες,
εφημερεύοντα φαρμακεία και νοσοκομεία, έργα του Δήμου με διαφάνεια από Διαύγεια και ΚΗΜΔΗΣ. Αναφέρει συμβάντα όπως
στο Waze, κερδίζει «Πόντους Γειτονιάς» και ρωτάει τη Stoa AI.

**Παραδοχές** (επιβεβαιώστε πριν το build):
- Το backend υπάρχει ήδη και εκθέτει τα `/routing`, `/env`, `/works`, `/points`, `/stoa_ask`, `/reports`. Τα
  σχήματα της ενότητας «Πηγές δεδομένων» είναι τα αναμενόμενα· αν διαφέρουν, προσαρμόζει μόνο το `api.js`.
  (Τα πραγματικά routes του backend: βλ. [Παράρτημα](#παράρτημα-spec--υπάρχον-backend).)
- Το αρχικό PDF του project δεν ήταν διαθέσιμο κατά τη σύνταξη· ό,τι προβλέπει και λείπει εδώ προστίθεται.

## Λειτουργίες

Τα F1–F6 και το υπόλοιπο πόντων του F7 είναι το MVP του demo· τα υπόλοιπα μπαίνουν μόνο αν το MVP δουλεύει
end-to-end.

| # | Feature | Τι κάνει | Πηγή / endpoint | Προτεραιότητα |
|---|---|---|---|---|
| F1 | 3D χάρτης | MapLibre, Liberty/Fiord, pitch 55, bearing −15, 3D κτίρια | OpenFreeMap | MVP |
| F2 | Layers | Θερμοκρασία/AQI, Προσβασιμότητα/Ράμπες, Έργα, Τηλεματική (ΟΑΣΑ), Μετρό/Προαστιακός, Εφημερεύοντα φαρμακεία/νοσοκομεία | `/env`, `/works`, νέα `/transit`, `/health` | MVP |
| F3 | Αναφορές πολιτών (Waze) | Κουμπί «+»: συμφόρηση, συμβάν, εμπόδιο, ζημιά, πρόοδος έργου· φωτογραφία με blur προσώπων/πινακίδων | `/reports` | MVP |
| F4 | Φούσκα έργου | Popup πάνω στον δρόμο: ανάδοχος, € πληρωμένα, countdown εγγύησης, ΑΔΑ | `/works` | MVP |
| F5 | Διαδρομές | Bottom sheet: προορισμός + προφίλ (Αμαξίδιο, Καρότσι, Δροσερότερη διαδρομή)· λαμβάνει υπόψη τα layers και τα έργα | `/routing` | MVP |
| F6 | Stoa AI chatbot | Γενικής χρήσης· οι δρόμοι που αναφέρει είναι clickable και κάνουν `flyTo` | `/stoa_ask` | MVP |
| F7 | Πόντοι Γειτονιάς (Loyalty) | Υπόλοιπο, progress δημοτικής κοινότητας, pulse, κατάλογος εξαργύρωσης με τον Δήμο | `/points` | MVP (υπόλοιπο), Nice (εξαργύρωση) |
| F8 | Tab Έργων | Λίστα έργων με φίλτρα· crowdsourced φωτογραφίες/σχόλια προόδου που φτάνουν στον Δήμο | `/works`, `/reports` | Nice |
| F9 | Light/Dark | Εναλλαγή Liberty ↔ Fiord χωρίς να χαθούν τα overlays | OpenFreeMap | Nice |

## Map & Visual Spec

Ένα full-screen canvas (100vw × 100vh) χωρίς sidebars· όλα τα controls είναι floating glass στοιχεία πάνω από τον
χάρτη.

### Engine και στυλ

- MapLibre GL JS μέσω CDN:
  - JS: `https://cdn.jsdelivr.net/npm/maplibre-gl@5.3.0/dist/maplibre-gl.js`
  - CSS: `https://cdn.jsdelivr.net/npm/maplibre-gl@5.3.0/dist/maplibre-gl.css`
- Default style: Liberty `https://tiles.openfreemap.org/styles/liberty`. Toggle Light/Dark σε Fiord
  `https://tiles.openfreemap.org/styles/fiord`.
- Αρχική κάμερα: κέντρο Σύνταγμα `[23.7348, 37.9755]`, zoom 15, `pitch: 55`, `bearing: -15`, `maxPitch: 70`.
- 3D κτίρια: αν το style έχει ήδη layer `fill-extrusion`, μένει ορατό. Αν λείπει (π.χ. στο Fiord), προστίθεται
  layer `3d-buildings` από το source `openmaptiles`, source-layer `building`, με `fill-extrusion-height` =
  `render_height` και `fill-extrusion-base` = `render_min_height`, από zoom 14.
- Στο `setStyle()` για Light/Dark χάνονται τα custom sources/layers. Λύση: συνάρτηση `addOverlays()` που καλείται σε
  κάθε `style.load` και ξαναπροσθέτει όλα τα overlays και την κατάσταση των toggles.

### HUD (glassmorphism)

Κοινή κλάση `.glass`: `background: rgba(255,255,255,.55)` (dark: `rgba(20,24,32,.55)`),
`backdrop-filter: blur(12px)`, `border: 1px solid rgba(255,255,255,.3)`, `border-radius: 999px` για pills και
`16px` για panels, ήπια σκιά.

| Θέση | Στοιχείο | Συμπεριφορά |
|---|---|---|
| Πάνω κέντρο | Pill bar με layer toggles | 6 chips: Θερμοκρασία/AQI, Προσβασιμότητα/Ράμπες, Έργα (Διαύγεια+ΚΗΜΔΗΣ), Τηλεματική ΟΑΣΑ, Μετρό/Προαστιακός, Εφημερεύοντα. Ενεργό chip = γεμάτο χρώμα. Σε κινητό οριζόντιο scroll |
| Πάνω δεξιά | «Πόντοι Γειτονιάς» pill | Live υπόλοιπο + progress bar δημοτικής κοινότητας. Animation `pulse` 600ms και «+N» που ανεβαίνει όταν κερδίζονται πόντοι. Κλικ ανοίγει panel με ιστορικό και εξαργύρωση |
| Πάνω αριστερά | Tabs Χάρτης / Έργα + Light/Dark | Το tab Έργα ανοίγει glass panel με λίστα και φόρμα crowdsourcing (F8) |
| Κάτω αριστερά | Κουμπί «+» (Waze) | Radial menu κατηγοριών → pin στο κέντρο του χάρτη (draggable) → φωτογραφία προαιρετική → αποστολή. Μήνυμα «Θολώνουμε πρόσωπα και πινακίδες…» κατά το upload |
| Κάτω δεξιά | Φούσκα Stoa AI | Ανοίγει ομαλά (transform + opacity, 250ms) σε panel 380×520. Οι δρόμοι στις απαντήσεις είναι links· κλικ → `map.flyTo({center, zoom: 17, pitch: 60})` + προσωρινό highlight |
| Κάτω κέντρο | Routing drawer | Bottom sheet με λαβή· από/προς (αναζήτηση ή κλικ στον χάρτη) + 3 προφίλ |

### Φούσκα έργου (map popup)

Κλικ σε highlighted έργο ανοίγει `maplibregl.Popup` με κλάση `.glass`, αγκυρωμένο στο σημείο κλικ πάνω στον δρόμο.
Περιέχει:
- Τίτλο έργου και κατάσταση (Προγραμματισμένο / Σε εξέλιξη / Ολοκληρωμένο)
- Ανάδοχο
- € πληρωμένα / € σύμβασης, με progress bar
- Countdown εγγύησης: μπάρα που αδειάζει από την παραλαβή ως τη λήξη, με «X μέρες ακόμα»
- Το ΑΔΑ ως highlighted quote, link στο `https://diavgeia.gov.gr/decision/view/<ΑΔΑ>`
- Κουμπί «Ανέφερε πρόοδο» που ανοίγει τη φόρμα αναφοράς για αυτό το έργο

Τα έργα σχεδιάζονται ως `line` layer πάνω στον δρόμο (πορτοκαλί σε εξέλιξη, μπλε προγραμματισμένα), με glow από
δεύτερο line layer με `line-blur`.

### Routing

Η διαδρομή υπολογίζεται από τα πεδία των layers, με βάρη που ορίζει το προφίλ του χρήστη. Το `/routing` διαβάζει τα
ίδια δεδομένα με τον χάρτη (`/env`, `/works`, `/reports`, προσβασιμότητα, `/transit`) και τα μετατρέπει σε κόστος
ανά τμήμα δρόμου. Έτσι, ό,τι βλέπει ο χρήστης στον χάρτη είναι αυτό που επηρεάζει τη διαδρομή.

| Προφίλ | Τι προτιμά | Τι αποφεύγει / αποκλείει |
|---|---|---|
| Αμαξίδιο | Ράμπες, χαμηλωμένα κράσπεδα, σταθμοί μετρό με ανελκυστήρα | Αποκλείει σκαλιά και τμήματα με ενεργό έργο ή αναφορά εμποδίου |
| Καρότσι | Άνετα πεζοδρόμια, χαμηλωμένα κράσπεδα, καλό AQI | Αποφεύγει έργα, σκαλιά, συμφόρηση |
| Δροσερότερη διαδρομή | Χαμηλή θερμοκρασία, σκιά/πράσινο, καλό AQI | Αποφεύγει θερμές ζώνες και δρόμους με υψηλό PM2.5 |

Και τα τρία προφίλ μπορούν να προτείνουν ένα κομμάτι με μετρό, προαστιακό ή λεωφορείο, χρησιμοποιώντας τη τηλεματική
για τον χρόνο αναμονής. Το προφίλ αποθηκεύεται στο `localStorage` και ανοίγει προεπιλεγμένο στον drawer. Το
`reasons` της απάντησης αναφέρει ποια στοιχεία των layers άλλαξαν τη διαδρομή, και τα αντίστοιχα features
φωτίζονται στον χάρτη.

- Η γραμμή της διαδρομής ζωγραφίζεται με animation: `line-gradient` (απαιτεί `lineMetrics: true` στο source) που
  προχωρά μέσω `requestAnimationFrame` σε ~1.2s.
- Μετά το animation, `fitBounds` με padding που αφήνει χώρο για τον drawer.
- Ετικέτα κάτω από τη διαδρομή: διάρκεια, απόσταση και ο λόγος της επιλογής (π.χ. «αποφεύγει 2 έργα, −2°C σκιά»).

## Πηγές δεδομένων και API contracts

Ο browser μιλάει μόνο με το δικό μας backend· όλες οι εξωτερικές πηγές περνάνε από backend adapters με cache (για
CORS, rate limits και offline). Δεδομένα χάρτη επιστρέφονται πάντα ως GeoJSON `FeatureCollection` σε WGS84. Τα
endpoints των εξωτερικών πηγών γράφτηκαν χωρίς online έλεγχο, οπότε επιβεβαιώστε τα URLs πριν τα χρησιμοποιήσετε.

### Εξωτερικές πηγές

| Layer | Πηγή | Σημείωση | Fallback |
|---|---|---|---|
| Θερμοκρασία / AQI | Open-Meteo forecast + air-quality API (χωρίς key) σε πλέγμα σημείων του Δήμου· αισθητήρες Δήμου αν υπάρχουν | Heatmap layer με βάρος τη θερμοκρασία ή το AQI | `mock/env.json` |
| Προσβασιμότητα / Ράμπες | OSM μέσω Overpass: `kerb=lowered`, `wheelchair=*`, `ramp=yes`, `tactile_paving=yes` | Προκατέβασμα σε αρχείο, όχι live | `mock/access.geojson` |
| Έργα | Διαύγεια OpenData API (αποφάσεις Δήμου Αθηναίων: αναθέσεις, πληρωμές) + ΚΗΜΔΗΣ OpenData (συμβάσεις, ανάδοχοι, ποσά) | Join με ΑΔΑ / ΑΔΑΜ· geocoding της οδού από το κείμενο (Nominatim ή χειροκίνητο curated σετ για το demo) | `mock/works.geojson` (10–15 αληθινά έργα) |
| Τηλεματική | ΟΑΣΑ telematics API (`getBusLocation`, `getStopArrivals`) | Polling ανά 20s, μόνο για γραμμές στο viewport· smooth κίνηση λεωφορείων με interpolation | Τελευταίο snapshot |
| Μετρό / Προαστιακός | GTFS static ΟΑΣΑ/ΣΤΑΣΥ αν είναι διαθέσιμο, αλλιώς OSM (`route=subway`, `route=train`) | Γραμμές + σταθμοί με τα επίσημα χρώματα γραμμών | `mock/transit.geojson` |
| Εφημερεύοντα φαρμακεία | Φαρμακευτικός Σύλλογος Αττικής (πιθανότατα δεν έχει επίσημο API) | Scraper μία φορά τη μέρα + geocoding διεύθυνσης | `mock/health.geojson` |
| Εφημερεύοντα νοσοκομεία | Ημερήσια ανακοίνωση εφημεριών του Υπουργείου Υγείας | Σταθερές θέσεις νοσοκομείων + σημαία «εφημερεύει σήμερα» ανά ειδικότητα | Ίδιο mock |

### Backend contracts

Οι υπάρχουσες κλήσεις μένουν ίδιες· τα `/transit` και `/health` είναι νέα. Τα σχήματα πιο κάτω είναι αυτά που
περιμένει το frontend.

| Endpoint | Request | Response (βασικά πεδία) |
|---|---|---|
| `GET /env` | `?bbox=minLon,minLat,maxLon,maxLat` | GeoJSON points: `temp_c`, `aqi`, `pm25`, `updated_at` |
| `GET /works` | `?bbox=&status=` | GeoJSON lines/points: `id`, `title`, `status`, `contractor`, `amount_contract_eur`, `amount_paid_eur`, `ada`, `adam`, `start_date`, `end_date`, `guarantee_end`, `reports_count` |
| `POST /routing` | `{from:[lon,lat], to:[lon,lat], profile:"wheelchair"\|"stroller"\|"cool"}` | `{geometry: LineString, distance_m, duration_s, legs:[{mode, line?}], reasons:[{text, layer, feature_id}]}` |
| `GET /points` | `?user_id=` | `{balance, district:{name, progress_pct, goal}, history:[{ts, delta, reason}], rewards:[{id, title, cost}]}` |
| `POST /points/redeem` (νέο, Nice) | `{user_id, reward_id}` | `{ok, balance, voucher_code}` |
| `POST /stoa_ask` | `{question, center:[lon,lat], history:[...]}` | `{answer_md, citations:[{label, lon, lat, kind}]}` |
| `POST /reports` | `multipart`: `category`, `lon`, `lat`, `note`, `work_id?`, `photo?` | `{id, photo_url_blurred, points_awarded, blur:{faces, plates}}` |
| `GET /reports` | `?bbox=&since=` | GeoJSON points: `category`, `created_at`, `confirmations` |
| `GET /transit` (νέο) | `?bbox=` | `{lines: FeatureCollection, stations: FeatureCollection, buses: FeatureCollection}` |
| `GET /health` (νέο) | `?date=` | GeoJSON points: `kind` (φαρμακείο/νοσοκομείο), `name`, `address`, `phone`, `hours`, `specialties` |

Η Stoa AI επιστρέφει τις οδούς ως `citations` με συντεταγμένες. Το frontend αντικαθιστά το `label` μέσα στο
`answer_md` με link που κάνει `flyTo`, οπότε δεν χρειάζεται geocoding στον browser.

### Κανόνες πόντων (πρόταση)

| Ενέργεια | Πόντοι |
|---|---|
| Αναφορά συμβάντος / συμφόρησης | 5 |
| Επιβεβαίωση αναφοράς άλλου | 2 |
| Αναφορά προόδου έργου με φωτογραφία | 15 |
| Αναφορά που επιβεβαιώνει ο Δήμος | +20 bonus |

Η εξαργύρωση γίνεται σε παροχές του Δήμου (π.χ. εισιτήρια σε δημοτικές εκδηλώσεις, θέσεις στάθμευσης, κουπόνια
τοπικών καταστημάτων). Ο κατάλογος των παροχών είναι ανοιχτό ερώτημα προς τον Δήμο. Για anti-abuse: όριο 10
αναφορές τη μέρα και όχι πόντοι για διπλότυπα σε ακτίνα 50 m / 30 λεπτά.

## Αρχιτεκτονική, offline fallback και privacy

Το `citizen.html` μένει το entry point, αλλά η λογική σπάει σε ES modules χωρίς build step. Έτσι οι δύο developers
δουλεύουν σε διαφορετικά αρχεία και δεν έχουν merge conflicts.

```
web/
  citizen.html          # μόνο markup + CDN + <script type="module" src="js/main.js">
  css/
    hud.css             # .glass, pills, drawer, chat, popup, pulse
  js/
    main.js             # bootstrap, συνδέει τα modules
    api.js              # ΜΟΝΗ πόρτα προς backend + fallback σε mock + localStorage cache
    map.js              # init, styles, Light/Dark, 3D buildings, addOverlays(), offline style
    layers/
      env.js  access.js  works.js  transit.js  health.js  reports.js
    ui/
      layerbar.js       # top-center pills
      points.js         # loyalty pill + panel
      report.js         # «+» flow
      stoa.js           # chatbot bubble + flyTo citations
      routing.js        # bottom sheet + animated route
      workpopup.js      # φούσκα έργου
      workstab.js       # tab Έργων (F8)
  mock/
    env.json  access.geojson  works.geojson  transit.geojson  health.geojson  points.json  stoa.json
```

### Offline fallback

1. Αν το style του OpenFreeMap δεν φορτώσει σε 6s ή πέσει `error` από το style/tiles, το `map.js` κάνει
   `setStyle()` σε inline offline style (`version: 8`, μόνο `background` + GeoJSON ορίων Δήμου και κύριων οδών από
   `mock/`).
2. Τα overlays ξαναμπαίνουν μέσω `addOverlays()`, οπότε έργα, αναφορές και διαδρομές συνεχίζουν να φαίνονται.
3. Το `api.js` δοκιμάζει backend → τελευταία απάντηση στο `localStorage` → `mock/`. Κάθε απάντηση έχει σημαία
   `source: live|cache|mock`.
4. Ένα μικρό glass badge «Offline λειτουργία» εμφανίζεται όταν κάποια πηγή δεν είναι `live`.
5. Αναφορές που γίνονται offline μπαίνουν σε ουρά στο `localStorage` και στέλνονται στο `online` event.

Εξασφαλίζει ότι το demo δεν πέφτει αν το Wi-Fi του Σεραφείου δεν δουλέψει: τα mock αρχεία πρέπει να είναι
ρεαλιστικά.

### Privacy (GDPR)

- Το blur προσώπων και πινακίδων γίνεται στο backend πριν αποθηκευτεί οτιδήποτε· το αρχικό δεν γράφεται ποτέ σε
  δίσκο.
- Στο frontend το preview δείχνει τη θολωμένη εκδοχή που επιστρέφει το `/reports` (`photo_url_blurred`).
- Καθαρίζονται τα EXIF (GPS, συσκευή).
- Η δημόσια θέση μιας αναφοράς στρογγυλεύεται σε ~10 m.
- Στο demo ο χρήστης είναι ανώνυμος (`user_id` στο `localStorage`). Στην παραγωγή θα μπει login μέσω δημοτικού
  λογαριασμού ή gov.gr.

## Μοίρασμα δουλειάς

Ο Dev A έχει τον χάρτη και ό,τι ζωγραφίζεται πάνω του· ο Dev B έχει τα δεδομένα, το backend και τα panels που δεν
είναι χάρτης. Το σημείο επαφής τους είναι τα contracts και τα αρχεία `mock/`: ο A δουλεύει πάνω στα mock μέχρι να
βγουν τα live endpoints του B, οπότε κανείς δεν περιμένει τον άλλον.

### Ιδιοκτησία αρχείων

| Dev A — Χάρτης & HUD | Dev B — Δεδομένα & backend |
|---|---|
| `citizen.html`, `css/hud.css`, `js/main.js`, `js/map.js` | `js/api.js`, όλο το `mock/` |
| `js/layers/*.js` (σχεδίαση layers) | Backend adapters: Διαύγεια, ΚΗΜΔΗΣ, ΟΑΣΑ, μετρό/προαστιακός, φαρμακεία/νοσοκομεία, Open-Meteo, Overpass |
| `ui/layerbar.js`, `ui/workpopup.js`, `ui/routing.js` | Νέα endpoints `/transit`, `/health`, `/points/redeem` |
| Offline style, Light/Dark, 3D κτίρια, animations | Κόστος διαδρομής ανά προφίλ στο `/routing` |
| | `ui/report.js` + blur/EXIF στο `/reports`, `ui/points.js`, `ui/stoa.js` (citations), `ui/workstab.js` |

### Φάσεις

| Φάση | Dev A | Dev B | Τέλος φάσης όταν |
|---|---|---|---|
| 0. Κοινή εκκίνηση (~1 ώρα, μαζί) | Σκελετός φακέλων, branches `dev-a` / `dev-b` | Κλείδωμα contracts, πρώτα mock αρχεία | Οι δύο συμφωνούν στα contracts |
| 1. Σκελετός | MapLibre + Liberty/Fiord, 3D, κάμερα, offline style, `.glass` HUD άδειο | `api.js` με live→cache→mock, υπάρχοντα endpoints δουλεύουν μέσω api.js | Χάρτης + HUD φορτώνουν και offline |
| 2. MVP | 6 layers + pill bar, φούσκα έργου, routing drawer + animated route | Adapters Διαύγεια/ΚΗΜΔΗΣ/ΟΑΣΑ/env/health, ροή «+» με blur, points pill + pulse, Stoa με flyTo, κόστος διαδρομής ανά προφίλ | Το demo script τρέχει από την αρχή ως το τέλος |
| 3. Nice | Κινητό layout, highlight των reasons στον χάρτη, λεία κίνηση λεωφορείων | Tab Έργων με crowdsourcing, εξαργύρωση πόντων, offline ουρά αναφορών | Όλα τα κριτήρια αποδοχής τικαρισμένα |
| 4. Freeze (μαζί) | Merge στο `main`, έλεγχος σε κινητό | Δοκιμή με κομμένο internet, τελικά mock | 2 επιτυχημένες πρόβες του demo, καμία αλλαγή μετά |

Αν ο χρόνος σφίξει, τα adapters μένουν σε mock και το demo βασίζεται σε ρεαλιστικά δεδομένα. Τον χάρτη και τη ροή
«+» το κοινό θα τα δει live, οπότε αυτά έχουν προτεραιότητα.

## Κριτήρια αποδοχής, demo και prompt για Claude Code

### Κριτήρια αποδοχής

- [ ] Ο χάρτης ανοίγει full-screen πάνω από το Σύνταγμα σε pitch 55 / bearing −15 με ορατά 3D κτίρια, σε Liberty
      και σε Fiord
- [ ] Το Light/Dark δεν χάνει κανένα overlay ούτε την κατάσταση των toggles
- [ ] Και τα 6 layer chips ανάβουν/σβήνουν το αντίστοιχο layer
- [ ] Κλικ σε έργο δείχνει ανάδοχο, € πληρωμένα, countdown εγγύησης και ΑΔΑ με link στη Διαύγεια
- [ ] Η ροή «+» στέλνει αναφορά, δείχνει θολωμένη φωτογραφία, βάζει pin στον χάρτη και το pill πόντων κάνει pulse
      με «+N»
- [ ] Η διαδρομή ζωγραφίζεται animated και διαφέρει ανά προφίλ
- [ ] Στη Stoa AI, κλικ σε δρόμο από την απάντηση κάνει `flyTo` εκεί
- [ ] Με κομμένο internet (DevTools → Offline) το app ανοίγει, δείχνει mock δεδομένα και το badge «Offline»
- [ ] Καμία υπάρχουσα κλήση (`/routing`, `/env`, `/works`, `/points`, `/stoa_ask`, `/reports`) δεν έσπασε
- [ ] Λειτουργεί σε κινητό (πλάτος 390px) χωρίς επικαλύψεις του HUD

### Demo script (3 λεπτά)

1. Άνοιγμα στο 3D Σύνταγμα, εναλλαγή σε Dark.
2. Ενεργοποίηση Θερμοκρασίας/AQI και Τηλεματικής: λεωφορεία κινούνται.
3. Κλικ σε έργο: φούσκα με ανάδοχο, € και ΑΔΑ → «Ανέφερε πρόοδο» με φωτογραφία, δείχνουμε το blur και τους πόντους
   να ανεβαίνουν.
4. Διαδρομή «Αμαξίδιο» από Σύνταγμα σε Μοναστηράκι που αποφεύγει το έργο, μετά «Δροσερότερη» για σύγκριση.
5. Ερώτηση στη Stoa: «Ποιο φαρμακείο εφημερεύει κοντά μου;» → κλικ στον δρόμο → flyTo.
6. Κλείσιμο με το tab Έργα και το panel εξαργύρωσης πόντων.

### Prompt για Claude Code

Δώστε το έγγραφο (export σε Markdown ως `docs/SPEC.md` στο repo) μαζί με αυτό το prompt. Κάθε dev αλλάζει το
`<A|B>`.

```
Διάβασε το docs/SPEC.md και το υπάρχον web/citizen.html και backend.
Είμαι ο Dev <A|B>. Υλοποίησε ΜΟΝΟ τις δουλειές του Dev <A|B> από την ενότητα
«Μοίρασμα δουλειάς», με τη σειρά των φάσεων.
Κανόνες:
- Μην αλλάξεις τα υπάρχοντα endpoints (/routing, /env, /works, /points,
  /stoa_ask, /reports).
  Αν το σχήμα τους διαφέρει από το SPEC, προσάρμοσε μόνο το web/js/api.js.
- Αγγίζεις μόνο τα αρχεία που ανήκουν στον Dev <A|B>.
- Χωρίς build step: ES modules + CDN (MapLibre GL JS 5.3.0, OpenFreeMap).
- Κάθε δεδομένο έχει mock στο web/mock/ και το app δουλεύει offline.
- Μετά από κάθε φάση: έλεγξε τα αντίστοιχα κριτήρια αποδοχής και κάνε commit
  στο branch dev-<a|b>.
Ξεκίνα δείχνοντάς μου σύντομο πλάνο για τη Φάση 1.
```

---

## Παράρτημα: SPEC ↔ υπάρχον backend

*Not part of the original PDF; added so `api.js` has a starting point.* The spec's short names map onto the real
FastAPI routes in `app/main.py` (all under `/api`). Dev B's `api.js` translates between the two shapes; the existing
routes don't change.

| SPEC | Real route today | Gap `api.js` has to bridge |
|---|---|---|
| `GET /env` | `GET /api/env/geojson?min_lng&min_lat&max_lng&max_lat`; also `/api/heat?lat&lng`, `/api/city/air` | bbox as 4 params; temp/AQI per point comes from `/api/heat` and `/api/city/air` |
| `GET /works` | `GET /api/works/geojson`; `GET /api/works?lat&lng&radius_m`; `GET /api/works/{id}` | no bbox/status filter (filter client-side); field names differ |
| `POST /routing` | `GET /api/navigate?from_lat&from_lng&to_lat&to_lng&profile&shade&air&rest&heat` | GET with lat/lng; `cool` ≈ `heat=true` + `shade=true`; no transit legs yet |
| `GET /points` | `GET /api/points/me` (cookie token), `GET /api/points/districts` | identity is a cookie, not `user_id`; no `rewards[]` yet |
| `POST /points/redeem` | — | new (Dev B, Nice) |
| `POST /stoa_ask` | `POST /api/stoa/ask` `{q}`; also `POST /api/ask` (City questions) | no `citations[{lon,lat}]` yet: needed for `flyTo` |
| `POST /reports` | `POST /api/report` (multipart: `photo` required, `lat`, `lng`, `address`, `note`) | `lon`→`lng`; no `category`/`work_id`; photo required today |
| `GET /reports` | `GET /api/reports`; `GET /api/hazards` | no bbox/since; not GeoJSON |
| `GET /transit` | — | new (Dev B) |
| `GET /health` | **conflict:** `GET /api/health` already exists (server status, used by tests) | the new on-duty pharmacies/hospitals endpoint needs another path, e.g. `/api/onduty` (decision for the owner) |
