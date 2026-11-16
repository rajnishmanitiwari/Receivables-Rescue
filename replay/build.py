import json, sys
sys.path.insert(0, "../backend")
from datetime import date, timedelta
from followup_planner import *
D0 = date(2026, 11, 1)
def d(n): return D0 + timedelta(days=n)
INV = {
 "A": (Invoice("INV-1042", 48000, d(-12)), "Northwind Studio", [
     Event(d(2), "sent", tier="firm"), Event(d(9), "reply", Label.PROMISE, promise_date=d(14)), ]),
 "B": (Invoice("INV-1043", 125000, d(-40)), "Harbor Labs", [
     Event(d(1), "sent", tier="escalation"), Event(d(6), "reply", Label.DISPUTE)]),
 "C": (Invoice("INV-1051", 22000, d(-3)), "Kite Foods", [
     Event(d(4), "reply", Label.PAID), Event(d(12), "payment", amount=22000.0)]),
 "D": (Invoice("INV-1060", 9000, d(-20)), "Mosaic Print", [
     Event(d(3), "sent", tier="firm"), Event(d(8), "reply", Label.UNKNOWN)]),
}
text = {"A":{9:"We will pay by the 15th."}, "B":{6:"The amount is wrong, we dispute this."}, "C":{4:"We already paid this."}, "D":{8:"ok thanks"}}
out = {"days": [], "invoices": []}
for k,(inv,cust,evs) in INV.items():
    rows=[]
    for n in range(0, 21):
        a = next_action(inv, evs, d(n))
        rows.append({"kind":a.kind.value,"reason":a.reason,"tier":a.tier,"until":a.until.isoformat() if a.until else None})
    out["invoices"].append({"no":inv.number,"customer":cust,"amount":inv.amount,"due":inv.due.isoformat(),
      "events":[{"n":(e.day-D0).days,"type":e.type,"label":e.label.value if e.label else None,"tier":e.tier,"amount":e.amount,"text":text[k].get((e.day-D0).days)} for e in evs],
      "plan":rows})
out["days"]=[d(n).isoformat() for n in range(21)]
html = open("template.html").read().replace("__DATA__", json.dumps(out))
open("index.html","w").write(html)
print("ok")
