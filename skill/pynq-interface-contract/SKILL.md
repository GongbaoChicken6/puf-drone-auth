---
name: pynq-interface-contract
description: Generate a PYNQ host driver and pytest skeleton from an interface contract (IP name + registers + operations) cross-checked against the overlay's real .hwh base addresses. Generated tests run OFF-board against a FakeMMIO, so offset math and guards are verified on any PC; a board-marked test re-runs the same smoke on hardware. Codegen + generated-test flow validated offline with pytest.
license: MIT
compatibility: Python 3.8+; pytest for generated tests. Board-marked test needs pynq on the board. Works with any .hwh-exported overlay.
metadata:
  author: fpgachina26 team (skill package)
  version: "1.0.0"
---

# Interface Contract -> Host Code & Test Skeleton

The bug class this kills: host code where the offset, the width, or the
base address disagrees with the hardware, discovered only after you are
on the board. The contract makes the interface explicit, the generator
makes the driver boring, and the off-board tests make the register math
wrong-before-lunch instead of wrong-on-the-board.

## When to use

- You have an HLS/RTL kernel behind AXI-Lite in an overlay and need the
  PS-side driver (control regs, arguments, result regs).
- Multiple people write host code against your IP - hand them the
  generated driver, not a spreadsheet.
- You want CI (no hardware) to catch driver regressions.
- Starting a new overlay: write the contract FIRST, generate the test
  skeleton, and you have an executable spec before RTL exists.

## Workflow

1. Export the overlay (.bit + .hwh) from Vivado.

2. Write the contract next to it - one JSON per IP (or a list under
   "contracts"):

```json
{
  "ip": "speck_cipher_0",
  "registers": [
    {"name": "ctrl",     "offset": 0,  "access": "rw",
     "doc": "bit0=start bit1=done bit2=idle"},
    {"name": "key_lo",   "offset": 4,  "access": "rw"},
    {"name": "result_lo","offset": 12, "access": "r"}
  ],
  "operations": [
    {"name": "encrypt_one", "writes": [{"reg": "ctrl", "value": 1}],
     "wait_done": {"reg": "ctrl", "bit": 1, "timeout_ms": 100}}
  ]
}
```

3. Generate:

```bash
python scripts/gen_driver_stub.py --hwh overlay.hwh \
    --contract speck_contract.json --out-dir gen
```

The tool reads the REAL base address (and span) for `speck_cipher_0`
from the .hwh and bakes it into the driver; it warns if the IP name is
not found instead of silently using 0x0.

4. Run the generated tests off-board:

```bash
pytest gen/test_speck_cipher_0.py -v
```

4 of the tests are pure logic (registers exist, write-readback logic,
broken-register detection, read_all shape) and run on any PC.

5. On the board, run the same file with the marker:

```bash
PYNQ_OVERLAY=/home/xilinx/overlay.bit pytest gen/test_speck_cipher_0.py \
    -m board -v
```

6. When the hardware contract changes: update the JSON, regenerate with
   `--force`, and the diff between generated drivers IS the interface
   change log.

## Verification (hard gates)

- generator exits 0 with one driver + one test per contract IP;
- off-board pytest: all non-board tests green;
- board pytest: write-readback smoke green;
- driver `read_all()` keys == contract register names (tested).

## Never do

- Never hardcode base addresses in hand-written code after adopting this;
  they come from the .hwh (script) / ip_dict (runtime).
- Never mark a side-effect register (start bits, FIFO resets) as plain
  "rw" without thinking about the smoke test flipping it.
- Never edit the generated test to make it pass; fix the contract or the
  hardware.
- Never trust the contract over the .hwh: if names disagree, the .hwh is
  the truth (the generator enforces this for base addresses).

## Common errors

| Symptom | Trigger | Fix |
|---|---|---|
| `[WARN] ip not found in .hwh` | contract IP name != BD instance name | copy exact name from overlay_doctor static output |
| base 0x0 in driver | no --hwh given / name mismatch | pass --hwh; fix name; or --base-addr |
| board smoke fails all regs | same causes as overlay-load-verify failures | run overlay_doctor --live first |
| off-board tests fail on read_all shape | contract edited but driver not regenerated | regenerate with --force |
| TimeoutError from wait_done | done bit never sets | kernel not started/clocked; check bit index - contract bit vs RTL bit order |

## Resources

- `scripts/gen_driver_stub.py` - generator (stdlib only)
- `references/contract-format.md` - full field reference + conventions
  (offsets in bytes, access r/rw, wait_done semantics)
- Sources: pattern distilled from the team's PUF terminal driver work
  (hand-written MMIO offsets drifted from RTL twice) and the official
  Ross skill style of contract-first verification; codegen validated in
  `tests/` with a synthetic HLS-style IP contract.
