---
name: pynq-golden-report
description: Golden-reference comparison plus Vivado utilization/timing report harvesting, producing one Markdown metrics file with honest verdicts (PASS/FAIL gates, synthesized-vs-routed labeling per UG906). Both scripts run on any PC. Validated offline: golden_compare on synthetic pass/fail CSV and binary vectors; collect_report on real Vivado 2026.1 utilization (-hierarchical included) and timing_summary reports from the team project.
license: MIT
compatibility: Python 3.8+. CSV/vector modes stdlib-only; binary mode uses numpy if installed. Reports from Vivado 2020+ text output.
metadata:
  author: fpgachina26 team (skill package)
  version: "1.0.0"
---

# Golden Compare + Metrics Auto-Report

Two scripts, one habit: every measured output gets compared against a
golden reference with hard gates, and every build gets its
utilization/timing numbers harvested into a single Markdown table. No
more "it looked correct" and no more screenshotting Vivado GUI tables.

## When to use

- After any board/sim run that produces numbers: compare against the
  golden vectors BEFORE believing them.
- After synthesis AND after implementation: collect metrics at both
  stages; the report labels synthesized timing as an estimate.
- At every project milestone: commit the generated .md next to the
  design so performance history is in git.
- In CI: both scripts exit non-zero on FAIL, wire them into any runner.

## Workflow

### Golden comparison

```bash
# CSV or whitespace vectors
python scripts/golden_compare.py --got out.csv --golden ref/golden.csv \
    --rtol 1e-4 --atol 1e-3 --md-out reports/cmp_run17.md

# raw binary (e.g. DMA output dumps)
python scripts/golden_compare.py --got out.bin --golden ref.bin --binary \
    --dtype int32 --shape 4096 --md-out reports/cmp_bin.md
```

Golden vectors come from: a Python/numpy model of the algorithm, a
reference implementation (e.g. cryptography test vectors), or a
previously-validated hardware run frozen as a tag in git. Never from
the current run.

### Metrics harvest

```bash
python scripts/collect_report.py --util utilization_w1.rpt \
    --hier-util utilization_hier.rpt --timing timing_w1.rpt \
    --design-name ro_ratio_top --md-out reports/metrics_w1.md \
    --json-out reports/metrics_w1.json
```

Point it at whatever `report_utilization` / `report_timing_summary`
emitted (the `-file` outputs - no GUI copy-paste).

## Verification (hard gates)

golden_compare PASS requires ALL of:

- every comparable cell within `atol + rtol*|golden|`;
- row AND column counts match (count mismatch = FAIL, not warning -
  silent truncation is what this exists to catch).

collect_report output must state:

- design state per source report (synthesized vs routed);
- if synthesized: an explicit "estimate only, signoff needs routed
  report (UG906)" warning - baked into the script;
- timing verdict printed only as data (WNS/TNS/...), and the MET
  verdict label only for routed reports.

## Never do

- Never loosen rtol/atol until it goes green without writing down why
  the old tolerance was wrong.
- Never compare against a golden file produced by the same build under
  test.
- Never quote synthesized WNS as a timing result; signoff is routed
  report_timing_summary (UG906 methodology).
- Never report average latency only - report min/median/max (scripts
  emit all three; keep them).
- Never let a FAIL exit code be ignored in CI.

## Common errors

| Symptom | Trigger | Fix |
|---|---|---|
| `[ERROR] could not convert ...` | CSV has non-numeric junk/header mis-detected | clean CSV; or use --binary for raw dumps |
| shape mismatch FAIL | producer wrote fewer samples (early exit, timeout) | look at producer logs first - this is a real bug, not a comparer bug |
| worst |err| huge but verdict PASS | tolerance too loose (rtol*|golden| dominates) | tighten rtol; check golden units (ns vs cycles!) |
| collect_report `[WARN] no utilization metrics parsed` | report from GUI "report" pane (no table) or non-English locale | use `-file` outputs of the Tcl commands |
| timing numbers all zero | design has no clocks constrained | add create_clock; a 0-row timing table is a constraint bug |
| hier table empty | depth-0 report or module names not matching regex | re-run with `-hierarchical_depth 2+` |

## Resources

- `scripts/golden_compare.py` - comparison with gates + md/json reports
- `scripts/collect_report.py` - Vivado report harvester
- `references/report-metrics.md` - which numbers to keep per milestone,
  and the estimate-vs-signoff rule with UG906/UG906 references.
- Sources: team practice (test-vector checking for the crypto kernel,
  report harvesting from build reports); scripts validated in `tests/`
  on both synthetic data and the project's real Vivado 2026.1 reports.
