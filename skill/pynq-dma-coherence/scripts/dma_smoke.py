#!/usr/bin/env python3
"""dma_smoke.py - DMA loopback smoke + throughput bench + cache-coherency drill.

ON-BOARD tool (needs a PYNQ image with an overlay containing an AXI DMA in
loopback: MM2S->S2MM, either wired in the block design or via an HP port
test core). OFF the board it only supports --dry-run (prints the exact
call sequence it would run - useful to review before hardware time).

The cache discipline it enforces (the whole point of this skill):
  send:    fill buffer -> buffer.flush()          -> dma.send
  receive: dma.wait -> buffer.invalidate()        -> read buffer
Order matters both ways. Flushing an S2MM buffer before the DMA wrote it,
or reading an MM2S-destination without invalidating, gives stale/garbage
data that *sometimes* looks fine - the worst class of bug to debug.

Usage (on board):
    python dma_smoke.py --bit overlay.bit [--size-kb 1024] [--iters 20] \
        [--md-out dma_bench.md] [--json-out dma_bench.json]
Off board:
    python dma_smoke.py --dry-run

Exit codes: 0 PASS, 1 FAIL, 2 usage/environment error.

License: MIT. Part of the generic PYNQ skill package.
"""
import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone

CACHE_LINE = 32  # Zynq-7000 A9 cache line, bytes (used for messages only)


def dry_run(size_bytes, iters):
    print("planned sequence (on-board run does exactly this):")
    print(f"""
  from pynq import Overlay, allocate
  import numpy as np

  ol = Overlay("<bit>")
  dma = ol.axi_dma_0                       # name from ol.ip_dict

  for i in range({iters}):
      with allocate(shape=({size_bytes // 4},), dtype=np.uint32) as tx, \\
           allocate(shape=({size_bytes // 4},), dtype=np.uint32) as rx:
          tx[:] = np.arange({size_bytes // 4}, dtype=np.uint32) + i
          tx.flush()                       # PS cache -> DDR  (BEFORE send)
          dma.sendchannel.transfer(tx)     # MM2S
          dma.recvchannel.transfer(rx)     # S2MM
          dma.sendchannel.wait()
          dma.recvchannel.wait()
          rx.invalidate()                  # DDR -> PS cache (AFTER wait,
                                           #  BEFORE first read)
          assert (rx == tx).all()          # loopback golden check
""")


def run_board(bit, size_bytes, iters):
    try:
        import numpy as np
        from pynq import Overlay, allocate
    except ImportError as e:
        print(f"[ERROR] board run needs pynq+numpy on the PYNQ image: {e}")
        sys.exit(2)

    ol = Overlay(bit)
    dmas = [n for n, d in ol.ip_dict.items()
            if "axi_dma" in d.get("type", "").lower()]
    if not dmas:
        print("[FAIL] no axi_dma IP found in overlay ip_dict "
              f"({list(ol.ip_dict)}) - this script needs a DMA loopback "
              "design")
        sys.exit(1)
    dma = getattr(ol, dmas[0])
    print(f"using DMA: {dmas[0]}")

    n = size_bytes // 4
    timings, first_err = [], None
    for i in range(iters):
        tx = allocate(shape=(n,), dtype=np.uint32)
        rx = allocate(shape=(n,), dtype=np.uint32)
        try:
            if not tx.c_contiguous or not rx.c_contiguous:
                print("[FAIL] pynq.allocate returned non-c-contiguous "
                      "buffer - DMA would scatter; report as env bug")
                sys.exit(1)
            tx[:] = np.arange(n, dtype=np.uint32) + i
            # ---- the discipline: flush BEFORE send, invalidate AFTER wait
            tx.flush()
            t0 = time.perf_counter()
            dma.sendchannel.transfer(tx)
            dma.recvchannel.transfer(rx)
            dma.sendchannel.wait()
            dma.recvchannel.wait()
            t1 = time.perf_counter()
            rx.invalidate()
            if not (rx == tx).all():
                bad = int(np.argmax(rx != tx))
                first_err = {
                    "iter": i,
                    "first_bad_index": bad,
                    "got": int(rx[bad]), "expected": int(tx[bad]),
                    "hint": ("stale/garbage at scattered indices -> cache "
                             "discipline broken (flush/invalidate order); "
                             "all-zero -> DMA not transferring (check "
                             "loopback wiring / stream width); consistent "
                             "shift -> misaligned length or stride"),
                }
                break
            timings.append(t1 - t0)
        finally:
            del tx, rx

    result = {
        "tool": "dma_smoke", "bit": bit, "dma": dmas[0],
        "bytes": size_bytes, "iters": iters,
        "utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    if first_err:
        result["verdict"] = "FAIL"
        result["error"] = first_err
    elif not timings:
        result["verdict"] = "FAIL"
        result["error"] = "no iteration completed"
    else:
        best = min(timings)
        result["verdict"] = "PASS"
        result["stats_us"] = {
            "min": best * 1e6,
            "median": sorted(timings)[len(timings) // 2] * 1e6,
            "max": max(timings) * 1e6,
        }
        # effective unidirectional payload throughput (loopback moves the
        # buffer twice, so per-direction bytes = size)
        result["throughput_MBps"] = {
            "per_direction": size_bytes / best / 1e6,
            "loopback_total": 2 * size_bytes / best / 1e6,
        }
        print(f"PASS {len(timings)}/{iters} iters, "
              f"best={result['throughput_MBps']['per_direction']:.1f} MB/s "
              f"per direction ({size_bytes / 1024:.0f} KiB)")
    return result


def md(r):
    lines = ["# dma_smoke report", "", f"- utc: {r['utc']}",
             f"- overlay: `{r['bit']}`", f"- dma: {r.get('dma')}",
             f"- size: {r['bytes']} B, iters: {r['iters']}",
             "", f"## Verdict: **{r['verdict']}**", ""]
    if "stats_us" in r:
        s = r["stats_us"]
        lines += ["| min (us) | median (us) | max (us) |", "|---|---|---|",
                  f"| {s['min']:.1f} | {s['median']:.1f} | {s['max']:.1f} |",
                  "", f"throughput/direction: "
                  f"{r['throughput_MBps']['per_direction']:.1f} MB/s"]
    if "error" in r:
        lines += ["", "## Error", "", "```json",
                  json.dumps(r["error"], indent=2), "```"]
    return "\n".join(lines) + "\n"


def main():
    ap = argparse.ArgumentParser(
        description="DMA loopback smoke/bench with cache discipline")
    ap.add_argument("--bit", help="overlay .bit (board mode)")
    ap.add_argument("--size-kb", type=int, default=1024,
                    help="buffer size in KiB per iteration")
    ap.add_argument("--iters", type=int, default=20)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--md-out")
    ap.add_argument("--json-out")
    args = ap.parse_args()

    if args.dry_run:
        dry_run(args.size_kb * 1024, args.iters)
        return

    if not args.bit:
        ap.error("board mode needs --bit (or use --dry-run)")
    r = run_board(args.bit, args.size_kb * 1024, args.iters)
    print(json.dumps(r, indent=2))
    if args.md_out:
        with open(args.md_out, "w", encoding="utf-8") as f:
            f.write(md(r))
    if args.json_out:
        with open(args.json_out, "w", encoding="utf-8") as f:
            json.dump(r, f, indent=2)
    sys.exit(0 if r["verdict"] == "PASS" else 1)


if __name__ == "__main__":
    main()
