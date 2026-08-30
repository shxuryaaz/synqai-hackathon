"""Load every source into store.sqlite with entity resolution, precedence, and PII masking at the boundary.
Run: python ingest.py   (idempotent: rebuilds the store from scratch each time)
"""
import csv, json, re, sys
from datetime import date
from pathlib import Path
import openpyxl
from common import BUNDLE, DB, db, mask, canon_vehicle, canon_client
import llm

PRECEDENCE = ["fleet_master", "maintenance_log", "tickets", "emails", "transcript"]

SCHEMA = """
create table vehicles(canon primary key, vehicle_id, model, year int, bs_stage, engine_heater, home_hub, capacity_tonnes, status, last_service_date);
create table vehicle_aliases(canon, original, source, ref);
create table clients(canon primary key);
create table client_aliases(canon, original, source, ref);
create table drivers(driver_id primary key, name, phone, dl_number, aadhaar, joining_date, home_hub);
create table trips(trip_id primary key, created_at, origin_name, dest_name, dispatch_time, delivery_time, osrm_time_min, actual_time_min, vehicle_canon, vehicle_original, driver_id, client, status, region);
create table maintenance(row int primary key, date, vehicle_canon, vehicle_original, odometer_km int, mechanic, notes);
create table maint_events(maint_row, kind, extracted_by, detail);
create table emails(thread, idx int, sender, recipient, date, subject, body, primary key(thread, idx));
create table transcript(section int primary key, text);
create table facts(entity, key, value, source, ref, won int, vs_source, vs_value);
create table entity_map(kind, original primary key, canon, proposed_by);
"""

HUB_WORDS = ["Delhi", "Gurgaon", "Jaipur", "Lucknow", "Chandigarh", "Ludhiana", "Ambala", "Kanpur", "Rudrapur",
             "Haryana", "Punjab", "Uttar Pradesh", "Uttarakhand", "Rajasthan", "Sonipat", "Noida", "Faridabad", "Panipat"]

# Maintenance-note regex first pass. LLM (T4) handles rows that match nothing.
NOTE_PATTERNS = {
    "brake_work": re.compile(r"\bbrake|\bpads?\b|\bdrum\b", re.I),
    "jugaad": re.compile(r"jugaad|temporary fix|temp fix|patch", re.I),
    "permanent_fix_pending": re.compile(r"permanent (fix|repair)|permanent fix baaki", re.I),
    "replaced": re.compile(r"replace|naya lagwaya", re.I),
    "repaired": re.compile(r"repair|weld|clean|refit|band kiya|tested", re.I),
}
EMAIL_YEAR = re.compile(r"(20\d\d)\s*model|model\D{0,20}(20\d\d)", re.I)
EMAIL_ODO = re.compile(r"(\d{1,3}(?:,\d{3})+|\d{4,6})\s*km", re.I)


def fact(con, entity, key, value, source, ref):
    """Store a fact under precedence. Higher-precedence existing value wins; loser recorded, never dropped."""
    row = con.execute("select * from facts where entity=? and key=? and won=1", (entity, key)).fetchone()
    if row is None:
        con.execute("insert into facts values(?,?,?,?,?,1,null,null)", (entity, key, str(value), source, ref))
        return
    if str(row["value"]) == str(value):
        return
    if PRECEDENCE.index(source) < PRECEDENCE.index(row["source"]):
        con.execute("update facts set won=0, vs_source=?, vs_value=? where entity=? and key=? and won=1", (source, str(value), entity, key))
        con.execute("insert into facts values(?,?,?,?,?,1,?,?)", (entity, key, str(value), source, ref, row["source"], row["value"]))
    else:
        con.execute("insert into facts values(?,?,?,?,?,0,?,?)", (entity, key, str(value), source, ref, row["source"], row["value"]))


def alias(con, canon, original, source, ref):
    con.execute("insert into vehicle_aliases values(?,?,?,?)", (canon, original, source, ref))
    con.execute("insert or ignore into entity_map values('vehicle',?,?,'rule')", (original, canon))


def load_fleet(con):
    for i, r in enumerate(csv.DictReader(open(BUNDLE / "fleet_master.csv", encoding="utf-8")), 2):
        c = canon_vehicle(r["registration_number"])
        if not c:
            continue
        con.execute("insert or ignore into vehicles values(?,?,?,?,?,?,?,?,?,null)",
                    (c, r["vehicle_id"], r["model"], int(r["year"]), r["bs_stage"], r["engine_heater"] or "Unknown", r["home_hub"], r["capacity_tonnes"], r["status"]))
        alias(con, c, r["registration_number"], "fleet_master", f"fleet_master.csv row {i}")
        for k in ("year", "bs_stage", "home_hub", "status"):
            fact(con, c, k, r[k], "fleet_master", f"fleet_master.csv row {i}")


def load_maintenance(con):
    ws = openpyxl.load_workbook(BUNDLE / "maintenance_log.xlsx").active
    for i, (d, veh, odo, mech, notes) in enumerate(ws.iter_rows(min_row=2, values_only=True), 2):
        c = canon_vehicle(veh)
        d = str(d)[:10]
        con.execute("insert into maintenance values(?,?,?,?,?,?,?)", (i, d, c, veh, odo, mech, mask(notes or "")))
        if c:
            alias(con, c, veh, "maintenance_log", f"maintenance_log.xlsx row {i}")
        kinds = [k for k, p in NOTE_PATTERNS.items() if p.search(notes or "")]
        for k in kinds:
            con.execute("insert into maint_events values(?,?,?,?)", (i, k, "regex", None))
        if not kinds:  # regex found nothing: ask the model, cite the row, keep going if it fails
            kinds = llm.extract_note(mask(notes or "")) or []
            for k in kinds:
                con.execute("insert into maint_events values(?,?,?,?)", (i, k, "llm", f"maintenance_log.xlsx row {i}"))
            if not kinds:
                con.execute("insert into maint_events values(?,?,?,?)", (i, "unclassified", "none", llm.last_error))
    con.execute("update vehicles set last_service_date=(select max(date) from maintenance m where m.vehicle_canon=vehicles.canon)")
    # Odometer is a time series; only the latest workshop reading is a fact.
    for r in con.execute("select row, date, vehicle_canon, odometer_km from maintenance m where vehicle_canon is not null and date=(select max(date) from maintenance where vehicle_canon=m.vehicle_canon)").fetchall():
        fact(con, r["vehicle_canon"], "odometer_km", r["odometer_km"], "maintenance_log", f"maintenance_log.xlsx row {r['row']} ({r['date']})")


def load_drivers(con):
    # The only place raw PII is read. Masked before it touches the store.
    for r in csv.DictReader(open(BUNDLE / "drivers_roster.csv", encoding="utf-8")):
        con.execute("insert into drivers values(?,?,?,?,?,?,?)",
                    (r["driver_id"], r["name"], mask(r["phone"]), mask(r["dl_number"]), mask(r["aadhaar"]), r["joining_date"], r["home_hub"]))


def load_trips(con):
    for r in csv.DictReader(open(BUNDLE / "meridian_trips.csv", encoding="utf-8")):
        c = canon_vehicle(r["vehicle_reg"])
        region = "north" if any(w in r["origin_name"] + r["dest_name"] for w in HUB_WORDS) else "other"
        con.execute("insert or ignore into trips values(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (r["trip_id"], r["created_at"], r["origin_name"], r["dest_name"], r["dispatch_time"], r["delivery_time"],
                     r["osrm_time_min"], r["actual_time_min"], c, r["vehicle_reg"], r["driver_id"], canon_client(r["client"]) or r["client"], r["status"], region))
        if c:
            con.execute("insert or ignore into entity_map values('vehicle',?,?,'rule')", (r["vehicle_reg"], c))
        con.execute("insert or ignore into client_aliases values(?,?,?,?)", (canon_client(r["client"]), r["client"], "trips", r["trip_id"]))


def load_tickets(con):
    for i, t in enumerate(json.load(open(BUNDLE / "tickets.json", encoding="utf-8"))):
        c = canon_vehicle(t.get("vehicle"))
        if c:
            alias(con, c, t["vehicle"], "tickets", f"tickets.json[{i}] {t.get('ticket_id')}")
        cc = canon_client(t.get("client"))
        if cc:
            con.execute("insert or ignore into client_aliases values(?,?,?,?)", (cc, t["client"], "tickets", t.get("ticket_id")))


def parse_thread(path):
    msgs = []
    for chunk in open(path, encoding="utf-8").read().split("-" * 60):
        hdr, _, body = chunk.strip().partition("\n\n")
        h = dict(re.findall(r"^(From|To|Date|Subject): (.*)$", hdr, re.M))
        if h:
            msgs.append((h, body.strip()))
    return msgs


def load_emails(con):
    for p in sorted((BUNDLE / "emails").glob("*.txt")):
        for idx, (h, body) in enumerate(parse_thread(p)):
            con.execute("insert into emails values(?,?,?,?,?,?,?)", (p.name, idx, h.get("From"), h.get("To"), h.get("Date"), h.get("Subject"), mask(body)))
            ref = f"emails/{p.name} msg {idx} ({h.get('Date')})"
            text = h.get("Subject", "") + " " + body
            plates = {canon_vehicle(m) for m in re.findall(r"\b[A-Z]{2}[ -]?\d{2}[ -]?[A-Z]{1,2}[ -]?\d{4}\b", text)} - {None}
            for m in re.findall(r"\b[A-Z]{2}[ -]?\d{2}[ -]?[A-Z]{1,2}[ -]?\d{4}\b", text):
                if canon_vehicle(m):
                    alias(con, canon_vehicle(m), m, "emails", ref)
            if len(plates) == 1:
                (c,) = plates
                y = EMAIL_YEAR.search(text)
                if y:
                    fact(con, c, "year", y.group(1) or y.group(2), "emails", ref)
                o = EMAIL_ODO.search(text)
                if o:
                    fact(con, c, "odometer_km", o.group(1).replace(",", ""), "emails", ref)


def load_transcript(con):
    text = open(BUNDLE / "dispatcher_interview.txt", encoding="utf-8").read()
    for i, sec in enumerate(re.split(r"\n\n(?=INTERVIEWER:)", text)):
        con.execute("insert into transcript values(?,?)", (i, mask(sec.strip())))


def main():
    if DB.exists():
        DB.unlink()
    for suffix in ("-wal", "-shm"):
        Path(str(DB) + suffix).unlink(missing_ok=True)
    con = db()
    con.executescript(SCHEMA)
    for c in ["Shakti Cement", "Vertex Retail", "Apex Chemicals", "Orion Pharma", "Internal"]:
        con.execute("insert into clients values(?)", (c,))
    for step in (load_fleet, load_maintenance, load_drivers, load_trips, load_tickets, load_emails, load_transcript):
        step(con)
    con.commit()
    n = lambda t: con.execute(f"select count(*) from {t}").fetchone()[0]
    conflicts = con.execute("select count(*) from facts where won=1 and vs_source is not null").fetchone()[0] + \
                con.execute("select count(*) from facts where won=0").fetchone()[0]
    print(f"store: {n('vehicles')} vehicles, {n('vehicle_aliases')} plate forms, {n('drivers')} drivers (masked), {n('trips')} trips, "
          f"{n('maintenance')} maintenance rows, {n('maint_events')} events, {n('emails')} emails, {n('transcript')} transcript sections, {conflicts} conflicts resolved by precedence")


if __name__ == "__main__":
    main()
