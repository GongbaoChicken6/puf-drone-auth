---
name: pynq-dma-coherence
description: Correct DMA buffer discipline for PYNQ on Zynq - allocate/c_contiguous, flush before MM2S, invalidate after S2MM wait - plus a loopback smoke/bench script that localizes the failure class (stale cache vs dead stream vs misalignment) from the error pattern. Script logic validated offline (--dry-run + code review); board numbers must come from a real DMA loopback overlay on your board.
license: MIT
compatibility: Board mode: PYNQ image + overlay containing an AXI DMA (MM2S/S2MM) reachable as ol.<dma_name>. Dry-run mode: any PC with Python 3.8+.
metadata:
  author: fpgachina26 team (skill package)
  version: "1.0.0"
---

# PYNQ DMA & Cache Coherency

Zynq-7000 PS has no I/O coherency on the HP ports by default: the DMA
reads/writes DDR, while the A9 caches hold a stale copy. The bug looks
like "my accelerator returns garbage *sometimes*" and it is almost always
one of two ordering mistakes:

```python
# WRONG: read rx right after wait        (stale cache lines)
# WRONG: flush rx before transfer         (evicts nothing yet, garbage in)
# RIGHT:
tx.flush()                    # AFTER filling, BEFORE sendchannel.transfer
dma.sendchannel.transfer(tx)
dma.recvchannel.transfer(rx)
dma.sendchannel.wait(); dma.recvchannel.wait()
rx.invalidate()               # AFTER wait, BEFORE first read of rx
```

## When to use

- Any overlay with AXI DMA (HLS `hls::stream` kernels wired via DMA, video
  pipelines, data movers) on Zynq-7000 (ZC702, PYNQ-Z2, ...).
- When output data is "sometimes right", all-zero, or looks like an old
  buffer.
- Before benchmarking: throughput numbers without the flush/invalidate
  discipline are measuring cache hits, not the DMA.
- On UltraScale+ with CCI and dma-coherent device tree entries the
  discipline may be a no-op - but keeping it costs nothing and keeps the
  code portable.

## Workflow

1. Confirm the DMA is in the design and reachable:

```python
ol = Overlay("design.bit")
[n for n, d in ol.ip_dict.items() if "axi_dma" in d["type"].lower()]
```

2. Wire a loopback (MM2S -> S2MM directly, or through a passthrough
   stream core) - in the block design, this is two clicks and it is the
   only honest way to separate "DMA path broken" from "my kernel broken".

3. Run the smoke on the board:

```bash
python scripts/dma_smoke.py --bit design.bit --size-kb 1024 --iters 20 \
    --md-out dma_bench.md
```

4. Review the verdict: PASS prints throughput per direction; FAIL prints
   the first bad index + a failure-class hint.

5. Only after loopback PASS, move the DMA onto your real kernel and keep
   the same flush/invalidate calls around it.

## Verification (hard gates)

- loopback PASS over >= 20 iterations at >= 1 MiB (no single-shot "it
  worked once");
- `c_contiguous` asserted on every allocated buffer (script enforces);
- throughput reported from best-of-N with sizes that far exceed the L2
  cache (>= 512 KiB) so the number reflects DDR, not cache;
- any FAIL -> fix before touching kernel logic. Do not "retry until it
  passes".

## Never do

- Never read an S2MM buffer before `invalidate()` - even if it "looks
  fine" at small sizes (it fits in cache and lies to you).
- Never skip `flush()` because "the buffer is fresh" - fresh means the
  dirty lines are IN the cache, not in DDR.
- Never `flush()` after the transfer started or `invalidate()` while the
  DMA is still writing.
- Never benchmark at a single tiny size (cache-resident = fake bandwidth).
- Never conclude "DMA broken" from one failing pattern - use the error
  class table below.

## Common errors

| Pattern | Meaning | Where to look |
|---|---|---|
| scattered wrong 32-bit words, mostly right | cache discipline broken | flush/invalidate order (see above) |
| all zeros | stream never arrived | loopback wiring, dma.recvchannel transfer not issued, stream width mismatch |
| consistent off-by-N shift | length/stride mismatch | transfer(len) argument in bytes; tdata width |
| `MemoryError`/non-c-contiguous from allocate | buffer shape/dtype (e.g. slicing made a view) | allocate fresh contiguous, no strided views |
| first iter OK, later iters garbage | buffer freed/reused while DMA in flight | keep references until wait() returns |
| `recvchannel.wait()` never returns | kernel never asserts TLAST on the output stream | HLS: set `last` on the final beat (`.last()` / packet mode); S2MM in simple mode waits for TLAST forever |
| transfers above 16 KiB (2^14) misbehave/fail | AXI DMA simple-mode length cap (default max transfer 2^14 bytes) | widen the DMA IP's length field config in Vivado, or split into <= 16 KiB chunks in host code (PYNQ's DMA class wraps simple mode only) |
| DMA errors bit set (ESTR) | slave error / decoding error | address outside HP aperture, buffer > 4 GB issues, SG misconfig |

## Resources

- `scripts/dma_smoke.py` - loopback smoke + bench (board), `--dry-run`
  prints the exact sequence (PC).
- `references/cache-coherency.md` - why: A9 caches vs HP ports, what
  flush/invalidate actually do, links to UG585 ch. 5 & the Zynq US+
  CCI difference.
- Sources: cache failure modes consolidated from PYNQ docs
  (pynq.readthedocs.io - allocate/buffer and DMA pages), the PYNQ
  `pynq/lib/dma.py` source (TLAST + 2^14 length-cap behavior,
  source-checked 2026-10), Xilinx wiki "Zynq UltraScale+ MPSoC Cache
  Coherency" (contrast case), and the AMD doc-search results pulled
  during skill development; board drill pending our DMA overlay
  milestone (honestly labeled).
