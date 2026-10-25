# Why flush/invalidate: Zynq A9 caches vs PL DMA

Load only when you need the mechanics, not just the rule.

## The mechanism

Zynq-7000 PS: dual Cortex-A9 with L1 I/D caches and a shared L2 (PL310).
The AXI HP ports that the PL DMA uses attach BEHIND the L2, to DDR via
the DDR controller. Nothing in that path snoops the A9 caches (no I/O
coherency on Zynq-7000 HP ports). So:

- CPU writes land in L2 (dirty lines) and may not be in DDR yet. If the
  DMA reads DDR now, it gets stale bytes. `buffer.flush()` pushes dirty
  cache lines out to DDR. Do it AFTER filling, BEFORE `transfer()`.
- DMA writes go to DDR. The CPU's caches may hold stale lines for those
  addresses. If the CPU reads now, it may hit its stale cache. 
  `buffer.invalidate()` drops those lines so reads go to DDR. Do it
  AFTER `wait()`, BEFORE the first read of the buffer.

Cache line is 32 bytes on the A9: coherency operates at line granularity,
which is why a "neighboring variable" can also be affected - one more
reason buffers are allocated wholesale via `pynq.allocate`.

## What allocate() gives you

`pynq.allocate(shape, dtype)` returns a C-contiguous numpy array backed
by physically-contiguous memory, with `.flush()` / `.invalidate()`
(ioctl-based cache maintenance on the PYNQ image). Contiguity matters:
AXI DMA (simple mode) needs one physically contiguous buffer; strided
numpy views silently break that assumption - hence the `c_contiguous`
assert in dma_smoke.py.

## UltraScale+ difference (why portable code keeps the calls)

On Zynq UltraScale+ MPSoC with the CCI-400/500 and `dma-coherent` in the
device tree, PL accesses through the coherent slave port are snooped, and
flush/invalidate become unnecessary (no-ops). The Xilinx wiki page
"Zynq UltraScale+ MPSoC Cache Coherency" demonstrates the
`&axi_dma { dma-coherent; }` device-tree route. Keeping the calls costs
nothing there and keeps your host code correct on Zynq-7000, where they
are mandatory.

## Two non-cache gotchas that masquerade as cache bugs

Checked against the PYNQ DMA docs and `pynq/lib/dma.py` source (2026-10):

1. **TLAST or the transfer never ends.** AXI DMA S2MM in simple mode
   terminates a transfer only when the stream asserts TLAST. An HLS
   kernel that streams N beats but never sets `last` leaves
   `recvchannel.wait()` hanging forever - which looks like "DMA is
   stuck", not like a kernel bug. In HLS, carry `.last()` on the final
   beat of `hls::stream` output (or generate packet mode).
2. **The 2^14-byte length cap.** The DMA has a default maximum single
   transfer length of 2^14 bytes (16 KiB); PYNQ's `DMA` class wraps
   simple mode only. Bigger buffers either need the DMA IP's length
   field width raised in Vivado, or host-side splitting into <= 16 KiB
   chunks.

## Failure-class fingerprinting (used by dma_smoke.py)

| Fingerprint | Class |
|---|---|
| mostly correct, scattered wrong words | cache discipline (order wrong / missed) |
| all zeros | stream never connected (wiring/width/transfer not issued) |
| constant shift/offset | length or tdata width mismatch |
| first run good, later runs garbage | lifetime bug: buffer freed/reused while DMA in flight |
| wait() never returns | TLAST never asserted by the kernel (see above) |
| > 16 KiB transfer fails/truncates | simple-mode length cap (see above) |

## References

- Zynq-7000 TRM (UG585), ch. 5 (memory system) & ch. 9 (DMA/pl interfaces):
  https://docs.amd.com/r/en-US/ug585-zynq-7000-TRM
- PYNQ allocate/buffer docs:
  https://pynq.readthedocs.io/en/latest/pynq_package/pynq.buffer.html
- PYNQ DMA class docs (simple mode, transfer semantics):
  https://pynq.readthedocs.io/en/latest/pynq_package/pynq.lib/dma.html
- AXI DMA product guide (PG021):
  https://docs.amd.com/r/en-US/pg021_axi_dma
- Xilinx wiki, Zynq US+ cache coherency (contrast case):
  https://xilinx-wiki.atlassian.net/wiki/spaces/A/pages/18842098/
- These URLs were surfaced and cross-checked via the official AMD
  doc-search MCP (ross.amd.com/mcp/doc-search) during skill development.
