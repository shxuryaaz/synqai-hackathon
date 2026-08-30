"""CLI twin of the /evaluator page. Run: make evidence"""
import json, sys
from common import db
import rerun_check, pii_scan, why
from common import OUT, AUDIT, LOGS

print("== 1. Double-run diff"); r = rerun_check.check(); print(f"   {len(r['differences'])} differences across {r['files_compared']} files")
print("== 2. PII scan"); hits = pii_scan.scan([p for p in (OUT, AUDIT, LOGS) if p.exists()]); print(f"   {len(hits)} leaks")
print("== 3. Audit replay"); con = db()
tid = con.execute("select ticket_id from work_orders order by ticket_id limit 1 offset (select count(*)/2 from work_orders)").fetchone()[0]
print("   " + why.story(tid).replace("\n", "\n   "))
print("== 4. Precedence conflicts (fleet_master > maintenance_log > tickets > emails > transcript)")
for f in con.execute("select * from facts where won=0 and source!=vs_source"):
    print(f"   {f['entity']} {f['key']}: {f['source']} said {f['value']}, {f['vs_source']} said {f['vs_value']} and wins ({f['ref']})")
sys.exit(1 if r["differences"] or hits else 0)
