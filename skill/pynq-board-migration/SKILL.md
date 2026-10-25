---
name: pynq-board-migration
description: Migrate a working PYNQ overlay project from board A to board B (worked example ZC702 -> ZC706) through five offline-gated steps - inventory what is board-coupled, retarget the part from a verified board table, regenerate (never hand-port) pin constraints, rebuild with routed timing signoff, and re-run the host regression. retarget_check.py gates XDC port compatibility and the .hwh target part offline; same part does NOT mean same board.
license: MIT
compatibility: Python 3.8+; stdlib only. Vivado needed for the rebuild step; board files for the target board. Works for any Zynq-7000 pair and, with the delta table filled from data sheets, across families.
metadata:
  author: fpgachina26 team (skill package)
  version: "1.0.0"
---

# Board Migration (A -> B): ZC702 -> ZC706 worked example

The bug class this kills: the "just change the part" migration. It keeps the
old XDC (pins for the wrong board), hand-copies the PS7 config (DDR/MIO for
the wrong memory), or reuses the old .bit/.hwh (host ip_dict for the wrong
design). Every one of these passes some stage of tooling and dies on - or
silently on - the new board. Migration failures are board-side by the time
anyone notices; this skill moves the discovery offline, into gates you can
run on a PC before the hardware is booked.

Born from the team's real mid-project board swap (ZC702 -> ZC706); written
to be board-agnostic so any A -> B pair works.

## When to use

- Your team switches boards mid-project (ours: ZC702 -> ZC706) and the
  overlay/RTL/host stack must come along.
- Porting an overlay to a second board to keep developing while the first
  is in the lab / being borrowed by another team.
- Reviewing someone else's "ported" project: run both gates before you
  trust it.

## Workflow - five gates, run in order

### G1. Inventory: board-coupled vs portable

Split the project into what the board touch and what it does not:

| Board-coupled (must be regenerated) | Portable (comes along as-is) |
|---|---|
| `part` property | RTL sources, BD logic, IP cores |
| XDC: PACKAGE_PIN / IOSTANDARD / board clocks | port NAMES and widths |
| PS7 config (DDR model, MIO, clocks) | host drivers, contract JSON |
| board preset / board files | golden data, testbenches, this package |

The one-line rule: **port names travel, pin locations never do.**

### G2. Retarget the part - from the table, not from memory

```
python scripts/retarget_check.py --boards
```

Prints the verified part for known boards (zc702 / zc706 / pynq-z2 /
zybo-z7-20) with the source for each. Note the two traps the table makes
visible: **pynq-z2 and zybo-z7-20 carry the IDENTICAL full part
(xc7z020clg400-1) yet are different boards** - pins, PS preset, and image
all differ; and zc702 vs pynq-z2 is the same silicon in a different
package (clg484 vs clg400) - logic fits identically, XDC does not travel.
Part equality never licenses you to reuse pins, PS preset, or image.

For a pair not in the table, fill the part from the target board's user
guide (UG954 for ZC706) and add a row with the source. Never guess a part
from the family name.

**Pre-board smoke (do this while waiting for the board):** one
`get_parts <target>*` call plus a one-minute AND-gate synthesis on the
target part validates part availability, license coverage, and toolchain
in a single shot - before the hardware is booked. We ran exactly this
gate for ZC706 on 2026-10-24: `get_parts xc7z045ffg900*` listed all
speed grades and a real `synth_design -part xc7z045ffg900-2` passed
(160 s), so the migration is unblocked ahead of the board arriving.

### G3. Constraints: regenerate, then gate the port set

Take the target board's master XDC (board file / user guide), keep your
old port NAMES, and let every LOC/IOSTANDARD come from the new board
source. Then gate the result offline:

```
python scripts/retarget_check.py --old-xdc old.xdc --new-xdc new.xdc
```

PASS requires every old port constrained in the new XDC. The report lists
relocations (expected), IOSTANDARD class changes (verify the bank), and
missing ports (hard fail - the classic half-done migration).

### G4. Rebuild with signoff

- apply the TARGET board preset to the PS7 block (DDR/MIO come from the
  board file - hand-copying from the old board is forbidden);
- regenerate IP output products, re-run synthesis + implementation;
- timing signoff from ROUTED timing (`report_timing_summary`), not synth
  estimates - pin moves change routing, see pitfall B4;
- export .bit + .hwh fresh. The old pair is dead weight; do not "patch".

### G5. Part gate + host regression, both offline first

```
python scripts/retarget_check.py --hwh overlay.hwh --expect-part <new part>
```

reads the PART the .hwh was actually exported for - catches exporting from
the wrong project/checkpoint. Then re-run the package regression that
needs no board: overlay_doctor static, generated contract tests, golden
compare. Only then book the board for the live smoke (overlay_doctor
--live, dma_smoke).

## Verification (hard gates)

- `retarget_check --old-xdc/--new-xdc`: exit 0 only if every old port is
  constrained in the new XDC; missing ports listed by name;
- `retarget_check --hwh --expect-part`: exit 0 only on exact part match;
  exit 2 with UNKNOWN if the .hwh carries no PART attribute (no silent
  pass on missing evidence);
- both gates exercised in tests/ (pass AND fail directions), T8a-T8e.

## Never do

- Never hand-port pin locations between boards - regenerate from the
  target board file and diff the PORT SET (G3), not the pin values.
- Never copy PS7 DDR/MIO settings across boards - apply the target
  board preset.
- Never reuse the old .bit/.hwh after a part change - the host ip_dict
  and the bitstream must be re-exported together or not at all.
- Never treat "same part" as "same board" (pynq-z2 vs zybo-z7-20 carry
  the identical part): part equality says nothing about pins, preset, or
  image.
- Never report timing from post-synth estimates on a migrated design -
  every pin moved, so routing changed (B4).

## Common errors

| Symptom | Trigger | Fix |
|---|---|---|
| `[Common 17-55] no ports matched` flood after part change | new XDC written for different port names | keep old port NAMES (G1 rule), re-gate G3 |
| `[DRC NSTD-1]/`unconstrained pins` warnings ignored | old XDC deleted, new one half-filled | G3 gate fails on missing ports - fix before synth, not after |
| board boots to nothing / DDR hang | PS7 config hand-copied from old board | G4: apply target board preset, re-export |
| overlay loads, ip_dict empty / base 0x0 | old .hwh next to new .bit (or vice versa) | G5 part gate + overlay_doctor static (timestamp/pair check) |
| `PART attribute not found` (exit 2) | .hwh from an unusual export path | verify the .hwh is a Vivado export; gate honestly stays UNKNOWN |
| passes on bench, fails at demo | routed timing never checked after pin moves | G4 signoff: report_timing_summary on the routed design |

## Resources

- `scripts/retarget_check.py` - offline gates (XDC port-compat diff,
  .hwh part check, verified board table); stdlib only
- `references/board-delta-method.md` - the A->B delta table method with
  the ZC702 -> ZC706 row set and sources (UG850 / UG954 / DS190)
- Sources: driven by the team's real ZC702 -> ZC706 mid-project swap;
  part numbers verified from AMD docs (UG850 for ZC702, UG954 for ZC706) and, for ZC702, the
  team's own Vivado 2026.1 synthesis runs. Gates validated offline in
  `tests/` (T8a-T8e).
