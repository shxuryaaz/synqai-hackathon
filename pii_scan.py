"""Scan outputs/, audit/, logs/ (plus any paths given) for phone, aadhaar or DL numbers. Exit 1 on any hit.
Run: python pii_scan.py [extra paths...]
"""
import sys
from pathlib import Path
from common import OUT, AUDIT, LOGS, PHONE, AADHAAR, DL

PATTERNS = {"phone": PHONE, "aadhaar": AADHAAR, "driving_licence": DL}


def scan(paths):
    hits = []
    for base in paths:
        files = [base] if Path(base).is_file() else sorted(Path(base).rglob("*"))
        for f in files:
            if not f.is_file():
                continue
            for n, line in enumerate(f.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
                for name, pat in PATTERNS.items():
                    if pat.search(line):
                        hits.append({"file": str(f), "line": n, "kind": name})  # never echo the value itself
    return hits


if __name__ == "__main__":
    paths = [Path(p) for p in sys.argv[1:]] or [OUT, AUDIT, LOGS]
    hits = scan([p for p in paths if p.exists()])
    for h in hits:
        print(f"LEAK {h['kind']} at {h['file']}:{h['line']}")
    print(f"pii_scan: {len(hits)} leaks in {', '.join(str(p) for p in paths)}")
    sys.exit(1 if hits else 0)
