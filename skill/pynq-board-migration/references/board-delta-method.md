# Board Delta Method (A -> B)

How to build the delta table for ANY board pair, with the team's real
ZC702 -> ZC706 row set filled in as the worked example. Every cell carries
its source; cells we could not verify say so and name the document that
settles them. Copy this table for your own pair and fill it the same way.

## How to fill the table (the method)

1. One row per fact class that the migration touches - not a board manual
   dump. The rows below are the complete set for a PYNQ overlay project.
2. Each cell gets a source tag: 【本队实测】= we ran it (logs exist),
   【文献】= named official document, 【方法】= no single source, it is
   discipline. No cell stays sourceless.
3. Anything you cannot source within 10 minutes becomes a TODO row with
   the document named - it is answered by reading that document, not by
   guessing. FMC types below started as a TODO row until they were read
   out of UG850/UG954 - that is the intended lifecycle of a TODO row.

## ZC702 -> ZC706 delta table

| Fact class | ZC702 (old) | ZC706 (new) | Source |
|---|---|---|---|
| Part | xc7z020clg484-1 | xc7z045ffg900-2 | both 【本队实测】: ZC702 via Vivado 2026.1 synthesis runs; ZC706 via UG954 【文献】 AND get_parts + a real synthesis smoke on xc7z045ffg900-2 in our Vivado 2026.1 (2026-10-24, pre-board gate) |
| PL scale | 85K logic cells / 220 DSP | ~350K logic cells / 900 DSP | 【文献】DS190 Table 1 (Zynq-7000 family overview); verify exact numbers in the current DS190 |
| IO bank types | HP banks only | HR + HP banks | 【文献】DS190 (7z020 vs 7z045 row); matters when a migration touches 2.5V/3.3V-capable IO or DCI - check bank voltage before copying an IOSTANDARD |
| PS architecture | Zynq-7000 PS7 | same PS7 family | 【文献】UG585; PS code/MIO concepts port, board wiring does not |
| DDR / MIO config | board-specific | board-specific, DIFFERENT | 【方法】never hand-copied in either direction - apply the target board preset (G4); this row is why G4 exists |
| PL input clock | from board master XDC | from board master XDC | 【方法】never carried over; take the new board's clock line verbatim |
| FMC / expansion | 2x FMC, both LPC | 2x FMC: 1x HPC (J4, with GTX) + 1x LPC (J5) | 【文献】UG850 (ZC702) / UG954 (ZC706) FMC chapters; the LPC-only -> HPC upgrade is the expansion delta a mezzanine-card design cares about |
| PYNQ image | board-specific image | DIFFERENT board-specific image | 【方法】swap image with the board; host API is the stable surface (pynq.readthedocs); image availability for a given board/version - check the official image list, not folklore |
| .bit + .hwh pair | re-exported for the new part, together | same | 【方法】G5 part gate |
| Host code + contract + golden data | unchanged | unchanged | 【方法】G1 inventory - this is the payoff of the contract/golden skills |

## Same-part trap (read before "we only changed the board")

Two levels, both verified from vendor docs (2026-10):

1. **Identical FULL part, different boards.** pynq-z2 and zybo-z7-20 both
   carry **xc7z020clg400-1** - and share nothing board-level: different
   pin locations, different DDR population, different PS preset, different
   image. If your migration plan says "same part, skip the gates", this
   pair is the counterexample.
2. **Same silicon, different package.** zc702 (clg484) vs pynq-z2
   (clg400): the logic fits identically, but the packages expose different
   pins, so XDC constraints are NOT interchangeable in either direction.

`retarget_check.py --boards` prints all four boards on purpose: the two
identical-part rows adjacent, and the two zc702 rows showing the package
split.

## Cross-family notes (7-series -> UltraScale+)

The five gates are unchanged; the delta table grows rows: PS becomes
PSU/Xilinx UltraScale+ MPSoC (different boot/PYNQ image line), DMA cache
coherency differs (see pynq-dma-coherence/references/cache-coherency.md
UltraScale+ section), and HP/HR bank semantics are replaced by HD/HP
bank rules. Fill every added row from DS-series docs before running G3.
