"""Savings model behind docs/PROPOSAL.pdf section 6. Run: python docs/economics_model.py
All inputs are assumptions or sourced figures listed in the proposal; confirm with DAEM before quoting."""
# AthensOne savings model (EUR/year at full adoption). low / base / high
S = {}
# 1. Service desk: triage, duplicates, calls -> app (team's SAVINGS.md model, 195k requests/yr)
S["Αναφορές & εξυπηρέτηση"] = (286_000, 491_000, 735_000)
# 2. Stoa guarantee recovery: street works value under guarantee/yr x defect repairs during guarantee x share paid by city today
works = (10e6, 15e6, 25e6); defect = (0.01, 0.02, 0.03); share = (0.3, 0.5, 0.7)
lookups = (1000, 2000, 3000)  # 'who built this?' lookups/yr, 1 h saved each at EUR 17/h
S["Stoa: εγγυήσεις έργων"] = tuple(round(w*d*s + l*17) for w,d,s,l in zip(works,defect,share,lookups))
# 3. Loyalty-driven recycling/organics: extra diverted tonnes x landfill tax EUR 45/t (2026), conservative (no EDSNA fee)
total_t = 850*365
div = (0.005, 0.015, 0.03)
S["Ανακύκλωση μέσω Πόντων"] = tuple(round(total_t*x*45) for x in div)
# 4. Give & Share: bulky items reused instead of collected (~1,000 items/day), EUR per item handled
items = 1000*365; reuse=(0.01,0.03,0.05); per=(15,20,25)
S["Give & Share (ογκώδη)"] = tuple(round(items*r*p) for r,p in zip(reuse,per))
for k,v in S.items(): print(f"{k:28s}", v)
tot = tuple(sum(v[i] for v in S.values()) for i in range(3)); print("TOTAL", tot)
# costs
build = {"low":350_000,"base":500_000,"high":700_000}
run   = {"low":150_000,"base":200_000,"high":260_000}
loyal = {"low":50_000,"base":80_000,"high":120_000}
ramp = [0.4,0.75,1,1,1]  # years 1-5 share of full savings
scen = {"Βασικό": (1,"base","base"), "Απαισιόδοξο": (0,"high","high"), "Αισιόδοξο": (2,"low","low")}
r=0.04
for name,(si,bc,rc) in scen.items():
    cum=-build[bc]; npv=-build[bc]; rows=[("Έτος 0",cum)]; pay=None
    for y,f in enumerate(ramp,1):
        net = tot[si]*f - run[rc] - loyal[rc]
        prev=cum; cum+=net; npv+=net/(1+r)**y; rows.append((f"Έτος {y}",round(cum)))
        if pay is None and cum>=0 and net>0: pay = y-1 + (-prev)/net
    print(name, "annual net full", tot[si]-run[rc]-loyal[rc], "NPV5", round(npv), "payback yrs", None if pay is None else round(pay,1))
    print("  ", rows)
