import sqlite3
import sys
from datetime import datetime
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from pipeline import candidate_fails, parse_date, process, record_order


@pytest.fixture
def con():
    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    connection.executescript(
        """
        create table maintenance(row integer primary key, date, vehicle_canon, notes);
        create table maint_events(maint_row, kind);
        create table tickets(ticket_id primary key, created_at, vehicle_canon, client);
        create table trips(trip_id primary key, dispatch_time, vehicle_canon, status);
        create table work_orders(ticket_id primary key, created_at, replacement);
        create table quarantine(key primary key, ticket_id, source_file, reason, detail, record, created_at, resubmitted);
        create table audit(key primary key, seq, ticket_id, step, at, decision, data, rule_ids, by);
        """
    )
    return connection


CANDIDATE = {"canon": "DL13XI5012", "home_hub": "Delhi"}


def context(at="2026-08-01T00:00:00", destination="Jaipur"):
    return {"ticket_id": "TKT-CURRENT", "created": datetime.fromisoformat(at), "destination": destination}


def maintenance(con, row, date, *kinds, notes=""):
    con.execute("insert into maintenance values(?,?,?,?)", (row, date, CANDIDATE["canon"], notes))
    con.executemany("insert into maint_events values(?,?)", ((row, kind) for kind in kinds))


def test_r5_requires_valid_history_and_keeps_30_day_boundary(con):
    assert candidate_fails({"service_overdue_days_lte": 30}, CANDIDATE, context(), con).startswith("no maintenance evidence")
    maintenance(con, 1, "not-a-date")
    assert candidate_fails({"service_overdue_days_lte": 30}, CANDIDATE, context(), con).startswith("no maintenance evidence")

    con.execute("update maintenance set date='2026-01-03' where row=1")
    assert candidate_fails({"service_overdue_days_lte": 30}, CANDIDATE, context(), con) is None
    assert "service overdue 31 days" in candidate_fails(
        {"service_overdue_days_lte": 30}, CANDIDATE, context("2026-08-02T00:00:00"), con
    )


def test_r6_old_unrepaired_patch_stays_home_until_repaired(con):
    maintenance(con, 1, "2026-01-01", "jugaad", "permanent_fix_pending", "repaired", notes="radiator leak, jugaad, permanent fix baaki")
    failure = candidate_fails({"jugaad_stays_home": 7}, CANDIDATE, context(), con)
    assert "overdue since 2026-01-08" in failure
    assert candidate_fails({"jugaad_stays_home": 7}, CANDIDATE, context(destination="Gurgaon"), con) is None

    maintenance(con, 2, "2026-07-31", "replaced", notes="radiator replace kiya")
    assert candidate_fails({"jugaad_stays_home": 7}, CANDIDATE, context(), con) is None


@pytest.mark.parametrize(
    ("repair_date", "blocked"),
    [("2026-07-31", False), ("2026-08-01", True), ("2026-08-02", True), ("bad-date", True)],
)
def test_r6_requires_matching_repair_on_strictly_later_day_before_dispatch(con, repair_date, blocked):
    maintenance(con, 1, "2026-07-25", "jugaad", "permanent_fix_pending", "repaired", notes="turbo awaaz, jugaad, permanent fix baaki")
    maintenance(con, 2, repair_date, "repaired", notes="turbo repair kiya")
    failure = candidate_fails({"jugaad_stays_home": 7}, CANDIDATE, context(), con)
    assert bool(failure) is blocked


def test_r6_unrelated_repair_does_not_clear_patch(con):
    maintenance(con, 1, "2026-07-20", "jugaad", notes="radiator leak, temporary fix applied")
    maintenance(con, 2, "2026-07-25", "jugaad", notes="turbo awaaz, temporary fix applied")
    maintenance(con, 3, "2026-07-31", "replaced", notes="radiator replace kiya")
    assert candidate_fails({"jugaad_stays_home": 7}, CANDIDATE, context(), con)


def test_r6_unknown_patch_component_fails_closed(con):
    maintenance(con, 1, "2026-07-25", "jugaad", notes="mystery assembly temporary fix applied")
    maintenance(con, 2, "2026-07-31", "repaired", notes="mystery assembly repair kiya")
    assert candidate_fails({"jugaad_stays_home": 7}, CANDIDATE, context(), con)


def test_r6_newest_component_repaired_but_older_component_open(con):
    maintenance(con, 1, "2026-07-20", "jugaad", notes="radiator leak, temporary fix applied")
    maintenance(con, 2, "2026-07-25", "jugaad", notes="turbo awaaz, temporary fix applied")
    maintenance(con, 3, "2026-07-31", "repaired", notes="turbo repair kiya")
    failure = candidate_fails({"jugaad_stays_home": 7}, CANDIDATE, context(), con)
    assert "2026-07-20 (radiator)" in failure
    assert "overdue since 2026-07-27" in failure


def test_r6_all_components_repaired(con):
    maintenance(con, 1, "2026-07-20", "jugaad", notes="radiator leak, temporary fix applied")
    maintenance(con, 2, "2026-07-25", "jugaad", notes="turbo awaaz, temporary fix applied")
    maintenance(con, 3, "2026-07-28", "replaced", notes="radiator replace kiya")
    maintenance(con, 4, "2026-07-31", "repaired", notes="turbo repair kiya")
    assert candidate_fails({"jugaad_stays_home": 7}, CANDIDATE, context(), con) is None


def test_r6_new_patch_after_repair_reopens_component(con):
    maintenance(con, 1, "2026-07-20", "jugaad", notes="turbo awaaz, temporary fix applied")
    maintenance(con, 2, "2026-07-25", "repaired", notes="turbo repair kiya")
    maintenance(con, 3, "2026-07-30", "jugaad", notes="turbo leak, temporary fix applied")
    failure = candidate_fails({"jugaad_stays_home": 7}, CANDIDATE, context(), con)
    assert "2026-07-30 (turbo)" in failure


def test_r9_uses_latest_events_not_database_row_order(con):
    issues = [
        ("TKT-OLD", "2026-07-01T10:00:00", CANDIDATE["canon"], "Apex Chemicals"),
        ("TKT-LATEST", "2026-07-03T10:00:00", CANDIDATE["canon"], "Apex Chemicals"),
    ]
    con.executemany("insert into tickets values(?,?,?,?)", reversed(issues))
    con.executemany(
        "insert into trips values(?,?,?,?)",
        [
            ("INVALID", "not-a-date", CANDIDATE["canon"], "COMPLETED"),
            ("CANCELLED", "2026-07-03T12:00:00", CANDIDATE["canon"], "CANCELLED"),
            ("BEFORE-LATEST", "2026-07-02T12:00:00", CANDIDATE["canon"], "COMPLETED"),
        ],
    )
    failure = candidate_fails(
        {"not_last_issue_with_client": "Apex Chemicals"}, CANDIDATE, context("2026-07-04T10:00:00"), con
    )
    assert "TKT-LATEST" in failure

    con.execute(
        "insert into trips values(?,?,?,?)",
        ("AFTER-LATEST", "2026-07-03T12:00:01", CANDIDATE["canon"], "COMPLETED"),
    )
    assert candidate_fails(
        {"not_last_issue_with_client": "Apex Chemicals"}, CANDIDATE, context("2026-07-04T10:00:00"), con
    ) is None


def test_r9_equal_timestamp_orders_issue_before_dispatch(con):
    con.execute(
        "insert into tickets values(?,?,?,?)",
        ("TKT-ISSUE", "2026-07-01T10:00:00", CANDIDATE["canon"], "Apex Chemicals"),
    )
    con.execute(
        "insert into trips values(?,?,?,?)",
        ("NEXT-DISPATCH", "2026-07-01T10:00:00", CANDIDATE["canon"], "COMPLETED"),
    )
    assert candidate_fails(
        {"not_last_issue_with_client": "Apex Chemicals"}, CANDIDATE, context("2026-07-02T10:00:00"), con
    ) is None

    con.execute(
        "insert into tickets values(?,?,?,?)",
        ("TKT-EQUAL-CURRENT", "2026-07-02T10:00:00", CANDIDATE["canon"], "Apex Chemicals"),
    )
    assert "TKT-EQUAL-CURRENT" in candidate_fails(
        {"not_last_issue_with_client": "Apex Chemicals"}, CANDIDATE, context("2026-07-02T10:00:00"), con
    )


def test_mixed_iso_times_and_shuffled_records_are_deterministic():
    assert parse_date("2026-08-01T05:30:00+05:30") == "2026-08-01T00:00:00"
    records = [
        {"ticket_id": "TKT-2", "created_at": "not-a-date"},
        {"ticket_id": "TKT-3", "created_at": "2026-08-02T00:00:00Z"},
        {"ticket_id": "TKT-1", "created_at": "2026-08-01 05:30:00+05:30"},
    ]
    expected = ["TKT-1", "TKT-3", "TKT-2"]
    assert [r["ticket_id"] for r in sorted(records, key=record_order)] == expected
    assert [r["ticket_id"] for r in sorted(reversed(records), key=record_order)] == expected


def test_out_of_range_numeric_timestamps_sort_and_quarantine(con):
    records = [
        {"ticket_id": ticket_id, "created_at": 10**30, "vehicle": "DL13XI5012", "origin_hub": "Delhi"}
        for ticket_id in ("TKT-Z", "TKT-A")
    ]
    expected = ["TKT-A", "TKT-Z"]
    assert parse_date(10**30) is None
    assert [r["ticket_id"] for r in sorted(records, key=record_order)] == expected
    assert [r["ticket_id"] for r in sorted(reversed(records), key=record_order)] == expected
    for record in records:
        process(con, record, "tickets.json", set(), [])
    assert con.execute("select count(*) from quarantine where reason='bad_date'").fetchone()[0] == 2
