"""Breakdown pipeline. Run: python pipeline.py candidate_bundle/tickets.json
Per ticket: validate -> enrich -> severity -> replacement -> work order -> comms draft. Every step audited.
Exactly-once: every decision is insert-or-ignore under a hash id; output files are re-projected from the store
in sorted order, so a second run writes the same bytes. Nothing in an output line comes from the wall clock.
"""
import csv, json, math, re, sys, traceback
from datetime import datetime, timedelta, timezone
from pathlib import Path
import yaml
import llm
from common import ROOT, OUT, AUDIT, LOGS, db, mask, canon_vehicle, canon_client, stable_id, CLIENT_ALIASES, pretty_plate

RULES = yaml.safe_load(open(ROOT / "rules.yaml"))
HUBS = yaml.safe_load(open(ROOT / "hubs.yaml"))
H = HUBS["hubs"]

# ---- schema tolerance -------------------------------------------------------------------------
FIELD_MAP = {
    "ticket_id": ["ticket_id", "ticketid", "id", "ticket", "ticket_no", "ticketnumber", "ticket_number", "ref"],
    "created_at": ["created_at", "createdat", "timestamp", "reported_at", "reportedat", "time", "date", "datetime", "opened_at", "created"],
    "vehicle": ["vehicle", "vehicleid", "vehicle_id", "vehicle_no", "vehicleno", "reg", "registration", "registration_number", "plate", "vehicle_reg", "vehiclereg", "truck"],
    "driver_id": ["driver_id", "driverid", "driver"],
    "origin_hub": ["origin_hub", "originhub", "hub", "origin", "from_hub", "source_hub"],
    "km_from_origin_hub": ["km_from_origin_hub", "kmfromoriginhub", "km_from_hub", "distance_km", "distancekm", "km", "distance"],
    "destination": ["destination", "dest", "destination_hub", "destinationhub", "to", "to_hub"],
    "issue": ["issue", "problem", "fault", "description", "complaint", "issue_description"],
    "severity": ["severity", "priority", "urgency"],
    "client": ["client", "customer", "client_name", "clientname", "account"],
    "status": ["status", "state"],
    "resolution_note": ["resolution_note", "resolutionnote", "resolution", "note", "notes"],
}
LOOKUP = {v: k for k, vs in FIELD_MAP.items() for v in vs}
REQUIRED = ["ticket_id", "vehicle", "created_at", "origin_hub"]
DRAFT_BY = llm.DRAFT_MODEL
STEPS = ["Validated", "Enriched", "Rule applied", "Truck selected", "Work order", "Draft created"]


def snake(k):
    return re.sub(r"(?<!^)(?=[A-Z])", "_", str(k)).lower().replace("-", "_").replace(" ", "_")


def map_record(rec):
    out, unknown = {}, []
    for k, v in rec.items():
        key = LOOKUP.get(snake(k)) or LOOKUP.get(snake(k).replace("_", ""))
        (out.__setitem__(key, v) if key else unknown.append(k))
    return out, unknown


def parse_date(v):
    """ISO, epoch seconds/millis, DD-MM-YYYY, DD/MM/YYYY, with or without time -> ISO string. None if hopeless."""
    if v is None or v == "":
        return None
    if isinstance(v, (int, float)) or re.fullmatch(r"\d{10,13}", str(v)):
        n = float(v)
        return datetime.fromtimestamp(n / 1000 if n > 1e11 else n, timezone.utc).replace(tzinfo=None, microsecond=0).isoformat()
    s = str(v).strip().replace("Z", "")
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M", "%Y-%m-%d %H:%M", "%Y-%m-%d",
                "%d-%m-%Y %H:%M:%S", "%d-%m-%Y %H:%M", "%d-%m-%Y", "%d/%m/%Y %H:%M:%S", "%d/%m/%Y %H:%M", "%d/%m/%Y",
                "%d %b %Y %H:%M", "%d %b %Y"):
        try:
            return datetime.strptime(s, fmt).isoformat()
        except ValueError:
            pass
    return None


def read_ticket_file(path):
    p = Path(path)
    text = p.read_text(encoding="utf-8")
    if p.suffix == ".csv":
        return list(csv.DictReader(text.splitlines()))
    if p.suffix == ".jsonl":
        return [json.loads(l) for l in text.splitlines() if l.strip()]
    data = json.loads(text)
    if isinstance(data, dict):
        data = next((v for v in data.values() if isinstance(v, list)), [])
    return data


# ---- geometry ---------------------------------------------------------------------------------
def km(a, b):
    la1, lo1, la2, lo2 = map(math.radians, (a["lat"], a["lon"], b["lat"], b["lon"]))
    h = math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2
    return 2 * 6371 * math.asin(math.sqrt(h)) * HUBS["road_factor"]


def breakdown_point(origin, dest, km_out):
    o, d = H[origin], H.get(dest, H[origin])
    total = km(o, d) or 1
    f = min(km_out / total, 1)
    return {"lat": o["lat"] + (d["lat"] - o["lat"]) * f, "lon": o["lon"] + (d["lon"] - o["lon"]) * f}


# ---- rule engine ------------------------------------------------------------------------------
def when_matches(when, ctx):
    checks = {
        "client": lambda v: ctx["client"] == v,
        "destination": lambda v: ctx["destination"] == v,
        "months": lambda v: ctx["month"] in v,
        "route_touches_ncr": lambda v: (ctx["origin_hub"] in HUBS["ncr"] or ctx["destination"] in HUBS["ncr"]) == v,
        "dest_hill": lambda v: bool(H.get(ctx["destination"], {}).get("hill")) == v,
        "dest_east_of_lucknow": lambda v: (H.get(ctx["destination"], H["Lucknow"])["lon"] > H["Lucknow"]["lon"]) == v,
        "km_from_origin_lte": lambda v: ctx["km_from_origin_hub"] <= v,
        "night_run": lambda v: (ctx["hour"] >= 20 or ctx["hour"] < 6) == v,
        "driver_tenure_months_lt": lambda v: ctx["driver_tenure_months"] is not None and ctx["driver_tenure_months"] < v,
    }
    return all(checks[k](v) for k, v in when.items())


def candidate_fails(require, cand, ctx, con):
    """Return the failing requirement name, or None if the candidate passes."""
    t = ctx["created"]
    for k, v in require.items():
        if k == "bs_stage" and cand["bs_stage"] != v:
            return f"bs_stage={cand['bs_stage']}"
        if k == "engine_heater" and cand["engine_heater"] != v:
            return f"engine_heater={cand['engine_heater']}"
        if k == "year_gte" and cand["year"] < v:
            return f"year={cand['year']}"
        if k == "no_brake_work_days":
            row = con.execute("select date from maintenance m join maint_events e on e.maint_row=m.row where vehicle_canon=? and kind='brake_work' and date<=? and date>=? order by date desc limit 1",
                              (cand["canon"], t.date().isoformat(), (t - timedelta(days=v)).date().isoformat())).fetchone()
            if row:
                return f"brake work on {row['date']}"
        if k == "service_overdue_days_lte":
            last = con.execute("select max(date) d from maintenance where vehicle_canon=? and date<=?", (cand["canon"], t.date().isoformat())).fetchone()["d"]
            if last:
                due = datetime.fromisoformat(last) + timedelta(days=HUBS["service_interval_days"])
                overdue = (t - due).days
                if overdue > v:
                    return f"service overdue {overdue} days (due {due.date()})"
        if k == "jugaad_stays_home":
            row = con.execute("select date from maintenance m join maint_events e on e.maint_row=m.row where vehicle_canon=? and kind='jugaad' and date<=? and date>=? order by date desc limit 1",
                              (cand["canon"], t.date().isoformat(), (t - timedelta(days=v)).date().isoformat())).fetchone()
            if row and H.get(cand["home_hub"], {}).get("region") != H.get(ctx["destination"], {}).get("region"):
                return f"jugaad on {row['date']}, must stay in {H.get(cand['home_hub'], {}).get('region')}"
        if k == "not_last_issue_with_client":
            row = con.execute("select ticket_id from tickets where vehicle_canon=? and client=? and created_at<? order by created_at desc limit 1", (cand["canon"], v, t.isoformat())).fetchone()
            if row:
                later = con.execute("select 1 from trips where vehicle_canon=? and client!=? and dispatch_time>? limit 1", (cand["canon"], v, t.isoformat())).fetchone()
                if not later:
                    return f"had issue on {v} run ({row['ticket_id']}), rotate"
    return None


# ---- store ------------------------------------------------------------------------------------
PIPE_SCHEMA = """
create table if not exists tickets(ticket_id primary key, created_at, vehicle_canon, vehicle_original, driver_id, origin_hub, km_from_origin_hub, destination, issue, reported_severity, client, status, source_file);
create table if not exists work_orders(work_order_id primary key, ticket_id unique, vehicle_reg, created_at, citations, severity, replacement, replacement_hub, eta, sla_hours, rules_applied, skipped, flags);
create table if not exists comms(message_id primary key, ticket_id unique, recipient, body, context, citations, drafted_by, status default 'pending', approved_by, sent_at, edited_body);
create table if not exists quarantine(key primary key, ticket_id, source_file, reason, detail, record, created_at, resubmitted int default 0);
create table if not exists audit(key primary key, seq int, ticket_id, step, at, decision, data, rule_ids, by);
create table if not exists alerts(key primary key, level, message, source_file, records int, created_at);
"""


def audit(con, ticket_id, seq, step, at, decision, data=None, rule_ids=(), by="code"):
    con.execute("insert or ignore into audit values(?,?,?,?,?,?,?,?,?)",
                (stable_id("AUD", ticket_id, seq, step), seq, ticket_id, step, at, decision, json.dumps(data or {}, ensure_ascii=False, sort_keys=True), ",".join(rule_ids), by))


def quarantine(con, rec, reason, detail, source_file, at):
    tid = str(rec.get("ticket_id") or stable_id("REC", json.dumps(rec, sort_keys=True, default=str)))
    con.execute("insert or ignore into quarantine values(?,?,?,?,?,?,?,0)",
                (stable_id("Q", tid, reason), tid, source_file, reason, detail, json.dumps(rec, ensure_ascii=False, sort_keys=True, default=str), at))
    audit(con, tid, 0, "Quarantined", at, f"{reason}: {detail}", {"source": source_file})


# ---- per ticket -------------------------------------------------------------------------------
def process(con, rec, source_file, seen):
    t, unknown = map_record(rec)
    if not t:
        return quarantine(con, rec, "unrecognized_format", f"no known fields in {list(rec)[:6]}", source_file, "n/a")
    tid = str(t.get("ticket_id") or "").strip()
    missing = [f for f in REQUIRED if not str(t.get(f) or "").strip()]
    created = parse_date(t.get("created_at"))
    if missing:
        return quarantine(con, t | {"_unmapped": unknown} if unknown else t, "missing_field", f"missing {', '.join(m.replace('_', ' ') for m in missing)}", source_file, created or "n/a")
    if not created:
        return quarantine(con, t, "bad_date", f"cannot parse created_at={t.get('created_at')!r}", source_file, "n/a")
    if tid in seen:
        LOG.append({"event": "duplicate_skipped", "ticket_id": tid, "source": source_file})
        return
    seen.add(tid)
    vc = canon_vehicle(t["vehicle"])
    if not vc:
        return quarantine(con, t, "invalid_vehicle", f"vehicle {t['vehicle']!r} is not a registration number", source_file, created)
    if t["origin_hub"] not in H:
        return quarantine(con, t, "unknown_hub", f"origin_hub {t['origin_hub']!r} not in hubs.yaml", source_file, created)
    if con.execute("select 1 from work_orders where ticket_id=?", (tid,)).fetchone():
        LOG.append({"event": "already_processed", "ticket_id": tid})
        return
    dt = datetime.fromisoformat(created)
    client = canon_client(t.get("client"))
    if client is None and t.get("client"):
        client = llm.propose_match(str(t["client"]), list(CLIENT_ALIASES))
        if client:
            con.execute("insert or ignore into entity_map values('client',?,?,'llm')", (re.sub(r"[^a-z]", "", str(t["client"]).lower()), client))
            LOG.append({"event": "client_match_proposed", "ticket_id": tid, "original": t["client"], "canon": client})
    client = client or "Internal"
    con.execute("insert or ignore into tickets values(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (tid, created, vc, t["vehicle"], t.get("driver_id"), t["origin_hub"], float(t.get("km_from_origin_hub") or 0), t.get("destination") or t["origin_hub"],
                 t.get("issue") or "", t.get("severity"), client, t.get("status"), source_file))
    audit(con, tid, 1, STEPS[0], created, "ticket has all required fields", {"mapped_from": {k: LOOKUP.get(snake(k)) for k in rec if LOOKUP.get(snake(k)) != k}, "source": source_file})

    # enrich
    veh = con.execute("select * from vehicles where canon=?", (vc,)).fetchone()
    if veh:  # service history as of the ticket date, not as of today
        veh = dict(veh) | {"last_service_date": con.execute("select max(date) d from maintenance where vehicle_canon=? and date<=?", (vc, dt.date().isoformat())).fetchone()["d"]}
    drv = con.execute("select * from drivers where driver_id=?", (t.get("driver_id"),)).fetchone()
    tenure = (dt - datetime.fromisoformat(drv["joining_date"])).days / 30.4 if drv else None
    hist = con.execute("select m.date, m.notes, m.row, group_concat(e.kind) kinds from maintenance m left join maint_events e on e.maint_row=m.row where vehicle_canon=? and date<=? group by m.row order by date desc limit 5", (vc, dt.date().isoformat())).fetchall()
    ctx = {"client": client, "destination": t.get("destination") or t["origin_hub"], "origin_hub": t["origin_hub"], "month": dt.month, "hour": dt.hour,
           "km_from_origin_hub": float(t.get("km_from_origin_hub") or 0), "driver_tenure_months": tenure, "created": dt}
    citations = [f"tickets: {source_file} {tid}"]
    if veh:
        citations.append(f"fleet_master.csv {veh['vehicle_id']} ({vc})")
    citations += [f"maintenance_log.xlsx row {h['row']} ({h['date']})" for h in hist]
    if drv:
        citations.append(f"drivers_roster.csv {drv['driver_id']} (joined {drv['joining_date']})")
    audit(con, tid, 2, STEPS[1], created, f"vehicle {'found' if veh else 'NOT in fleet master'}, driver {'found' if drv else 'unknown'}, {len(hist)} maintenance rows, client {client}",
          {"vehicle": veh, "driver_tenure_months": round(tenure, 1) if tenure is not None else None, "maintenance": [dict(h) for h in hist], "citations": citations})

    # rules
    params = {"sla_hours": HUBS["default_sla_hours"], "replacement_hub": "nearest", "eta_pad": 1.0}
    applied, requires = [], []
    for r in RULES["rules"]:
        if when_matches(r.get("when", {}), ctx):
            applied.append(r["id"])
            params.update(r.get("effect", {}))
            if r.get("require"):
                requires.append(r)
    sev = next((s for s, words in RULES["severity"].items() if any(w in (t.get("issue") or "").lower() for w in words)), "LOW")
    if client in RULES["escalate_for_clients"] and sev != "HIGH":
        sev = {"LOW": "MEDIUM", "MEDIUM": "HIGH"}[sev]
    audit(con, tid, 3, STEPS[2], created, f"severity {sev} (reported {t.get('severity')}), SLA {params['sla_hours']}h, replacement from {params['replacement_hub']} hub" + (", pair the driver (night run, new driver)" if params.get("pair_driver") else ""),
          {"params": params, "severity_words": RULES["severity"]}, applied)

    # replacement
    point = breakdown_point(t["origin_hub"], ctx["destination"], ctx["km_from_origin_hub"])
    hubs_order = [t["origin_hub"]] if params["replacement_hub"] == "origin" else sorted(H, key=lambda h: km(H[h], point))
    skipped, chosen, chosen_hub = [], None, None
    for hub in hubs_order:
        cands = con.execute("select * from vehicles where home_hub=? and status='Active' and canon!=? order by year desc, canon", (hub, vc)).fetchall()
        for c in cands:
            busy = con.execute("select trip_id from trips where vehicle_canon=? and dispatch_time<=? and delivery_time>=?", (c["canon"], created, created)).fetchone()
            if busy:
                skipped.append({"vehicle": c["canon"], "hub": hub, "rule": "assigned", "why": f"on trip {busy['trip_id']}"})
                continue
            fail = next(((r["id"], candidate_fails(r["require"], c, ctx, con)) for r in requires if candidate_fails(r["require"], c, ctx, con)), None)
            if fail:
                skipped.append({"vehicle": c["canon"], "hub": hub, "rule": fail[0], "why": fail[1]})
                continue
            chosen, chosen_hub = c, hub
            break
        if chosen:
            break
    rules_hit = sorted({s["rule"] for s in skipped if s["rule"].startswith("R")})
    audit(con, tid, 4, STEPS[3], created, f"{chosen['canon'] + ' from ' + chosen_hub + ' hub' if chosen else 'NO eligible replacement'}; {len(skipped)} candidates skipped",
          {"chosen": dict(chosen) if chosen else None, "skipped": skipped, "hubs_considered": hubs_order[:3]}, applied + rules_hit)

    # eta / sla
    hours = HUBS["transfer_hours"] + (km(H[chosen_hub], point) + km(point, H.get(ctx["destination"], H[t["origin_hub"]]))) / HUBS["avg_speed_kmh"] if chosen else None
    eta = (dt + timedelta(hours=hours * params["eta_pad"])).replace(second=0, microsecond=0) if hours else None
    flags = []
    if eta and params.get("gate_close_hour") and eta.hour >= params["gate_close_hour"]:
        eta = (eta + timedelta(days=1)).replace(hour=params["gate_open_hour"], minute=0, second=0)
        flags.append("scheduled morning delivery (gate closed), not a failed delivery")
    if eta and (eta - dt).total_seconds() / 3600 > params["sla_hours"]:
        flags.append(f"ETA exceeds {params['sla_hours']}h SLA")
    if params.get("pair_driver"):
        flags.append("pair the driver: under 6 months, night run")
    if params.get("no_overnight_hold"):
        flags.append("no overnight hold at hub (refrigerated load)")

    # work order (idempotent)
    wo = stable_id("WO", tid)
    con.execute("insert or ignore into work_orders values(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (wo, tid, vc, created, json.dumps(citations, ensure_ascii=False), sev, chosen["canon"] if chosen else None, chosen_hub, eta.isoformat() if eta else None,
                 params["sla_hours"], ",".join(applied + rules_hit), json.dumps(skipped, ensure_ascii=False), json.dumps(flags)))
    audit(con, tid, 5, STEPS[4], created, f"work order {wo}", {"citations": citations})

    # comms draft (template; llm.py in T4 replaces the body when available)
    if client == "Internal":
        audit(con, tid, 6, STEPS[5], created, "internal ticket, no client message", {})
    else:
        facts = {"client": client, "truck": pretty_plate(vc), "route": f"{t['origin_hub']} to {ctx['destination']}", "fault": t.get("issue"), "km_from_hub": int(ctx["km_from_origin_hub"]),
                 "replacement": pretty_plate(chosen["canon"]) if chosen else None, "replacement_hub": chosen_hub, "revised_delivery": eta.strftime("%d %b %H:%M") if eta else None,
                 "notes": flags + (["ETA includes monsoon allowance"] if params.get("eta_pad", 1) > 1 else []), "hub_desk": t["origin_hub"]}
        body = llm.draft(facts)
        drafted_by = DRAFT_BY if body else "template"
        if not body:
            body = draft_body(client, vc, t, chosen, chosen_hub, eta, flags, params)
            audit(con, tid, 6, "Draft fallback", created, f"model unavailable ({llm.last_error}); template used", {}, by="code")
        why = why_text(t, client, chosen, chosen_hub, skipped, params, applied + rules_hit)
        recipient = con.execute("select sender from emails where sender like ? order by thread limit 1", (f"%{client.split()[0].lower()}%",)).fetchone()
        con.execute("insert or ignore into comms(message_id, ticket_id, recipient, body, context, citations, drafted_by) values(?,?,?,?,?,?,?)",
                    (stable_id("MSG", tid), tid, recipient[0] if recipient else f"{client} dispatch desk", mask(body),
                     json.dumps({"why": why, "rules": applied + rules_hit, "severity": sev, "eta": eta.isoformat() if eta else None, "flags": flags}, ensure_ascii=False), json.dumps(citations, ensure_ascii=False), drafted_by))
        audit(con, tid, 6, STEPS[5], created, f"client message drafted for {client} by {drafted_by}, awaiting approval", {"recipient": recipient[0] if recipient else None}, applied + rules_hit, by="LLM" if drafted_by != "template" else "code")


def draft_body(client, vc, t, chosen, hub, eta, flags, params):
    fmt = lambda d: d.strftime("%d %b %H:%M")
    lines = [f"Dear {client} team,", "",
             f"Your consignment on truck {vc} ({t['origin_hub']} to {t.get('destination') or t['origin_hub']}) has been held up by a mechanical fault ({t.get('issue') or 'breakdown'}) {int(float(t.get('km_from_origin_hub') or 0))} km from {t['origin_hub']}."]
    if chosen:
        lines.append(f"A replacement truck, {chosen['canon']}, is being dispatched from the {hub} hub. Revised delivery time: {fmt(eta)}.")
    else:
        lines.append("We are arranging a replacement and will confirm the revised delivery time shortly.")
    if any("morning delivery" in f for f in flags):
        lines.append("As the arrival falls after your gate closes, the truck will hold at the last halt and deliver at 08:00 next morning as a scheduled morning delivery.")
    if params.get("eta_pad", 1) > 1:
        lines.append("This time includes the monsoon allowance for eastern routes.")
    lines += ["", "No action is needed from your side. We are sorry for the inconvenience.", "", f"Meridian Freight, {t['origin_hub']} desk"]
    return "\n".join(lines)


def why_text(t, client, chosen, hub, skipped, params, rules):
    km_out = int(float(t.get("km_from_origin_hub") or 0))
    s = [f"The breakdown is {km_out} km from {t['origin_hub']}, so the {'origin hub sends' if params['replacement_hub'] == 'origin' else 'nearest hub with an eligible truck sends'}."]
    if chosen:
        s.append(f"{chosen['canon']} was the newest free truck at {hub} that passed every rule.")
    else:
        s.append("No truck at any hub passed every rule; the work order is open for a manual decision.")
    by_rule = {}
    for sk in skipped:
        by_rule.setdefault(sk["rule"], []).append(sk)
    for rid, items in by_rule.items():
        s.append(f"{len(items)} skipped by {rid}: " + "; ".join(f"{i['vehicle']} ({i['why']})" for i in items[:3]) + (" ..." if len(items) > 3 else ""))
    if params["sla_hours"] != HUBS["default_sla_hours"]:
        s.append(f"Planned to a {params['sla_hours']}h SLA for {client}.")
    return " ".join(s)


# ---- projection --------------------------------------------------------------------------------
def write_outputs(con):
    OUT.mkdir(exist_ok=True); AUDIT.mkdir(exist_ok=True)
    def dump(path, rows):
        with open(path, "w", encoding="utf-8") as f:
            for r in rows:
                f.write(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n")
    dump(OUT / "work_orders.jsonl", [{"work_order_id": r["work_order_id"], "ticket_id": r["ticket_id"], "vehicle_reg": r["vehicle_reg"], "created_at": r["created_at"], "citations": json.loads(r["citations"]),
                                     "severity": r["severity"], "replacement": r["replacement"], "replacement_hub": r["replacement_hub"], "eta": r["eta"], "rules": r["rules_applied"].split(",") if r["rules_applied"] else [], "flags": json.loads(r["flags"])}
                                    for r in con.execute("select * from work_orders order by ticket_id")])
    dump(OUT / "comms_pending.jsonl", [{"message_id": r["message_id"], "ticket_id": r["ticket_id"], "recipient": r["recipient"], "body": r["body"], "context": json.loads(r["context"]), "citations": json.loads(r["citations"]), "drafted_by": r["drafted_by"]}
                                       for r in con.execute("select * from comms where status='pending' order by ticket_id")])
    dump(OUT / "comms_sent.jsonl", [{"message_id": r["message_id"], "ticket_id": r["ticket_id"], "recipient": r["recipient"], "body": r["edited_body"] or r["body"], "approved_by": r["approved_by"], "sent_at": r["sent_at"]}
                                    for r in con.execute("select * from comms where status='sent' order by ticket_id")])
    dump(OUT / "quarantine.jsonl", [{"ticket_id": r["ticket_id"], "reason": r["reason"], "detail": r["detail"], "source_file": r["source_file"], "record": json.loads(r["record"]), "alert": f"Ticket {r['ticket_id']} set aside: {r['detail']}"}
                                    for r in con.execute("select * from quarantine where resubmitted=0 order by ticket_id, reason")])
    dump(AUDIT / "audit.jsonl", [{"ticket_id": r["ticket_id"], "seq": r["seq"], "step": r["step"], "at": r["at"], "decision": r["decision"], "data": json.loads(r["data"]), "rule_ids": r["rule_ids"].split(",") if r["rule_ids"] else [], "by": r["by"]}
                                 for r in con.execute("select * from audit order by ticket_id, seq, step")])


LOG = []


def run(path):
    con = db()
    con.executescript(PIPE_SCHEMA)
    source_file = Path(path).name
    try:
        records = read_ticket_file(path)
    except Exception as e:
        con.execute("insert or ignore into alerts values(?,?,?,?,?,?)", (stable_id("ALERT", source_file, "unreadable"), "amber", f"File {source_file} could not be read ({type(e).__name__}). Nothing was changed.", source_file, 0, "n/a"))
        con.commit(); write_outputs(con)
        return {"file": source_file, "error": str(e)}
    mapped = [map_record(r)[0] for r in records if isinstance(r, dict)]
    recognised = sum(1 for m in mapped if all(f in m for f in REQUIRED))
    if records and recognised == 0:
        con.execute("insert or ignore into alerts values(?,?,?,?,?,?)", (stable_id("ALERT", source_file, "format"), "amber",
                    f"New ticket file received in an unrecognized format. Nothing was changed. {len(records)} records held safely.", source_file, len(records), "n/a"))
        for r in records:
            quarantine(con, r if isinstance(r, dict) else {"raw": r}, "unrecognized_format", f"fields {list(r)[:6] if isinstance(r, dict) else type(r).__name__} did not map to the ticket schema", source_file, "n/a")
        con.commit(); write_outputs(con)
        return {"file": source_file, "records": len(records), "unrecognized": True}
    seen = set()
    for rec in records:
        try:
            with con:
                process(con, rec if isinstance(rec, dict) else {"raw": rec}, source_file, seen)
        except Exception as e:
            LOG.append({"event": "exception", "ticket": str(rec)[:200], "error": repr(e), "trace": traceback.format_exc()[-800:]})
            with con:
                quarantine(con, rec if isinstance(rec, dict) else {"raw": rec}, "processing_error", f"{type(e).__name__}: {e}", source_file, "n/a")
    write_outputs(con)
    LOGS.mkdir(exist_ok=True)
    with open(LOGS / "pipeline.jsonl", "a", encoding="utf-8") as f:
        for e in LOG:
            f.write(json.dumps({"file": source_file, **e}, ensure_ascii=False) + "\n")
    n = lambda q: con.execute(q).fetchone()[0]
    summary = {"file": source_file, "records": len(records), "work_orders": n("select count(*) from work_orders"), "pending": n("select count(*) from comms where status='pending'"),
               "quarantined": n("select count(*) from quarantine where resubmitted=0"), "duplicates_skipped": sum(1 for e in LOG if e["event"] == "duplicate_skipped"), "exceptions": sum(1 for e in LOG if e["event"] == "exception")}
    return summary


if __name__ == "__main__":
    print(json.dumps(run(sys.argv[1] if len(sys.argv) > 1 else "candidate_bundle/tickets.json")))
