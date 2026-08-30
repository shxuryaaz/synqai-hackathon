"""Human approval gate. Run: python approve.py TKT-0009 --by "Ramesh Kumar" [--body "edited text"]"""
import argparse, json
from contextlib import closing
from datetime import datetime, timezone
from common import db, mask, mask_data, has_pii
from pipeline import audit, write_outputs, PIPE_SCHEMA


class ApprovalConflict(Exception):
    pass


class ApprovalValidationError(ValueError):
    pass


def approve(ticket_id, by, body=None, at=None):
    if body is not None and has_pii(body):
        raise ApprovalValidationError("refusing to send: edited body matches a PII pattern")
    ticket_id, by, at = mask_data((ticket_id, by, at))
    body = mask(body) if body is not None else None
    with closing(db()) as con:
        con.executescript(PIPE_SCHEMA)
        row = con.execute("select * from comms where ticket_id=?", (ticket_id,)).fetchone()
        if not row:
            raise ApprovalConflict(f"{ticket_id} has no approval record")
        at = at or datetime.now(timezone.utc).isoformat(timespec="seconds")
        final = body or row["body"]
        if has_pii(final):
            raise ApprovalValidationError("refusing to send: body matches a PII pattern")
        with con:
            updated = con.execute("update comms set status='sent', approved_by=?, sent_at=?, edited_body=? where ticket_id=? and status='pending'", (by, at, body, ticket_id))
            if updated.rowcount != 1:
                current = con.execute("select status, approved_by, sent_at from comms where ticket_id=?", (ticket_id,)).fetchone()
                if current and current["status"] == "sent":
                    raise ApprovalConflict(f"{ticket_id} was already sent by {current['approved_by']} at {current['sent_at']}")
                raise ApprovalConflict(f"{ticket_id} is not pending approval")
            audit(con, ticket_id, 7, "Approved and sent", at, f"approved by {by}" + (" with edits" if body else ""), {"recipient": row["recipient"]}, by="human")
        write_outputs(con)
        return {"ticket_id": ticket_id, "result": "sent", "sent_at": at, "approved_by": by}


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("ticket_id"); ap.add_argument("--by", required=True); ap.add_argument("--body")
    a = ap.parse_args()
    print(json.dumps(approve(a.ticket_id, a.by, a.body)))
