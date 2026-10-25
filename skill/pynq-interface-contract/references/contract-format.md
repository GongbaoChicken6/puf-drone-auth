# Interface contract format

Load only when writing/editing a contract JSON.

## Top-level

Either a single contract object, or `{"contracts": [ ... ]}` to generate
drivers for several IPs in one call.

## Fields

```json
{
  "ip": "speck_cipher_0",          // REQUIRED - must equal the BD
                                    // instance name in the .hwh (the
                                    // generator warns on mismatch)
  "registers": [                    // REQUIRED (may be [])
    {
      "name": "ctrl",               // python-identifier-safe, unique
      "offset": 0,                  // byte offset from IP base (dec or "0x4")
      "width": 32,                  // informational (MMIO path is 32-bit)
      "access": "rw",               // "rw" | "r"  ("w"-only discouraged:
                                    //   cannot smoke it)
      "reset": 0,                   // informational, lands in driver doc
      "doc": "bit0=start ..."       // one-line doc, lands in driver
    }
  ],
  "operations": [
    {
      "name": "encrypt_one",        // becomes a driver method
      "doc": "kick one block",
      "writes": [{"reg": "ctrl", "value": 1}],
                                    // applied in order; value is a python
                                    // literal (int or "0x1")
      "wait_done": {                // optional poll
        "reg": "ctrl",              // register to poll
        "bit": 1,                   // bit index
        "timeout_ms": 100           // TimeoutError after this
      }
    }
  ]
}
```

## Conventions that keep contracts honest

1. Offsets are BYTES from the IP base address - same units as the Vivado
   Address Editor's offset column and `MMIO.write(offset, ...)`.
2. Register `name` must be a python identifier (it becomes
   `read_<name>`/`write_<name>` methods).
3. Don't mark side-effect registers (FIFO reset, DMA start, flash
   write-enable) as `"rw"` without realizing the generated smoke test
   will XOR-flip bit 0 of them. Options: mark them `"r"` and drive via
   an operation, or accept and delete the smoke test.
4. One contract per IP version; keep contracts in git next to the .hwh
   they were written against. The generator bakes in the .hwh's base
   address, so a regenerated diff reveals address drift.
5. HLS kernels: the register map is in the HLS-generated drivers
   (x<hlsip>.h / _hw.h) - ctrl @0x00, args in declaration order from
   0x10, on 0x8/0x10 alignment; copy from the generated header, not
   from memory.

## What the generator does with it

- `driver_<ip>.py`: class with `read_/write_<reg>` per register,
  `read_all()`, `smoke()` (write-readback), plus one method per
  operation (writes + optional poll loop).
- `test_<ip>.py`: FakeMMIO-injected logic tests (run anywhere) +
  `@pytest.mark.board` class that does the same smoke through real MMIO
  when `PYNQ_OVERLAY` env var is set on the board.
- Base address & span come from the .hwh (`--hwh`), overridable with
  `--base-addr` when no .hwh is at hand (prints a WARN - don't ship
  that mode).
