# Business model canvas: AthensOne AI

| Block | Content |
|---|---|
| **Customer segments** | Payer: Municipality of Athens / DAEM S.A. Users: residents (priority: older people, people with disabilities, parents with strollers), visitors, municipal staff handling requests. |
| **Value proposition** | Residents: one place to ask, report and see progress; step-free routes that avoid reported obstacles. City: fewer duplicate crew trips, faster triage, fewer phone calls, visible trust (sources, privacy, human decision). |
| **Channels** | Web app (PWA) linked from AthensGov / cityofathens.gr; QR codes at Friendship Clubs, ΚΑΠΗ, KEP; later inside existing municipal apps. |
| **Customer relationships** | Free for citizens, no login to report. Status updates until the problem is fixed. Public AI register and feedback via 1595. |
| **Revenue streams / funding** | Not sold to citizens. Funded by the Municipality's digital budget and co-financing: Greece 2.0 (Smart Cities & Digital Transformation), ESPA 2021–2027 digital-governance actions, EU Digital Europe / climate-resilience calls. Later: other Greek municipalities reuse the open-source modules (paid setup and support). |
| **Key resources** | AthensGov APIs and open data, open-source stack (FastAPI, OpenStreetMap, Valhalla, OpenCV, MapLibre), Greek-capable AI model, team know-how. |
| **Key activities** | Integration with AthensGov/Novoville/1595, accessibility design (WCAG), privacy reviews, model evaluation in Greek, operator training. |
| **Key partners** | DAEM S.A., Municipality directorates (cleaning, technical works, social services), Crowdpolicy, ILSP (Greek models), disability and older-people associations, OpenStreetMap Greece community. |
| **Cost structure** | Build: ~€150–280k (integration, UX, Greek AI tuning). Run: ~€70–110k/year (EU hosting, AI inference, security audit, maintenance). No licence fees. |
| **Impact (social sustainability)** | ~€0.5M/year estimated direct savings; heat protection for vulnerable residents; accessible city; closed feedback loop. KPIs for the 90-day pilot: duplicate rate, mean triage time, time to fix, citizen satisfaction, accessibility reports resolved. |
