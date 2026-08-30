"""Plain-English decision story for one ticket. Run: python why.py TKT-0009"""
import json, sys
from common import AUDIT


def story(ticket_id):
    rows = sorted((json.loads(l) for l in open(AUDIT / "audit.jsonl", encoding="utf-8") if f'"ticket_id": "{ticket_id}"' in l), key=lambda r: r["seq"])
    if not rows:
        return f"No audit trail for {ticket_id}. Not processed, or the id is wrong."
    out = [f"{ticket_id}: what happened and why", ""]
    for r in rows:
        out.append(f"{r['seq']}. {r['step']} ({r['at']}, by {r['by']}" + (f", rules {', '.join(r['rule_ids'])}" if r["rule_ids"] else "") + ")")
        out.append(f"   {r['decision']}")
        d = r["data"]
        if r["step"] == "Enriched":
            v = d.get("vehicle")
            if v:
                out.append(f"   Vehicle: {v['model']} {v['year']} {v['bs_stage']}, heater {v['engine_heater']}, home {v['home_hub']}, last service {v['last_service_date']}")
            for m in d.get("maintenance", [])[:3]:
                out.append(f"   Maintenance {m['date']}: {m['notes']} [{m['kinds']}]")
        if r["step"] == "Truck selected":
            for s in d.get("skipped", []):
                out.append(f"   Skipped {s['vehicle']} at {s['hub']}: {s['rule']}, {s['why']}")
        if d.get("citations"):
            out.append("   Based on: " + " · ".join(d["citations"]))
    return "\n".join(out)


if __name__ == "__main__":
    print(story(sys.argv[1]))
