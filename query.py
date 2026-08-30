"""Ask the store a question. Retrieval by entity mention; every answer cites file + row. No rows, no answer.
Run: python query.py "what year is RJ43DD3546"
"""
import re, sys
from common import db, canon_vehicle, canon_client


def retrieve(q):
    con = db()
    hits = []
    plates = {canon_vehicle(m) for m in re.findall(r"[A-Za-z]{2}[ -]?\d{2}[ -]?[A-Za-z]{1,2}[ -]?\d{4}", q)} - {None}
    for c in sorted(plates):
        for r in con.execute("select * from vehicles where canon=?", (c,)):
            hits.append((f"fleet_master.csv ({r['vehicle_id']})", f"{c}: {r['model']} {r['year']} {r['bs_stage']} heater={r['engine_heater']} home={r['home_hub']} status={r['status']} last_service={r['last_service_date']}"))
        for r in con.execute("select * from facts where entity=? order by key, won desc", (c,)):
            tag = "WINS" if r["won"] else f"overridden by {r['vs_source']}={r['vs_value']}"
            hits.append((r["ref"], f"{c} {r['key']}={r['value']} [{r['source']}, {tag}]"))
        for r in con.execute("select m.*, group_concat(e.kind) kinds from maintenance m left join maint_events e on e.maint_row=m.row where vehicle_canon=? group by m.row order by date desc limit 8", (c,)):
            hits.append((f"maintenance_log.xlsx row {r['row']}", f"{r['date']} {r['mechanic']}: {r['notes']} [{r['kinds']}]"))
    for d in sorted(set(re.findall(r"DRV-\d{3}", q.upper()))):
        for r in con.execute("select * from drivers where driver_id=?", (d,)):
            hits.append(("drivers_roster.csv", f"{d} {r['name']} joined {r['joining_date']} home={r['home_hub']} phone={r['phone']}"))
    client = canon_client(next((w for w in ["shakti", "vertex", "apex", "orion"] if w in q.lower()), None))
    if client:
        for r in con.execute("select thread, idx, date, subject, body from emails where lower(body) like ? or lower(subject) like ? order by thread, idx limit 6", (f"%{client.split()[0].lower()}%",) * 2):
            hits.append((f"emails/{r['thread']} msg {r['idx']} ({r['date']})", f"{r['subject']}: {r['body'][:200]}"))
    words = [w for w in re.findall(r"[a-z]{5,}", q.lower()) if w not in {"which", "about", "there", "vehicle", "truck"}]
    for w in words[:3]:
        for r in con.execute("select section, text from transcript where lower(text) like ? limit 2", (f"%{w}%",)):
            hits.append((f"dispatcher_interview.txt section {r['section']}", r["text"][:240].replace("\n", " ")))
    return hits


def answer(q):
    hits = retrieve(q)
    if not hits:
        return "insufficient data"
    return "\n".join(f"- {text}\n    source: {ref}" for ref, text in hits)


if __name__ == "__main__":
    print(answer(" ".join(sys.argv[1:])))
