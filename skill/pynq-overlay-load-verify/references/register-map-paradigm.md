# register_map vs MMIO paradigms on PYNQ

Load only when you need the details behind the SKILL.md workflow.

## The two idioms

```python
ol = Overlay("design.bit")          # parses design.hwh next to it

# 1) register_map (preferred when the IP has a driver binding)
rm = ol.my_accel_0.register_map
rm.CTRL = 0x1                        # by symbolic name
rm.CTRL.AP_START = 1                 # bitfield access (HLS-style)
v = int(rm.RESULT_LO)                # reads need int() -> plain number

# 2) MMIO (works for any address, no driver needed)
from pynq import MMIO
ipd = ol.ip_dict["my_accel_0"]
m = MMIO(ipd["phys_addr"], span=0x10000)
m.write(0x00, 1)                     # raw offsets in bytes
x = m.read(0x0c)
```

## What ip_dict gives you

`ol.ip_dict` (and `ol.ip_dict[name]`) is the ground truth for what the
.hwh says: `phys_addr` (base), `type` (VLNV, e.g.
`xilinx.com:ip:axi_gpio:2.0`), `drives`, `mem_id`, `state`. Print it
before guessing names:

```python
for name, d in ol.ip_dict.items():
    print(name, hex(d["phys_addr"]), d["type"])
```

`gpio_dict` and `interrupt_pins` exist in the same spirit. `ol.ip_dict`
names are the BD instance names - renaming an IP in the block design
renames the Python attribute.

## Which to use when

| Situation | Use |
|---|---|
| HLS-generated kernel (control/status/args) | register_map - names come from the HLS register map |
| custom RTL AXI-Lite peripheral | MMIO + a contract (see pynq-interface-contract skill) |
| quick interactive poke | MMIO one-liner |
| anything automated/repeatable | generated driver, never interactive pokes |

## Gotchas seen in practice

- `register_map` field names are case-sensitive and version-sensitive;
  print `rm` once and copy exact names (`print(ip.register_map)`).
- Setting a bitfield (`rm.CTRL.AP_START = 1`) reads-modifies-writes the
  register; if the hardware clears bits on read (W1C), use whole-register
  writes instead.
- Reading `register_map` properties returns view objects; `int()` them
  before comparing or JSON-serializing.
- `ol.download()` happens on Overlay() construction; re-download after
  re-programming the PL from another process or the addresses are stale
  from Linux's point of view (`Overlay(..., download=True)`).
- Two Overlays alive at once = last one wins on the PL; keep exactly one.

## References

- PYNQ docs, Overlay class: https://pynq.readthedocs.io/en/latest/pynq_libraries/overlay.html
- PYNQ docs, register_map API:
  https://pynq.readthedocs.io/en/latest/pynq_package/pynq.register_map.html
- PYNQ docs, MMIO:
  https://pynq.readthedocs.io/en/latest/pynq_package/pynq.mmio.html
