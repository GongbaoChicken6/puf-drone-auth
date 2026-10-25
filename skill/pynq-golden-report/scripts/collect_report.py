#!/usr/bin/env python3
"""collect_report.py - turn Vivado text reports into one Markdown metrics file.

Parses:
  * report_utilization output        (Slice LUTs/FFs, BRAM, DSP, URAM, IO)
  * report_utilization -hierarchical (per-module table, Synthesized state ok)
  * report_timing_summary output     (WNS/TNS/WHS/THS per clock, verdict)

All parsing is regex-based and tolerant of Vivado 202x report cosmetics.
Runs anywhere Python runs - deliberately NOT tied to the board or to an
open Vivado session, so it can be used from CI or from the PS side.

Usage:
    python collect_report.py --util utilization.rpt \
        [--timing timing.rpt] [--design-name my_top] \
        [--md-out metrics.md] [--json-out metrics.json]

Golden rule baked in (UG906 methodology): if the report header says the
design state is "Synthesized", the timing numbers are ESTIMATES and this
tool labels them as such in the output. Signoff numbers come only from
routed reports.

Exit codes: 0 ok, 1 no usable data found, 2 usage error.

License: MIT. Part of the generic PYNQ skill package.
"""
import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone

UTIL_KEYS = [
    ("Slice LUTs", "LUT"),
    ("Slice Registers", "FF"),
    ("Block RAM Tile", "BRAM"),
    ("DSPs", "DSP"),
    ("URAM", "URAM"),
    ("Bonded IOB", "IO"),
]


def _header_field(text, key):
    # header lines look like "| Device       : xc7a35tcsg324-1 |" but the
    # trailing pipe is optional depending on report vintage
    m = re.search(r"^\|\s*" + re.escape(key) + r"\s*:\s*(.+?)\s*\|?\s*$",
                  text, re.M)
    return m.group(1).strip() if m else None


def parse_utilization(path):
    """Parse a report_utilization text file into a dict."""
    text = open(path, encoding="utf-8", errors="replace").read()
    out = {"file": os.path.basename(path),
           "tool": _header_field(text, "Tool Version"),
           "design": _header_field(text, "Design"),
           "device": _header_field(text, "Device"),
           "state": _header_field(text, "Design State"),
           "metrics": {}}

    for label, key in UTIL_KEYS:
        # | Slice LUTs |  699 | 0 | 0 | 20800 | 3.36 |
        m = re.search(
            r"^\|\s*" + re.escape(label) +
            r"\s*\|\s*(\d+)\s*\|\s*\d+\s*\|\s*\d+\s*\|\s*(\d+)\s*\|"
            r"\s*([\d.]+)\s*\|?\s*$", text, re.M)
        if m:
            out["metrics"][key] = {"used": int(m.group(1)),
                                   "available": int(m.group(2)),
                                   "util_pct": float(m.group(3))}
    return out


def parse_hier_utilization(path):
    """Parse -hierarchical utilization: per-module table.

    Real 2026.1 layout (pipe-table):
    | Instance | Module | Total LUTs | Logic LUTs | LUTRAMs | SRLs |
      FFs | RAMB36 | RAMB18 | DSP Blocks |
    Leading spaces in Instance encode hierarchy depth. We split cells
    instead of regexing so cosmetic column changes don't break parsing.
    """
    text = open(path, encoding="utf-8", errors="replace").read()
    rows = []
    for line in text.splitlines():
        s = line.rstrip()
        if not s.startswith("|") or not s.endswith("|"):
            continue
        cells = [c.strip() for c in s.strip("|").split("|")]
        if len(cells) < 10:
            continue
        nums = cells[2:10]
        if not all(re.fullmatch(r"\d+", c) for c in nums):
            continue
        inst = cells[0]
        if not inst or inst.lower() == "instance":
            continue
        # cells[2:10] = Total LUTs | Logic LUTs | LUTRAMs | SRLs | FFs |
        #               RAMB36 | RAMB18 | DSP Blocks
        rows.append({
            "instance": inst,
            "module": cells[1],
            "depth": len(line.split("|")[0]),  # leading-space width ~ depth
            "LUT": int(nums[0]), "FF": int(nums[4]),
            "BRAM": int(nums[5]) + int(nums[6]), "DSP": int(nums[7]),
        })
    return {"file": os.path.basename(path),
            "design": _header_field(text, "Design"),
            "device": _header_field(text, "Device"),
            "state": _header_field(text, "Design State"),
            "modules": rows}


def parse_timing(path):
    """Parse report_timing_summary: global WNS/TNS/WHS/THS + per-clock."""
    text = open(path, encoding="utf-8", errors="replace").read()
    out = {"file": os.path.basename(path),
           "design": _header_field(text, "Design"),
           "device": _header_field(text, "Device"),
           "state": _header_field(text, "Design State"),
           "global": None, "clocks": []}

    # Summary block: a header line containing "WNS(ns) ... TNS Failing
    # Endpoints ..." followed by a numeric row. Column count varies by
    # Vivado version (9 cols up to WPWS, 13 when TPWS cols are present),
    # so we locate the header then read all numbers from the next line.
    lines = text.splitlines()
    for i, ln in enumerate(lines):
        if "WNS(ns)" in ln and "TNS Failing Endpoints" in ln:
            # skip separator/dash lines after the header, take the first
            # line carrying the numeric summary row
            for j in range(i + 1, min(i + 4, len(lines))):
                nums = re.findall(r"-?\d+(?:\.\d+)?", lines[j])
                if len(nums) >= 9:
                    out["global"] = {
                        "WNS_ns": float(nums[0]), "TNS_ns": float(nums[1]),
                        "wns_failing": int(float(nums[2])),
                        "wns_total": int(float(nums[3])),
                        "WHS_ns": float(nums[4]), "THS_ns": float(nums[5]),
                        "whs_failing": int(float(nums[6])),
                        "whs_total": int(float(nums[7])),
                        "WPWS_ns": float(nums[8]),
                    }
                    break
            break

    # Per-clock rows (Intra Clock Table): "<clock name>  WNS TNS F T
    # WHS THS F T WPWS [TPWS F T]" - column count varies, clock names
    # may contain slashes. Tokenize: trailing numeric run of >= 9 is the
    # summary, leading tokens are the name. Period comes from the Clock
    # Summary table when present.
    periods = {}
    for cm in re.finditer(
            r"^\s*(\S+)\s+(?:Rise\s+)?(\d+(?:\.\d+)?)\s+"
            r"(?:\{[^}]*\}\s*)?No\s+Period\s+Change",
            text, re.M):
        periods[cm.group(1)] = float(cm.group(2))
    clock_summary = re.search(r"Clock Summary(.*?)(?:\n\n|\Z)", text, re.S)
    if clock_summary and not periods:
        for ln in clock_summary.group(1).splitlines():
            toks = ln.split()
            if len(toks) >= 2 and re.fullmatch(r"\d+(\.\d+)?", toks[1]):
                periods[toks[0]] = float(toks[1])

    section = re.search(r"Intra Clock Table(.*?)(?:Inter Clock Table|\Z)",
                        text, re.S)
    if section:
        for ln in section.group(1).splitlines():
            toks = ln.rstrip().split()
            if len(toks) < 10:
                continue
            # find trailing numeric run
            k = len(toks)
            while k > 0 and re.fullmatch(r"-?\d+(\.\d+)?", toks[k - 1]):
                k -= 1
            nums = toks[k:]
            name = " ".join(toks[:k])
            if len(nums) < 9 or not name or set(name) <= set("-=|"):
                continue
            out["clocks"].append({
                "clock": name, "period_ns": periods.get(name),
                "WNS_ns": float(nums[0]), "TNS_ns": float(nums[1]),
                "WHS_ns": float(nums[4]), "THS_ns": float(nums[5])})
    return out


def signoff_warning(rep):
    if rep and (rep.get("state") or "").lower().startswith("synth"):
        return ("Design State is Synthesized: timing above is an "
                "**estimate**. Signoff requires the routed "
                "report_timing_summary (UG906).")
    return None


def md_report(util, hier, tim, design_name):
    utc = datetime.now(timezone.utc).isoformat(timespec="seconds")
    name = design_name or (util or hier or tim or {}).get("design") or "?"
    dev = (util or hier or tim or {}).get("device")
    lines = ["# FPGA metrics auto-report", "",
             f"- utc: {utc}", f"- design: `{name}`",
             f"- device: {dev or '?'}", ""]
    if util and util["metrics"]:
        lines += ["## Utilization", "",
                  "| Resource | Used | Available | Util % |",
                  "|---|---|---|---|"]
        for label, key in UTIL_KEYS:
            if key in util["metrics"]:
                m = util["metrics"][key]
                lines.append(f"| {key} | {m['used']} | {m['available']} | "
                             f"{m['util_pct']} |")
        lines.append(f"\n_source: {util['file']} (state: {util['state']})_")
    if hier and hier.get("modules"):
        lines += ["", "## Utilization by hierarchy (top modules)", "",
                  "| Instance | Module | LUT | FF | BRAM | DSP |",
                  "|---|---|---|---|---|---|"]
        for r in hier["modules"][:15]:
            lines.append(f"| {r['instance']} | {r['module'] or '(top)'} | "
                         f"{r['LUT']} | {r['FF']} | {r['BRAM']} | "
                         f"{r['DSP']} |")
        if len(hier["modules"]) > 15:
            lines.append(f"\n_... {len(hier['modules']) - 15} more modules "
                         f"(see JSON output)_")
        lines.append(f"\n_source: {hier['file']} (state: {hier['state']})_")
    if tim:
        warn = signoff_warning(tim)
        if tim["global"]:
            g = tim["global"]
            lines += ["", "## Timing (global)", "",
                      "| WNS (ns) | TNS (ns) | WHS (ns) | THS (ns) | "
                      "WPWS (ns) |", "|---|---|---|---|---|"]
            lines.append(f"| {g['WNS_ns']} | {g['TNS_ns']} | {g['WHS_ns']} | "
                         f"{g['THS_ns']} | {g['WPWS_ns']} |")
            verdict = ("**TIMING MET (routed)**"
                       if g["WNS_ns"] >= 0 and g["WHS_ns"] >= 0
                       and (tim["state"] or "").lower().startswith("rout")
                       else ("timing met (estimate only)"
                             if g["WNS_ns"] >= 0 and g["WHS_ns"] >= 0
                             else "**TIMING VIOLATED**"))
            lines += ["", f"Verdict: {verdict}"]
        if tim["clocks"]:
            lines += ["", "## Timing per clock", "",
                      "| Clock | Period (ns) | WNS (ns) | TNS (ns) | "
                      "WHS (ns) | THS (ns) |", "|---|---|---|---|---|---|"]
            for c in tim["clocks"]:
                lines.append(f"| {c['clock']} | "
                             f"{c['period_ns'] if c['period_ns'] else '-'} | "
                             f"{c['WNS_ns']} | {c['TNS_ns']} | {c['WHS_ns']} "
                             f"| {c['THS_ns']} |")
        if warn:
            lines += ["", f"> {warn}"]
    lines.append("")
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser(
        description="Vivado utilization/timing reports -> Markdown metrics")
    ap.add_argument("--util", help="report_utilization output file")
    ap.add_argument("--hier-util", dest="hier",
                    help="report_utilization -hierarchical output file")
    ap.add_argument("--timing", help="report_timing_summary output file")
    ap.add_argument("--design-name")
    ap.add_argument("--md-out")
    ap.add_argument("--json-out")
    args = ap.parse_args()
    if not (args.util or args.hier or args.timing):
        ap.error("give at least one of --util/--hier-util/--timing")

    util = parse_utilization(args.util) if args.util else None
    hier = parse_hier_utilization(args.hier) if args.hier else None
    tim = parse_timing(args.timing) if args.timing else None

    if util and not util["metrics"]:
        print(f"[WARN] no utilization metrics parsed from {args.util}")
    if tim and not (tim["global"] or tim["clocks"]):
        print(f"[WARN] no timing numbers parsed from {args.timing}")

    ok = (util and util["metrics"]) or (hier and hier["modules"]) or \
         (tim and (tim["global"] or tim["clocks"]))
    md = md_report(util, hier, tim, args.design_name)
    print(md)
    if args.md_out:
        with open(args.md_out, "w", encoding="utf-8") as f:
            f.write(md)
    if args.json_out:
        with open(args.json_out, "w", encoding="utf-8") as f:
            json.dump({"util": util, "hier": hier, "timing": tim},
                      f, indent=2)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
