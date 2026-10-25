#!/usr/bin/env python3
"""overlay_doctor.py - PYNQ Overlay static & live health check.

Static mode (works OFF the board, no pynq required):
    Parse the .hwh sidecar of an overlay, list every IP with its base
    address, address range, and key C_* parameters. Detects the classic
    "bit/hwh mismatch" and "missing hwh" failure modes before you ever
    touch the board.

Live mode (requires pynq ON the board):
    Load the overlay, dump ip_dict, and run a write-readback smoke test
    on every register listed in a register spec JSON.

Usage:
    python overlay_doctor.py --overlay-dir <dir>            # static check
    python overlay_doctor.py --bit <file.bit>               # static (finds .hwh next to it)
    python overlay_doctor.py --bit <file.bit> --live \
        --regspec regspec.json [--ip axi_gpio_0]            # board smoke test

Exit codes: 0 = PASS, 1 = FAIL (details printed), 2 = usage error.

License: MIT. Part of the generic PYNQ skill package.
"""
import argparse
import json
import os
import sys
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

# ---------------------------------------------------------------- helpers

def _text(node, tag):
    """Return the text of the first child <tag> of an Element, or None."""
    if node is None:
        return None
    child = node.find(tag)
    return child.text.strip() if child is not None and child.text else None


def _parse_registers(mod):
    """Extract the REGISTERS block a Vivado export attaches to AXI-Lite
    IPs (the same source pynq's hwh_parser uses to build register_map).

    Tag spellings vary slightly across Vivado versions, so both
    ADDRESSOFFSET / ADDRESS_OFFSET style names are accepted.
    """
    regs = []
    regsnode = mod.find("REGISTERS")
    if regsnode is None:
        return regs
    for r in regsnode.iter("REGISTER"):
        name = _text(r, "NAME")
        if not name:
            continue
        off = None
        for tag in ("ADDRESSOFFSET", "ADDRESS_OFFSET"):
            v = _text(r, tag)
            if v is not None:
                off = v
                break
        fields = 0
        fieldsnode = r.find("FIELDS")
        if fieldsnode is not None:
            fields = sum(1 for _ in fieldsnode.iter("FIELD"))
        regs.append({
            "name": name,
            "offset": off,
            "size": _text(r, "SIZE"),
            "access": _text(r, "ACCESS"),
            "fields": fields,
        })
    return regs


def parse_hwh(hwh_path):
    """Parse a PYNQ .hwh XML into a plain list of IP dicts.

    Tolerant by design: real .hwh files come from several Vivado versions
    and the exact nesting varies; we walk every MODULENODE wherever it
    sits and pull out what PYNQ itself uses (FULLNAME, MEMRANGES,
    PARAMETERS, and the REGISTERS block when present).
    """
    tree = ET.parse(hwh_path)
    root = tree.getroot()

    ips = []
    for mod in root.iter("MODULENODE"):
        fullname = _text(mod, "FULLNAME") or ""
        fullname = fullname.lstrip("/")
        if not fullname or fullname in ("iop_pmoda",):
            continue
        base = high = None
        memranges = mod.find("MEMRANGES")
        if memranges is not None:
            for mr in memranges.iter("MEMRANGE"):
                b = _text(mr, "BASEVALUE")
                h = _text(mr, "HIGHVALUE")
                if b is not None:
                    base, high = b, h
                    break
        params = {}
        paramsnode = mod.find("PARAMETERS")
        if paramsnode is not None:
            for p in paramsnode.iter("PARAMETER"):
                name = _text(p, "PARAMETERNAME")
                val = _text(p, "PARAMETERVALUE")
                if name:
                    params[name] = val
        # Skip pure infra IPs unless they carry a meaningful parameter set.
        ipstruct = None
        for tag in ("IPSTRUCT", "IPCOREREF"):
            v = _text(mod, tag)
            if v:
                ipstruct = v
                break
        ips.append({
            "fullname": fullname,
            "base": base,
            "high": high,
            "ipstruct": ipstruct,
            "parameters": params,
            "registers": _parse_registers(mod),
        })
    return ips


def static_check(bit_path):
    """Offline checks that need no board and no pynq install."""
    problems, warnings = [], []
    if not os.path.isfile(bit_path):
        return None, [f"bitstream not found: {bit_path}"], warnings

    hwh_path = os.path.splitext(bit_path)[0] + ".hwh"
    if not os.path.isfile(hwh_path):
        # PYNQ cannot build ip_dict without the .hwh - this is THE classic
        # "overlay loads but has no attributes" failure.
        hwh_alt = os.path.splitext(bit_path)[0] + ".tcl"
        if os.path.isfile(hwh_alt):
            warnings.append(
                f"no .hwh next to .bit but found {os.path.basename(hwh_alt)}; "
                "legacy .tcl metadata works but register_map needs .hwh "
                "(export with Vivado 2017.3+ / include .hwh in your delivery)")
        else:
            problems.append(
                "no .hwh sidecar found next to the .bit - pynq.Overlay will "
                "fail or expose an empty ip_dict. Re-export the overlay with "
                "both files from the same Vivado run.")
        return {"bit": bit_path, "hwh": None, "ips": []}, problems, warnings

    try:
        ips = parse_hwh(hwh_path)
    except ET.ParseError as e:
        problems.append(f".hwh is not valid XML ({e}) - corrupt export?")
        return {"bit": bit_path, "hwh": hwh_path, "ips": []}, problems, warnings

    if not ips:
        problems.append(
            ".hwh parsed but zero MODULENODE IPs extracted - wrong export "
            "(block design without addressable IP?) or unsupported format")

    mtime_delta = abs(os.path.getmtime(bit_path) - os.path.getmtime(hwh_path))
    if mtime_delta > 3600:
        warnings.append(
            f".bit and .hwh timestamps differ by {mtime_delta/60:.0f} min - "
            "if they were not exported in the same Vivado run, addresses "
            "may not match the bitstream (classic wrong-register-map bug)")

    return {"bit": bit_path, "hwh": hwh_path, "ips": ips}, problems, warnings


def live_smoke(bit_path, regspec, only_ip=None, download=True):
    """On-board smoke test. Returns list of per-register results."""
    try:
        from pynq import Overlay
    except ImportError:
        print("[ERROR] pynq is not installed - this mode must run ON the "
              "board (PYNQ image). Use --static for offline checks.")
        sys.exit(2)

    ol = Overlay(bit_path, download=download)
    ip_dict = ol.ip_dict
    print(f"overlay loaded: {len(ip_dict)} IP(s) in ip_dict")

    results = []
    targets = regspec.get("ips", regspec.get("targets", {}))
    for ip_name, spec in targets.items():
        if only_ip and ip_name != only_ip:
            continue
        if ip_name not in ip_dict:
            results.append({"ip": ip_name, "error": "not in ip_dict"})
            continue
        ip = getattr(ol, ip_name)
        try:
            rm = ip.register_map
        except AttributeError:
            results.append({"ip": ip_name,
                            "error": "no register_map (IP has no AXI-Lite?)"})
            continue
        regs = spec.get("registers", {})
        for reg_name, rw in regs.items():
            try:
                attr = getattr(rm, reg_name)
            except AttributeError:
                results.append({"ip": ip_name, "reg": reg_name,
                                "status": "MISSING"})
                continue
            if rw == "r":
                val = int(attr)
                results.append({"ip": ip_name, "reg": reg_name,
                                "status": "RO", "value": val})
                continue
            # write-readback on the fields we are allowed to touch
            cur = int(attr)
            test = cur ^ 1 if spec.get("xor_mode", True) else int(
                spec.get("test_value", 1))
            setattr(rm, reg_name, test)
            back = int(getattr(rm, reg_name))
            ok = back == test
            # restore
            setattr(rm, reg_name, cur)
            results.append({"ip": ip_name, "reg": reg_name,
                            "status": "PASS" if ok else "FAIL_RW",
                            "wrote": test, "read": back})
    return results


# ---------------------------------------------------------------- main

def main():
    ap = argparse.ArgumentParser(
        description="PYNQ overlay static/live health check")
    ap.add_argument("--overlay-dir", help="directory containing .bit+.hwh")
    ap.add_argument("--bit", help="path to the .bit file")
    ap.add_argument("--live", action="store_true",
                    help="run on-board register smoke test (needs pynq)")
    ap.add_argument("--regspec", help="JSON register spec for --live")
    ap.add_argument("--ip", help="restrict --live to this IP name")
    ap.add_argument("--json-out", help="also write results as JSON")
    ap.add_argument("--md-out", help="also write results as Markdown")
    args = ap.parse_args()

    if not args.bit and not args.overlay_dir:
        ap.error("need --bit or --overlay-dir")
    if args.live and not args.regspec:
        ap.error("--live requires --regspec (which IPs/registers to touch)")

    if args.overlay_dir:
        bits = [f for f in os.listdir(args.overlay_dir) if f.endswith(".bit")]
        if len(bits) != 1:
            print(f"[FAIL] expected exactly one .bit in {args.overlay_dir}, "
                  f"found {len(bits)}")
            sys.exit(1)
        args.bit = os.path.join(args.overlay_dir, bits[0])

    if not args.live:
        info, problems, warnings = static_check(args.bit)
        stamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
        report = {"tool": "overlay_doctor", "mode": "static",
                  "utc": stamp, "bit": args.bit,
                  "problems": problems, "warnings": warnings,
                  "ips": (info or {}).get("ips", [])}
        for w in warnings:
            print(f"[WARN ] {w}")
        for p in problems:
            print(f"[FAIL ] {p}")
        ips = report["ips"]
        print(f"\n{len(ips)} IP(s) parsed from "
              f"{os.path.basename((info or {}).get('hwh') or args.bit)}:")
        for ip in ips:
            base = ip["base"] or "-"
            nregs = len(ip.get("registers") or [])
            print(f"  - {ip['fullname']:<32} base={base:<12} "
                  f"type={ip['ipstruct'] or '?'} "
                  f"params={len(ip['parameters'])} regs={nregs}")
        verdict = "PASS" if not problems else "FAIL"
        print(f"\n[VERDICT] static check: {verdict}")
        if args.json_out:
            with open(args.json_out, "w", encoding="utf-8") as f:
                json.dump(report, f, indent=2)
        if args.md_out:
            with open(args.md_out, "w", encoding="utf-8") as f:
                f.write(md_static(report))
        sys.exit(0 if not problems else 1)

    with open(args.regspec, encoding="utf-8") as f:
        regspec = json.load(f)
    results = live_smoke(args.bit, regspec, only_ip=args.ip)
    bad = [r for r in results if r.get("status") not in ("PASS", "RO")]
    for r in results:
        print("  " + json.dumps(r, ensure_ascii=False))
    verdict = "PASS" if not bad else "FAIL"
    print(f"\n[VERDICT] live smoke: {verdict} "
          f"({len(results) - len(bad)}/{len(results)} ok)")
    if args.json_out:
        with open(args.json_out, "w", encoding="utf-8") as f:
            json.dump({"mode": "live", "results": results}, f, indent=2)
    sys.exit(0 if not bad else 1)


def md_static(rep):
    lines = ["# overlay_doctor static report", "",
             f"- utc: {rep['utc']}", f"- bit: `{rep['bit']}`",
             f"- verdict: **{('PASS' if not rep['problems'] else 'FAIL')}**",
             ""]
    if rep["warnings"]:
        lines += ["## Warnings", ""] + \
                 [f"- {w}" for w in rep["warnings"]] + [""]
    if rep["problems"]:
        lines += ["## Problems", ""] + \
                 [f"- {p}" for p in rep["problems"]] + [""]
    lines += ["## IPs", "",
              "| IP | base | type | #params | #regs |", "|---|---|---|---|---|"]
    for ip in rep["ips"]:
        lines.append(f"| {ip['fullname']} | {ip['base'] or '-'} | "
                     f"{ip['ipstruct'] or '?'} | {len(ip['parameters'])} | "
                     f"{len(ip.get('registers') or [])} |")
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    main()
