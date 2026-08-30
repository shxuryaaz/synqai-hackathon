"""FastAPI over the store. Every endpoint is a query; state changes go through pipeline/approve. Serves ui/dist."""
import json, os, shutil
from datetime import datetime, timezone
from pathlib import Path
from fastapi import FastAPI, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import yaml
from common import ROOT, WORK, OUT, AUDIT, atomic_write_jsonl, db, mask, mask_data, has_pii, pretty_plate
import jwt
import pipeline, approve as approve_mod, rerun_check, pii_scan, query as query_mod, persist

app = FastAPI(title="Meridian Ops")
RULES = {r["id"]: r for r in yaml.safe_load(open(ROOT / "rules.yaml"))["rules"]}
H = pipeline.H
SUPABASE_URL = os.environ.get("SUPABASE_URL")   # unset locally and in tests: no auth, no snapshots
JWKS = jwt.PyJWKClient(f"{SUPABASE_URL}/auth/v1/.well-known/jwks.json") if SUPABASE_URL else None


@app.middleware("http")
async def guard(request, call_next):
    """Every /api call needs a Supabase session when deployed; every successful write is snapshotted to Neon."""
    path = request.url.path
    if JWKS and path.startswith("/api/") and path != "/api/config":
        try:
            token = request.headers.get("authorization", "").split(" ", 1)[1]
            jwt.decode(token, JWKS.get_signing_key_from_jwt(token).key, algorithms=["ES256"], audience="authenticated")
        except Exception:
            return JSONResponse({"detail": "Sign in required"}, status_code=401)
    response = await call_next(request)
    if request.method == "POST" and path.startswith("/api/") and response.status_code < 300:
        persist.save_later()
    return response


@app.get("/api/config")
def config():
    return {"supabase_url": SUPABASE_URL, "supabase_anon_key": os.environ.get("SUPABASE_ANON_KEY")}


def rows(sql, *args):
    con = db(); con.executescript(pipeline.PIPE_SCHEMA)
    return [mask_data(dict(r)) for r in con.execute(sql, args)]


def meta(key):
    r = rows("select value from meta where key=?", key) if rows("select 1 from sqlite_master where name='meta'") else []
    return json.loads(r[0]["value"]) if r else None


def chips(rule_ids):
    return [{"id": r, "label": f"{r}: {RULES[r]['short']}"} for r in rule_ids if r in RULES]


def breakdown(w, t, c):
    point = pipeline.breakdown_point(t["origin_hub"], t["destination"], t["km_from_origin_hub"])
    status = "Quarantined" if not w else ("Resolved" if c and c["status"] == "sent" else ("Awaiting approval" if c else "Resolved"))
    return {"ticket_id": t["ticket_id"], "severity": w["severity"] if w else "HIGH", "status": status, "at": t["created_at"], "client": t["client"],
            "summary": f"Truck {pretty_plate(t['vehicle_canon'])} broke down {int(t['km_from_origin_hub'])} km from {t['origin_hub']}, {t['issue']}",
            "replacement_line": f"Replacement {pretty_plate(w['replacement'])} dispatched from {w['replacement_hub']} hub" if w and w["replacement"] else "No eligible replacement found, needs a manual decision",
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
    for c in rows("select c.*, t.vehicle_canon, t.origin_hub, t.destination, t.issue, t.created_at, t.client from comms c join tickets t using(ticket_id) order by t.created_at desc"):
        ctx = json.loads(c["context"])
        items.append({"ticket_id": c["ticket_id"], "client": c["client"], "status": c["status"], "recipient": c["recipient"], "body": c["edited_body"] or c["body"], "drafted_by": c["drafted_by"],
                      "summary": f"{c['issue']} on {pretty_plate(c['vehicle_canon'])}, {c['origin_hub']} to {c['destination']}", "why": ctx["why"], "rules": chips(ctx["rules"]), "flags": ctx.get("flags", []),
                      "based_on": json.loads(c["citations"]), "at": c["created_at"], "approved_by": c["approved_by"], "sent_at": c["sent_at"], "vehicle": pretty_plate(c["vehicle_canon"])})
    return {"pending": [i for i in items if i["status"] == "pending"], "sent": [i for i in items if i["status"] == "sent"]}


class Approve(BaseModel):
    ticket_id: str
    by: str
    body: str | None = None


@app.post("/api/approve")
def do_approve(a: Approve):
    try:
        return approve_mod.approve(a.ticket_id, a.by, a.body)
    except approve_mod.ApprovalConflict as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    except approve_mod.ApprovalValidationError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


def missing_fields(rec):
    """Every field the dispatcher must supply before this record can pass validation."""
    from common import canon_vehicle
    out = [f for f in pipeline.REQUIRED if not str(rec.get(f) or "").strip()]
    if "vehicle" not in out and not canon_vehicle(rec.get("vehicle")):
        out.append("vehicle")
    if "created_at" not in out and not pipeline.parse_date(rec.get("created_at")):
        out.append("created_at")
    if rec.get("origin_hub") and rec["origin_hub"] not in H and "origin_hub" not in out:
        out.append("origin_hub")
    return out or ["vehicle"]


@app.get("/api/attention")
def attention():
    q = [{"ticket_id": r["ticket_id"], "reason": r["reason"], "detail": r["detail"], "record": json.loads(r["record"]), "source_file": r["source_file"],
          "missing": missing_fields(json.loads(r["record"]))}
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
    rec = json.loads(qs[0]["record"]) | mask_data(r.fields)
    rec.pop("_unmapped", None)
    with con:
        pipeline.process(con, rec, qs[0]["source_file"] + " (resubmitted)", set(), [])
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


@app.post("/api/run")
def run():
    return pipeline.run(str(ROOT / "candidate_bundle" / "tickets.json"))


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
        atomic_write_jsonl(scratch / "planted.jsonl", [{"body": "driver on +91 98765 43210, aadhaar 1234 5678 9012"}], sanitize=False)
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
    return mask_data({"question": q, "answer": query_mod.answer(mask(q))})


@app.get("/api/random-ticket")
def random_ticket():
    import hashlib
    ids = [r["ticket_id"] for r in rows("select ticket_id from work_orders order by ticket_id")]
    pick = ids[int(hashlib.sha256(datetime.now(timezone.utc).isoformat(timespec='seconds').encode()).hexdigest(), 16) % len(ids)] if ids else None
    return history(pick) if pick else {"steps": []}


# ---- knowledge graph ------------------------------------------------------------------------------
@app.get("/api/graph/{ticket_id}")
def ticket_graph(ticket_id: str):
    t = (rows("select * from tickets where ticket_id=?", ticket_id) or [None])[0]
    if not t:
        return {"nodes": [], "edges": []}
    w = (rows("select * from work_orders where ticket_id=?", ticket_id) or [None])[0]
    nodes, edges = [{"id": ticket_id, "kind": "ticket", "label": f"{ticket_id}\n{t['issue']}"}], []
    add = lambda i, k, l: nodes.append({"id": i, "kind": k, "label": l})
    v = t["vehicle_canon"]; veh = (rows("select * from vehicles where canon=?", v) or [None])[0]
    add(v, "vehicle", f"{pretty_plate(v)}\n{veh['model'] + ' ' + str(veh['year']) + ' ' + veh['bs_stage'] if veh else 'not in fleet master'}"); edges.append([ticket_id, v, "broke down"])
    if t["driver_id"]:
        d = (rows("select * from drivers where driver_id=?", t["driver_id"]) or [None])[0]
        add(t["driver_id"], "driver", f"{t['driver_id']}\n{'joined ' + d['joining_date'] if d else 'unknown'}"); edges.append([ticket_id, t["driver_id"], "driven by"])
    add(t["client"], "client", t["client"]); edges.append([ticket_id, t["client"], "consignment for"])
    add(t["origin_hub"], "hub", f"{t['origin_hub']} hub"); edges.append([ticket_id, t["origin_hub"], f"{int(t['km_from_origin_hub'])} km from"])
    for m in rows("select m.date, m.row, group_concat(e.kind) kinds from maintenance m join maint_events e on e.maint_row=m.row where vehicle_canon=? and date<=? and kind in ('brake_work','jugaad','permanent_fix_pending') group by m.row order by date desc limit 4", v, t["created_at"]):
        add(f"m{m['row']}", "maintenance", f"{m['date']}\n{m['kinds'].replace('_', ' ')}"); edges.append([v, f"m{m['row']}", "log row " + str(m["row"])])
    if w:
        if w["replacement"]:
            add(w["replacement"], "vehicle", f"{pretty_plate(w['replacement'])}\nreplacement"); edges.append([ticket_id, w["replacement"], f"replaced from {w['replacement_hub']}"])
        for r in [r for r in (w["rules_applied"] or "").split(",") if r]:
            add(r, "rule", f"{r}\n{RULES[r]['short']}"); edges.append([r, ticket_id, "applied"])
        for s in json.loads(w["skipped"])[:6]:
            add(s["vehicle"], "skipped", f"{pretty_plate(s['vehicle'])}\nskipped"); edges.append([s["rule"] if s["rule"] in RULES else ticket_id, s["vehicle"], s["why"][:40]])
    seen, uniq = set(), []
    for n in nodes:
        if n["id"] not in seen:
            seen.add(n["id"]); uniq.append(n)
    return {"nodes": uniq, "edges": [{"from": a, "to": b, "label": l} for a, b, l in edges]}


@app.get("/api/graph")
def global_graph():
    nodes, edges = [], []
    for c in rows("select client, count(*) n from tickets group by client"):
        nodes.append({"id": c["client"], "kind": "client", "label": f"{c['client']}\n{c['n']} tickets"})
    for h in rows("select origin_hub, count(*) n from tickets group by origin_hub"):
        nodes.append({"id": h["origin_hub"], "kind": "hub", "label": f"{h['origin_hub']} hub\n{h['n']} breakdowns"})
    for e in rows("select client, origin_hub, count(*) n from tickets group by client, origin_hub"):
        edges.append({"from": e["client"], "to": e["origin_hub"], "label": f"{e['n']}"})
    for r in rows("select w.replacement_hub, w.rules_applied from work_orders w where replacement_hub is not null"):
        for rid in [x for x in (r["rules_applied"] or "").split(",") if x in RULES]:
            if not any(n["id"] == rid for n in nodes):
                nodes.append({"id": rid, "kind": "rule", "label": f"{rid}\n{RULES[rid]['short']}"})
            if not any(e["from"] == rid and e["to"] == r["replacement_hub"] for e in edges):
                edges.append({"from": rid, "to": r["replacement_hub"], "label": ""})
    return {"nodes": nodes, "edges": edges}


# Must stay last: catch-all for the SPA.
DIST = (ROOT / "ui" / "dist").resolve()
if DIST.exists():
    app.mount("/assets", StaticFiles(directory=DIST / "assets"), name="assets")

    @app.get("/{path:path}")
    def spa(path: str):
        f = (DIST / path).resolve()
        if not f.is_relative_to(DIST):
            raise HTTPException(status_code=404)
        if not f.is_file():
            f = (DIST / "index.html").resolve()
            if not f.is_relative_to(DIST):
                raise HTTPException(status_code=404)
        return FileResponse(f)
