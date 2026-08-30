"""Render free tier has no disk. Snapshot the whole SQLite store into Neon after every write and restore it at boot.
ponytail: one bytea row (~4 MB); move the store to real Postgres if it passes ~50 MB."""
import os, sqlite3
import psycopg
from common import DB

URL = os.environ.get("DATABASE_URL")
DDL = "create table if not exists snapshots(name text primary key, data bytea not null, at timestamptz not null default now())"


def restore():
    """Overwrite the local store with the latest snapshot. Returns False when there is no Neon or no snapshot yet."""
    if not URL:
        return False
    with psycopg.connect(URL) as con:
        con.execute(DDL)
        row = con.execute("select data from snapshots where name='store'").fetchone()
    if not row:
        return False
    for suffix in ("-wal", "-shm"):
        DB.with_name(DB.name + suffix).unlink(missing_ok=True)
    DB.write_bytes(row[0])
    return True


def save():
    if not URL or not DB.exists():
        return
    src = sqlite3.connect(DB)
    try:
        data = src.serialize()   # consistent copy, WAL included
    finally:
        src.close()
    with psycopg.connect(URL) as con:
        con.execute(DDL)
        con.execute("insert into snapshots(name, data, at) values ('store', %s, now()) on conflict (name) do update set data = excluded.data, at = now()", (data,))
