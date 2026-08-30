# Meridian Ops

Breakdown-to-resolution automation for Meridian Freight (400 trucks, North India): a pipeline that turns a breakdown ticket into a work order and a drafted client message, and a console where a dispatcher approves the message before it goes out. Reads are automatic, writes need a human.

## Quickstart

```bash
git clone <this repo> && cd synqai-hackathon
cp .env.example .env            # put your OPENAI_API_KEY in it (optional, see below)
./run.sh
```

## What you'll see

`run.sh` prints one line per stage, then `Meridian Ops: http://localhost:8000`. Open that.

- **Operations**: a map of North India with hubs, red pins for open breakdowns, dashed lines for the replacement truck's dispatch, and a feed of plain-English cards on the right.
- **Approvals**: an inbox of drafted client messages. Pick one, read "Why this decision" and the rule chips, press **Approve & send**. It moves to Sent with your name and time. Pressing it again does nothing.
- **Attention**: tickets the pipeline set aside (missing plate, missing hub, bad date) with an inline box to fill the gap and resubmit, and amber warnings for files it did not recognise.
- **Evaluator**: one button each for the double-run diff, the PII scan (with a test mode that plants a fake number), a random audit replay, and the precedence conflicts found in the data.

Every card has a **History** link: the audit timeline for that ticket, and a "View as graph" toggle.

Without an `OPENAI_API_KEY` everything still runs. Drafts come from a template and the audit log says so.

## Requirements

- macOS or Linux, [uv](https://docs.astral.sh/uv/) (it installs Python 3.12 itself)
- Node 20+ and npm (only for building the UI; `run.sh` does it)
- Internet for map tiles and, optionally, OpenAI

## Troubleshooting

| Symptom | Fix |
|---|---|
| `install uv first` | `curl -LsSf https://astral.sh/uv/install.sh \| sh`, then rerun |
| Blank page after rebuilding the UI | Hard refresh (Cmd+Shift+R). The old service worker is replaced on next load |
| `pii_scan: N leaks` and run.sh stops | Something wrote an unmasked number to outputs/, audit/ or logs/. That is the build failing on purpose. Run `python pii_scan.py` to see file and line |
| Port 8000 busy | `uv run uvicorn server:app --port 8001` |

## Project structure

| File | What it does |
|---|---|
| `run.sh` | One command: deps, ingest, pipeline, PII scan, double-run diff, UI build, server |
| `common.py` | Paths, PII regexes and `mask()`, canonical plate/client ids, hash ids, sqlite handle |
| `ingest.py` | Loads all seven sources into `store.sqlite` with entity resolution, precedence facts, masking |
| `pipeline.py` | `pipeline.py <ticket_file>`: validate, enrich, rules, replacement, work order, draft, audit |
| `rules.yaml` | Rajender's 11 rules as data, each with a transcript citation |
| `hubs.yaml` | Hub coordinates, regions, and the few planning constants |
| `llm.py` | The only OpenAI door: cache, temperature 0, PII firewall, fallbacks |
| `approve.py` | `approve.py TKT-0009 --by "Name"`: writes comms_sent once |
| `why.py` | `why.py TKT-0009`: the decision story in plain English |
| `query.py` | `query.py "question"`: store answers with citations, or "insufficient data" |
| `pii_scan.py` | Scans outputs/, audit/, logs/; exit 1 on any hit |
| `rerun_check.py` | Runs the pipeline twice, diffs every output byte |
| `evidence.py` | `make evidence`: CLI twin of the Evaluator page |
| `server.py` | FastAPI over the store, serves `ui/dist` |
| `ui/` | React + Vite + Tailwind console |
| `tests/` | The invariants as pytest |
| `llm_cache.sqlite` | Committed warm cache: a fresh clone reproduces the same drafts with no API call |
| `surprise_test.json` | A queue in a different shape (camelCase, DD-MM-YYYY, epoch) to prove change tolerance |

## Architecture

1. `ingest.py` reads the bundle and writes `store.sqlite`. Every plate becomes one canonical id; every source's spelling is kept for citations.
2. Facts that sources disagree on go through precedence (below). The loser is stored next to the winner, never dropped.
3. PII is masked in the loader. Raw values exist only in the roster CSV on disk and never enter the store.
4. `pipeline.py` maps whatever field names the ticket file uses onto the schema, validates, and quarantines what it cannot understand.
5. Per ticket it enriches from the store, evaluates `rules.yaml`, picks a replacement truck, and records every skipped candidate with the rule that skipped it.
6. Every decision is an insert-or-ignore under a sha256-derived id. Timestamps come from the ticket, never the clock.
7. The five output files are re-projected from the store in sorted order at the end of each run. Run two writes the same bytes because there is nothing new to write.
8. `approve.py` and the UI flip a draft to sent exactly once. A second approval is an audit line.
9. `pii_scan.py` runs after every pipeline run and fails the build on a hit.
10. `server.py` exposes the store; the UI has no data of its own.

## Precedence

`fleet_master > maintenance_log > tickets > emails > transcript`. Applied per fact. Conflicts found in this bundle: RJ43DD3546's year (an email says 2021, fleet_master says 2017 and wins) and CH67HY8613's odometer (a yard-check email says 92,000, the workshop log says 296,178 and wins). Fleet_master also has 18 duplicate plates with differing years; the first row wins and the rest are recorded. Odometer is a time series, so only the latest workshop reading counts as a fact.

## Rules

| Id | Rule | Where it bites |
|---|---|---|
| R1 | Shakti Cement is planned to 36h, not the contractual 48h | SLA flag on the work order |
| R2 | Oct to Feb, no BS4 truck on routes touching Delhi, Gurgaon, Faridabad, Noida | replacement filter |
| R3 | Within 50 km of the origin hub, the origin hub sends; beyond, nearest hub with an eligible truck | hub choice |
| R4 | Hill routes Nov to Feb: engine heater, no brake work in 30 days | replacement filter |
| R5 | Service overdue by more than 30 days grounds the truck, no exceptions | replacement filter |
| R6 | Jugaad fix starts a 7-day clock; truck stays in its home region until repaired | replacement filter |
| R7 | Orion Pharma: 2020 or newer, no overnight unrefrigerated hold | filter + flag |
| R8 | Vertex Ludhiana gate closes 18:00; late arrival becomes an 08:00 scheduled delivery, never a failure | ETA + flag |
| R9 | A truck with an issue on an Apex run does not go back to Apex next dispatch | replacement filter |
| R10 | Monsoon Jul to Sep, east of Lucknow: ETA +20%, quote the padded number | ETA |
| R11 | Under 6 months tenure, no solo night run | pair-driver flag |

One derivation to know about: fleet_master has no service-due date, so R5 uses last maintenance-log entry + 180 days (`hubs.yaml`), evaluated as of the ticket date.

## Where AI is used and where it deliberately is not

The model (`gpt-4o-mini` for extraction, `gpt-4o` for drafting) does four jobs and nothing else:

1. Classifying Hinglish maintenance notes that the regex pass could not (on this bundle the regex covered all 250 rows, so the path is tested but idle).
2. Drafting the client message from a fact sheet the pipeline hands it. Template fallback if the call fails, recorded in the audit log.
3. Summarising retrieved rows for `query.py`. Empty retrieval means "insufficient data", the model is never asked.
4. Proposing a canonical client for an unfamiliar name. The proposal is stored in `entity_map`; re-runs read the table.

Severity, eligibility, hub choice, truck choice, ETA and SLA math are code reading `rules.yaml`. The model never decides. Every call goes through `llm.py`: cached in `llm_cache.sqlite` by hash of model + prompt + input, temperature 0, inputs refused if they match a PII pattern, outputs masked on the way in.

## Feeding a new ticket file

```bash
uv run python pipeline.py path/to/new_file.json     # .json, .jsonl or .csv
```

or press **Process new file** in the top bar. Field names are mapped through a table of likely variants (`vehicleId`, `reg`, `plate`, `reportedAt`, epoch, `DD-MM-YYYY`, ...). Records that still cannot be mapped go to quarantine with an "unrecognized format" alert and nothing else changes. `surprise_test.json` is a worked example.

## What was deliberately cut

- No login. The approver is "Dispatcher on duty". First thing to add for real use.
- The "already assigned" check reads trips, and every trip in the bundle is from 2018, so it never fires for 2026 tickets. The code path stays.
- Distances are haversine times a road factor at a flat 40 km/h. Swap in OSRM if the ETAs need to be real.
- The knowledge graph is a radial SVG rather than a physics layout; fine for a dozen nodes.
- R10 never triggers on this data (no destination east of Lucknow). It is encoded anyway.
