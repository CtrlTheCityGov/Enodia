# Pitch: 5–6 minutes, 5 slides

Sunday 22 Nov, 16:30–18:30, in person, own laptop, order by draw. The organizers want three things:
the problem, the solution as a live demo, and the next step after the hackathon.

| Time | Slide | Say |
|---|---|---|
| 0:00–1:00 | **1. Maria** | "Maria is a retiree in Pangrati. It's 40 °C. She needs a cool place, a certificate, and a sidewalk she can actually walk on. Today that's several apps and a phone call, and when she reports a problem she never hears back." |
| 1:00–4:00 | *(live demo)* | See the demo script in SPEC.md. Say "source shown", "face blurred", "a human decides" out loud. |
| 4:00–4:45 | **2. Built on AthensGov** | Architecture diagram. "Search, services, POIs, requests: all the city's API. We added what it's missing: the map and accessible route, photo AI with privacy, and the operator screen. Public AI register." |
| 4:45–5:30 | **3. Money** | "About €0.5M a year saved (€0.29–0.74M). Mostly crew trips that don't happen twice. Pays back in about 6 months." |
| 5:30–6:00 | **4. Next 90 days** | "Pilot in one Municipal Community. We measure duplicate rate, triage time, time to fix, citizen satisfaction. Funded through Greece 2.0 / ESPA digital programmes." |
| backup | **5. Team** | Names, roles, repo link. |

## Judge questions

- **"Isn't this just our sandbox bot?"** No. We use it for answers and reports and add what it lacks: photos with privacy blur, an accessible route that reacts to reports, and the operator screen.
- **"What if the AI picks the wrong category?"** It never dispatches. The operator sees the guess and approves or fixes it. Below 85% confidence it's flagged. Every decision is in the report history.
- **"GDPR?"** Faces blurred and EXIF stripped before storage or any AI call. The original photo is never saved. No login needed to report. Plates aren't blurred yet in the prototype; production adds a plate detector at the same step.
- **"Why not a Greek model?"** The provider is one setting. Production path: an open model on EU cloud; for Greek text, ILSP's Llama-Krikri / Meltemi (the organizers' suggestion). *(Say only what you actually ran.)*
- **"Where do the savings come from?"** Our estimate from 195,000 requests a year, Greek public pay scales and US/European benchmarks. The first numbers we'd verify with DAEM: share of phone requests and duplicate rate.
- **"Who maintains it?"** Open-source parts on city or EU cloud; one developer part-time plus hosting fits the €70–110k/year running cost.
- **"Why should we believe it scales?"** Same API for all 7 Municipal Communities; nothing is hard-coded to Pangrati except the demo seed.
