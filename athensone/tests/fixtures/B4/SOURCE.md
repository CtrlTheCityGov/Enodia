# B4 fixtures (real responses, saved 2026-11-21)

- `pharmacies.html`: `POST https://fsa-efimeries.gr/Home/FilteredHomeResults` with `Date=2026-11-21&IsOpen=false`
  (HTTP 200, text/html, 78 on-duty pharmacy cards for Attica; public business listings).
- `hospitals.txt`: plain text extracted by `app.onduty_src._extract_doc_text()` from the Ministry of Health Attica
  announcement for Saturday 21 Nov 2026 (`.../68-efhmeries-nosokomeiwn-attikhs?fdl=32105`, HTTP 200,
  application/msword, 138 752 bytes). This is what `fetch_hospitals_announcement()` returns.
