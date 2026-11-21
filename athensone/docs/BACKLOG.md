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
