"""FastAPI over the store. Every endpoint is a query; state changes go through pipeline/approve. Serves ui/dist."""
import json, shutil
from datetime import datetime, timezone
from pathlib import Path
from fastapi import FastAPI, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import yaml
from common import ROOT, WORK, OUT, AUDIT, db, mask, has_pii
import pipeline, approve as approve_mod, rerun_check, pii_scan, query as query_mod

app = FastAPI(title="Meridian Ops")
RULES = {r["id"]: r for r in yaml.safe_load(open(ROOT / "rules.yaml"))["rules"]}
H = pipeline.H


def rows(sql, *args):
    con = db(); con.executescript(pipeline.PIPE_SCHEMA)
    return [dict(r) for r in con.execute(sql, args)]


def meta(key):
    r = rows("select value from meta where key=?", key) if rows("select 1 from sqlite_master where name='meta'") else []
    return json.loads(r[0]["value"]) if r else None


def chips(rule_ids):
    return [{"id": r, "label": f"{r}: {RULES[r]['short']}"} for r in rule_ids if r in RULES]


def breakdown(w, t, c):
    point = pipeline.breakdown_point(t["origin_hub"], t["destination"], t["km_from_origin_hub"])
    status = "Quarantined" if not w else ("Resolved" if c and c["status"] == "sent" else ("Awaiting approval" if c else "Resolved"))
    return {"ticket_id": t["ticket_id"], "severity": w["severity"] if w else "HIGH", "status": status, "at": t["created_at"], "client": t["client"],
            "summary": f"Truck {t['vehicle_original']} broke down {int(t['km_from_origin_hub'])} km from {t['origin_hub']}, {t['issue']}",
            "replacement_line": f"Replacement {w['replacement']} dispatched from {w['replacement_hub']} hub" if w and w["replacement"] else "No eligible replacement found, needs a manual decision",
            "point": point, "hub": H.get(w["replacement_hub"]) if w and w["replacement_hub"] else None, "replacement_hub": w["replacement_hub"] if w else None,
            "rules": chips([r for r in (w["rules_applied"] or "").split(",") if r]) if w else [], "flags": json.loads(w["flags"]) if w else []}


@app.get("/api/stats")
def stats():
    pending = rows("select count(*) n from comms where status='pending'")[0]["n"]
    attention = rows("select count(*) n from quarantine where resubmitted=0")[0]["n"] + rows("select count(*) n from alerts")[0]["n"]
    return {"active": pending, "awaiting": pending, "attention": attention, "fleet": rows("select count(*) n from vehicles where status='Active'")[0]["n"], "rerun": meta("last_rerun_check")}


@app.get("/api/breakdowns")
def breakdowns():
    out = [breakdown(w, t, (rows("select * from comms where ticket_id=?", t["ticket_id"]) or [None])[0])
           for w in rows("select * from work_orders") for t in rows("select * from tickets where ticket_id=?", w["ticket_id"])]
    return {"items": sorted(out, key=lambda b: b["at"], reverse=True), "hubs": {k: v for k, v in H.items()}}


@app.get("/api/approvals")
def approvals():
    items = []
    for c in rows("select c.*, t.vehicle_original, t.origin_hub, t.destination, t.issue, t.created_at, t.client from comms c join tickets t using(ticket_id) order by t.created_at desc"):
        ctx = json.loads(c["context"])
        items.append({"ticket_id": c["ticket_id"], "client": c["client"], "status": c["status"], "recipient": c["recipient"], "body": c["edited_body"] or c["body"], "drafted_by": c["drafted_by"],
                      "summary": f"{c['issue']} on {c['vehicle_original']}, {c['origin_hub']} to {c['destination']}", "why": ctx["why"], "rules": chips(ctx["rules"]), "flags": ctx.get("flags", []),
                      "based_on": json.loads(c["citations"]), "at": c["created_at"], "approved_by": c["approved_by"], "sent_at": c["sent_at"], "vehicle": c["vehicle_original"]})
    return {"pending": [i for i in items if i["status"] == "pending"], "sent": [i for i in items if i["status"] == "sent"]}


class Approve(BaseModel):
    ticket_id: str
    by: str
    body: str | None = None


@app.post("/api/approve")
def do_approve(a: Approve):
    return approve_mod.approve(a.ticket_id, a.by, a.body)


@app.get("/api/attention")
def attention():
    q = [{"ticket_id": r["ticket_id"], "reason": r["reason"], "detail": r["detail"], "record": json.loads(r["record"]), "source_file": r["source_file"],
          "missing": [f for f in pipeline.REQUIRED if not str(json.loads(r["record"]).get(f) or "").strip()] or ["vehicle"]}
         for r in rows("select * from quarantine where resubmitted=0 order by ticket_id")]
    return {"quarantined": q, "alerts": rows("select * from alerts order by key")}


class Resubmit(BaseModel):
    ticket_id: str
    fields: dict


@app.post("/api/resubmit")
def resubmit(r: Resubmit):
    con = db(); con.executescript(pipeline.PIPE_SCHEMA)
    qs = [dict(x) for x in con.execute("select * from quarantine where ticket_id=? and resubmitted=0", (r.ticket_id,))]
    if not qs:
        return {"result": "not_found"}
    rec = json.loads(qs[0]["record"]) | {k: mask(str(v)) for k, v in r.fields.items()}
    rec.pop("_unmapped", None)
    with con:
        pipeline.process(con, rec, qs[0]["source_file"] + " (resubmitted)", set())
        done = con.execute("select 1 from work_orders where ticket_id=?", (r.ticket_id,)).fetchone()
        if done:
            con.execute("update quarantine set resubmitted=1 where ticket_id=?", (r.ticket_id,))
            pipeline.audit(con, r.ticket_id, 0, "Resubmitted", rec.get("created_at", "n/a"), f"dispatcher supplied {', '.join(r.fields)}", {"fields": list(r.fields)}, by="human")
    pipeline.write_outputs(con)
    return {"result": "processed" if done else "still_quarantined", "quarantine": [dict(x) for x in con.execute("select reason, detail from quarantine where ticket_id=? and resubmitted=0", (r.ticket_id,))]}


@app.get("/api/history/{ticket_id}")
def history(ticket_id: str):
    steps = [{"seq": a["seq"], "step": a["step"], "at": a["at"], "decision": a["decision"], "by": a["by"], "rules": chips(a["rule_ids"].split(",") if a["rule_ids"] else []),
              "sources": json.loads(a["data"]).get("citations") or ([json.loads(a["data"])["source"]] if json.loads(a["data"]).get("source") else []), "data": json.loads(a["data"])}
             for a in rows("select * from audit where ticket_id=? order by seq, step", ticket_id)]
    return {"ticket_id": ticket_id, "steps": steps, "rerun": meta("last_rerun_check")}


class Run(BaseModel):
    file: str | None = None


@app.post("/api/run")
def run(r: Run):
    return pipeline.run(r.file or str(ROOT / "candidate_bundle" / "tickets.json"))


@app.post("/api/upload")
async def upload(file: UploadFile):
    dest = WORK / "uploads" / Path(file.filename).name
    dest.parent.mkdir(exist_ok=True)
    dest.write_bytes(await file.read())
    return pipeline.run(str(dest))


@app.post("/api/rerun-check")
def do_rerun():
    return rerun_check.check(str(ROOT / "candidate_bundle" / "tickets.json"))


class Scan(BaseModel):
    plant: bool = False


@app.post("/api/pii-scan")
def do_scan(s: Scan):
    if s.plant:  # test mode: copy outputs to scratch, plant a fake number, prove the scanner bites
        scratch = WORK / "scratch_pii"
        shutil.rmtree(scratch, ignore_errors=True); shutil.copytree(OUT, scratch)
        (scratch / "planted.jsonl").write_text('{"body": "driver on +91 98765 43210, aadhaar 1234 5678 9012"}\n')
        hits = pii_scan.scan([scratch]); shutil.rmtree(scratch)
        return {"mode": "planted", "leaks": len(hits), "hits": [{"kind": h["kind"], "file": Path(h["file"]).name, "line": h["line"]} for h in hits]}
    hits = pii_scan.scan([p for p in (OUT, AUDIT, WORK / "logs") if p.exists()])
    return {"mode": "live", "leaks": len(hits), "hits": hits, "scanned": ["outputs/", "audit/", "logs/"]}


@app.get("/api/precedence")
def precedence():
    return {"order": ["fleet_master", "maintenance_log", "tickets", "emails", "transcript"],
            "conflicts": rows("select entity, key, value, source, ref, vs_source, vs_value from facts where won=0 and source!=vs_source order by entity, key"),
            "same_source_duplicates": rows("select entity, key, value, ref, vs_value from facts where won=0 and source=vs_source order by entity")}


@app.get("/api/rules")
def rules():
    return list(RULES.values())


@app.get("/api/query")
def q(q: str):
    return {"question": q, "answer": query_mod.answer(q)}


@app.get("/api/random-ticket")
def random_ticket():
    import hashlib
    ids = [r["ticket_id"] for r in rows("select ticket_id from work_orders order by ticket_id")]
    pick = ids[int(hashlib.sha256(datetime.now(timezone.utc).isoformat(timespec='seconds').encode()).hexdigest(), 16) % len(ids)] if ids else None
    return history(pick) if pick else {"steps": []}


DIST = ROOT / "ui" / "dist"
if DIST.exists():
    app.mount("/assets", StaticFiles(directory=DIST / "assets"), name="assets")

    @app.get("/{path:path}")
    def spa(path: str):
        f = DIST / path
        return FileResponse(f if f.is_file() else DIST / "index.html")
