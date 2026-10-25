#!/usr/bin/env python3
"""retarget_check.py - offline gates for board-to-board overlay migration.

Three independent checks (give any combination; worst exit code wins):

  --old-xdc A --new-xdc B   port-compatibility gate: every port constrained
                            in the old board XDC must be constrained in the
                            new board XDC (pin VALUES are expected to move;
                            the port SET must survive). Lists relocations,
                            IOSTANDARD class changes, missing ports.
  --hwh overlay.hwh
  --expect-part xc7z045ffg900-2
                            part gate: the PART recorded in the .hwh export
                            must equal the target board part. Exit 2 (not
                            silent pass) if the .hwh carries no PART attr.
  --boards                  verified part table (with source per row),
                            including the same-part-different-board trap.

Exit codes: 0 = all gates PASS, 1 = a gate FAILED, 2 = a gate UNKNOWN
(insufficient evidence - treat as "do not proceed", never as pass).

Stdlib only; runs on any PC without Vivado/board.
"""
import argparse
import os
import re
import sys

BOARDS = {
    "zc702": {
        "part": "xc7z020clg484-1",
        "note": "source: team's own Vivado 2026.1 synthesis runs (UG850 board)",
    },
    "zc706": {
        "part": "xc7z045ffg900-2",
        "note": ("source: UG954 (XC7Z045-2FFG900) + team-verified: get_parts "
                 "and a real synthesis smoke on this part passed in our "
                 "Vivado 2026.1 (2026-10-24, pre-board gate)"),
    },
    "pynq-z2": {
        "part": "xc7z020clg400-1",
        "note": ("TRAP: same SILICON as zc702 (7z020) but CLG400 package - "
                 "XDC/pins NOT interchangeable (AMD AUP / TUL PYNQ-Z2 specs)"),
    },
    "zybo-z7-20": {
        "part": "xc7z020clg400-1",
        "note": ("TRAP: IDENTICAL full part to pynq-z2 but a different board "
                 "- pins, PS preset, image all differ (Digilent reference)"),
    },
}

# set_property PACKAGE_PIN H17 [get_ports {led[0]}]   (braces or not)
_RE_PIN = re.compile(
    r"set_property\s+PACKAGE_PIN\s+(\S+)\s*\[?\s*get_ports\s+\{([^}]+)\}",
    re.IGNORECASE)
_RE_PIN_NB = re.compile(
    r"set_property\s+PACKAGE_PIN\s+(\S+)\s*\[?\s*get_ports\s+([^\s\{\]]+)",
    re.IGNORECASE)
_RE_IOSTD = re.compile(
    r"set_property\s+IOSTANDARD\s+(\S+)\s*\[?\s*get_ports\s+\{([^}]+)\}",
    re.IGNORECASE)
_RE_IOSTD_NB = re.compile(
    r"set_property\s+IOSTANDARD\s+(\S+)\s*\[?\s*get_ports\s+([^\s\{\]]+)",
    re.IGNORECASE)
_RE_CLK = re.compile(r"create_clock.*get_ports\s+\{?([^\}\]\s]+)", re.IGNORECASE)


def _strip_comments(text):
    return "\n".join(l for l in text.splitlines() if not l.strip().startswith("#"))


def parse_xdc(path):
    """-> {port_token: {"pin": str|None, "iostd": str|None}}, [clock ports]."""
    text = _strip_comments(open(path, encoding="utf-8", errors="replace").read())
    ports = {}

    def put(tok, key, val):
        tok = tok.strip()
        ports.setdefault(tok, {})[key] = val

    for val, tok in _RE_PIN.findall(text) + _RE_PIN_NB.findall(text):
        put(tok, "pin", val.upper())
    for val, tok in _RE_IOSTD.findall(text) + _RE_IOSTD_NB.findall(text):
        put(tok, "iostd", val.upper())
    clocks = [c.strip() for c in _RE_CLK.findall(text)]
    return ports, clocks


def base(tok):
    return tok.split("[")[0].strip()


def gate_port_compat(old_path, new_path):
    old, old_clks = parse_xdc(old_path)
    new, new_clks = parse_xdc(new_path)
    old_bases = {base(t) for t in old}
    new_bases = {base(t) for t in new}

    missing = sorted(old_bases - new_bases)
    relocated, same_pin, iostd_changed = 0, [], []
    for tok, od in sorted(old.items()):
        nd = new.get(tok)
        if not nd:
            continue
        if od.get("pin") and nd.get("pin"):
            if od["pin"] != nd["pin"]:
                relocated += 1
            else:
                same_pin.append(tok)
        if od.get("iostd") and nd.get("iostd") and od["iostd"] != nd["iostd"]:
            iostd_changed.append((tok, od["iostd"], nd["iostd"]))

    extra = sorted(new_bases - old_bases)
    print("[PORT-COMPAT] old XDC: %d constrained tokens (%d ports) | new XDC: "
          "%d tokens (%d ports)" % (len(old), len(old_bases), len(new),
                                    len(new_bases)))
    print("[PORT-COMPAT] pins relocated (expected on a board swap): %d" % relocated)
    for tok in same_pin:
        print("[SUSPECT ] %s kept the SAME pin %s across boards - verify this "
              "is really from the new board file" % (tok, old[tok]["pin"]))
    for tok, a, b in iostd_changed:
        print("[IOSTD   ] %s: %s -> %s (voltage class changed - verify bank)"
              % (tok, a, b))
    for tok in extra:
        print("[INFO    ] new-only port %s (added constraints are fine)" % tok)
    bad_clk = [c for c in old_clks if base(c) not in new_bases]
    for c in bad_clk:
        print("[MISSING ] clock port %s unconstrained in new XDC" % c)
    for m in missing:
        print("[MISSING ] port %s present in old XDC, unconstrained in new XDC"
              % m)

    ok = not missing and not bad_clk
    print("[VERDICT] port-compat: %s%s"
          % ("PASS" if ok else "FAIL",
             "" if ok else " (%d missing port(s), %d clock(s)) "
             % (len(missing), len(bad_clk))))
    return 0 if ok else 1


def gate_hwh_part(hwh_path, expect):
    text = open(hwh_path, encoding="utf-8", errors="replace").read()
    m = (re.search(r"<PARTITION>.*?PART=\"([^\"]+)\"", text, re.IGNORECASE | re.DOTALL)
         or re.search(r"PART=\"([^\"]+)\"", text, re.IGNORECASE))
    if not m:
        print("[PART-GATE] %s: no PART attribute found - cannot verify" % hwh_path)
        print("[VERDICT] part-gate: UNKNOWN (no PART attribute in .hwh)")
        return 2
    got = m.group(1).strip().lower()
    want = expect.strip().lower()
    print("[PART-GATE] .hwh says %r | expected %r" % (got, want))
    ok = got == want
    print("[VERDICT] part-gate: %s" % ("PASS" if ok else "FAIL (exported for "
                                       "the wrong part/project)"))
    return 0 if ok else 1


def print_boards():
    print("[BOARDS] verified part table for --expect-part / G2 retarget:")
    for name, b in sorted(BOARDS.items()):
        print("  %-8s %-18s %s" % (name, b["part"], b["note"]))
    return 0


def main():
    ap = argparse.ArgumentParser(
        description="Offline migration gates (port-compat / .hwh part / board table)")
    ap.add_argument("--old-xdc")
    ap.add_argument("--new-xdc")
    ap.add_argument("--hwh")
    ap.add_argument("--expect-part")
    ap.add_argument("--boards", action="store_true")
    a = ap.parse_args()

    rcs = []
    if a.boards:
        rcs.append(print_boards())
    if a.old_xdc or a.new_xdc:
        if not (a.old_xdc and a.new_xdc):
            sys.exit("--old-xdc and --new-xdc must be given together")
        rcs.append(gate_port_compat(a.old_xdc, a.new_xdc))
    if a.hwh or a.expect_part:
        if not (a.hwh and a.expect_part):
            sys.exit("--hwh and --expect-part must be given together")
        rcs.append(gate_hwh_part(a.hwh, a.expect_part))
    if not rcs:
        ap.print_help()
        sys.exit(64)
    sys.exit(max(rcs))


if __name__ == "__main__":
    main()
