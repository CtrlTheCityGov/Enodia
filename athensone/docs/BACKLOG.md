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
