# Which numbers to keep, and when

Load only when setting up reporting for a milestone.

## Per-milestone minimum set

| Stage | Keep these | Source |
|---|---|---|
| post-synthesis | LUT/FF/BRAM/DSP (hier table too), WNS/TNS labeled ESTIMATE | `report_utilization`, `report_timing_summary` (state: synthesized) |
| post-implementation (routed) | same + WNS/WHS/TNS/THS/WPWS, per-clock table - THIS is signoff | same commands after route_design |
| board run | golden-compare verdict, min/median/max latency or throughput, iteration count | your run logs + golden_compare.py |

collect_report.py harvests the first two rows into one .md; keep the
habit "one metrics file per build tag", commit next to sources.

## The estimate-vs-signoff rule (UG906)

Timing numbers from a synthesized design are estimates: no placement, no
routing, no real interconnect delay. Signoff timing is the ROUTED
`report_timing_summary` (WNS >= 0 on all clocks and WPWS clean).
collect_report.py encodes this: routed reports can print "TIMING MET
(routed)"; synthesized ones print "timing met (estimate only)". When
writing your competition/project report, quote routed numbers - or say
explicitly that only synthesis estimates exist at that point.

## Golden-compare discipline

- Golden sources, in order of trust: official test vectors (crypto
  standards, dataset labels) > independent software model (numpy/python
  written from the spec, not from the RTL) > previously-frozen hardware
  run (tagged in git).
- Never generate the golden from the build under test in the same run -
  that only proves determinism, not correctness.
- Tolerances: start from the algorithm's expected precision (fixed-point
  word length, float32 eps * N accumulation), write the derivation in
  the md header comment. If you loosen a tolerance to pass, that fact
  must survive in git history and the report.
- Count mismatches fail hard on purpose: a truncated output (design
  stopped early) is a correctness bug even when every produced sample
  happens to match.

## Useful Vivado Tcl to standardize the harvest

```tcl
# run after synth_design / after route_design respectively
report_utilization       -file rpt/util_synth.rpt
report_utilization -hierarchical -hierarchical_depth 3 -file rpt/util_hier.rpt
report_timing_summary    -file rpt/timing.rpt
```

Keep the -file outputs (ASCII, diffable, locale-stable) rather than GUI
copies; the parser expects them.
