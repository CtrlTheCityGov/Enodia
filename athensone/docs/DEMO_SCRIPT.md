# Demo script (about 3 minutes of the 5–6)

**Setup (5 min before):** server running in real mode · `python seed.py --reset --ramp <lat,lng>` ·
citizen page on the demo phone (via ngrok/cloudflared for HTTPS), operator page on the laptop ·
a blocked-ramp photo with a teammate's face in it (with their OK) saved on the phone, in case the camera fails ·
phone hotspot ready · backup video open in another tab.

| Time | Who | Do | Say |
|---|---|---|---|
| 0:00 | Phone | Tap **Aa Μεγάλα** (big mode) | "Maria is a retiree in Pangrati. Big buttons, and the app talks back." |
| 0:10 | Phone | Tap 🎤, say: «Πού να πάω να δροσιστώ; Και τι χρειάζομαι για βεβαίωση μόνιμης κατοικίας;» | "She just asks, in Greek." |
| 0:25 | Phone | Point at the answer and the source chips | "**Every answer shows its official source.** No source, no answer." |
| 0:40 | Phone | Map shows the Friendship Club + blue route, alternatives dashed, the sentence under it | "Not the shortest route, the best one *for her*: step-free, 100% shade instead of 24%, away from the avenue, a bench every 90 m. One extra minute. And it tells her why." |
| 0:55 | Phone | Untick 🌳 Σκιά → route switches to the fastest | "Her choice, not ours." |
| 1:00 | Phone | Note: «μηχανάκι πάνω στη ράμπα», tap 📷, pick the ramp photo | "A neighbour sees a motorbike blocking the ramp on her route." |
| 1:15 | Phone | Blurred photo appears | "**The face is blurred before anything is stored or sent to the AI.**" |
| 1:30 | Phone | Result text + route redraws, ⚠️ on the map | "The AI says: sidewalk, severity 4, blocks wheelchairs. It checked the city's API for duplicates. And Maria's route already goes around it." |
| 1:50 | Laptop | Operator list: new report on top, "2 nearby reports" badge | "On the Municipality's side: the report, the photo, the AI's suggestion, and the bin 30 m away, so one trip fixes both." |
| 2:15 | Laptop | Edit the draft reply a little, click **Έγκριση & αποστολή συνεργείου** | "**The AI never sends a crew. A person decides.**" |
| 2:35 | Phone | Toast «Το συνεργείο ξεκίνησε» + timeline | "And Maria sees it. That's the loop that's missing today: 'I reported it and never heard back.'" |
| 2:50 | Laptop | Click the **σπασμένο πεζοδρόμιο** report → Stoa card | "One more thing. This sidewalk was relaid last year. Stoa read the City's own decisions on Diavgeia: **possibly still under the contractor's guarantee**, here is the sentence it came from." |
| 3:10 | Laptop | Click **Προσχέδιο φακέλου προς ανάδοχο** | "So instead of paying a crew, the engineer gets a cited draft to the contractor. **She reviews and signs; nothing is sent automatically.**" |
| 3:25 | Phone | Toggle **Έργα & εγγυήσεις** layer | "Same map for everyone: reports, cool places, public works. Parking, waste and events are next. They need City data, so we don't fake them." |
| 3:40 | — | — | "All of it runs on the AthensGov API and Diavgeia, open-source, with a public AI register." |

**Stoa data:** if `data/stoa/works.json` (real) isn't ready, the banner says SEED: say "demo records" out loud and give no € figure.

**If something fails:** voice → type the question · camera → pick the saved photo · Valhalla →
the app shows a straight-line fallback and says so · Wi-Fi → hotspot · everything → play the video.

**Optional duplicate moment:** seed with `--with-duplicate`, then the live photo returns
"already reported nearby, we added your vote" instead of a new report.
