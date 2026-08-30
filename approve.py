"""Human approval gate. Run: python approve.py TKT-0009 --by "Ramesh Kumar" [--body "edited text"]
Writes comms_sent exactly once per ticket. A second approval is a no-op with an audit line.
"""
import argparse, json
from datetime import datetime, timezone
from common import db, mask, mask_data, has_pii
from pipeline import audit, write_outputs, PIPE_SCHEMA


def approve(ticket_id, by, body=None, at=None):
    ticket_id, by, body, at = mask_data((ticket_id, by, body, at))
    con = db()
    con.executescript(PIPE_SCHEMA)
    row = con.execute("select * from comms where ticket_id=?", (ticket_id,)).fetchone()
    if not row:
        return {"ticket_id": ticket_id, "result": "no_draft"}
    at = at or datetime.now(timezone.utc).isoformat(timespec="seconds")
    if row["status"] == "sent":
        audit(con, ticket_id, 8, "Approval repeated", at, f"already sent by {row['approved_by']} at {row['sent_at']}; no-op, nothing re-sent", {"by": by}, by="human")
        con.commit(); write_outputs(con)
        return {"ticket_id": ticket_id, "result": "already_sent", "sent_at": row["sent_at"], "approved_by": row["approved_by"]}
    if body is not None:
        body = mask(body)
    final = body or row["body"]
    assert not has_pii(final), "refusing to send: body matches a PII pattern"
    with con:
        con.execute("update comms set status='sent', approved_by=?, sent_at=?, edited_body=? where ticket_id=? and status='pending'", (by, at, body, ticket_id))
        audit(con, ticket_id, 7, "Approved and sent", at, f"approved by {by}" + (" with edits" if body else ""), {"recipient": row["recipient"]}, by="human")
    write_outputs(con)
    return {"ticket_id": ticket_id, "result": "sent", "sent_at": at, "approved_by": by}


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("ticket_id"); ap.add_argument("--by", required=True); ap.add_argument("--body")
    a = ap.parse_args()
    print(json.dumps(approve(a.ticket_id, a.by, a.body)))
