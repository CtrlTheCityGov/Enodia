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
