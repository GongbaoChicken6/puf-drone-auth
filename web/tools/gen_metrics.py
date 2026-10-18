#!/usr/bin/env python3
"""B4:竞赛指标四表生成器 —— 把散落的真实产物聚成 metrics 表(逐格来源徽章)。

用法(在 web/ 下):
    python tools/gen_metrics.py --repo-root <puf-drone-auth> --data-dir <沙箱>
输出(默认 web/.out/metrics/):core.md fpga.md security.md reliability.md README.md

纪律(与报告 §9 同源):每个格子必须带来源分级;没有真实来源的格子写「待板」并注明
替换条件,绝不补数。分级:STATIC=仓库静态文件/代码常量、LIVE=离线采样或会话门禁
实测、MODEL=黄金模型推演(非上板)、待板=需上板。
"""
from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path


def read_json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def table(rows):
    head = "| 指标 | 值 | 分级 | 来源 |\n|---|---|---|---|\n"
    return head + "".join(
        f"| {m} | {v} | **{g}** | {s} |\n" for m, v, g, s in rows)


def main() -> int:
    p = argparse.ArgumentParser(description="G5 指标四表生成(逐格来源)")
    p.add_argument("--repo-root", required=True, help="puf-drone-auth 仓库根")
    p.add_argument("--data-dir", default=None,
                   help="桥接运行态数据目录(默认 <repo-root>/data)")
    p.add_argument("--out", default=None, help="输出目录(默认 web/.out/metrics)")
    args = p.parse_args()

    repo = Path(args.repo_root).resolve()
    data = Path(args.data_dir).resolve() if args.data_dir else repo / "data"
    out = Path(args.out).resolve() if args.out else \
        Path(__file__).resolve().parents[1] / ".out" / "metrics"
    out.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")

    roc = read_json(data / "viz" / "roc_summary.json")
    hd = read_json(data / "viz" / "hd_sample.json")
    ml_a = read_json(repo / "data" / "ml_attack" / "exp_a_results.json")
    ml_b = read_json(repo / "data" / "ml_attack" / "exp_b_results.json")

    # FPGA:取 vivado_mcp 下最新 util_*.rpt
    lut = ff = lut_pct = ff_pct = None
    util_src = "build/vivado_mcp(无 util_*.rpt)"
    utils = sorted(repo.glob("build/vivado_mcp/util_*.rpt"),
                   key=lambda f: f.stat().st_mtime, reverse=True)
    for u in utils:
        text = u.read_text(encoding="utf-8", errors="replace")
        m1 = re.search(r"\| Slice LUTs\*?\s*\|\s*(\d+)[^|]*\|[^|]*\|[^|]*\|[^|]*\|\s*([\d.]+)", text)
        m2 = re.search(r"\| Slice Registers\s*\|\s*(\d+)[^|]*\|[^|]*\|[^|]*\|[^|]*\|\s*([\d.]+)", text)
        if m1 and m2:
            lut, lut_pct = m1.group(1), m1.group(2)
            ff, ff_pct = m2.group(1), m2.group(2)
            util_src = f"build/vivado_mcp/{u.name}(最新)"
            break

    thr = repo / "src" / "python" / "server" / "threshold.py"
    tau_txt = thr.read_text(encoding="utf-8") if thr.exists() else ""
    tp = re.search(r"TAU_PASS = (\d+)", tau_txt)
    tr = re.search(r"TAU_REJECT = (\d+)", tau_txt)
    tau_cell = f"{tp.group(1)} / {tr.group(1)}" if tp and tr else "?"
    flow_src = "docs/dashboards/project_flow.html(2026-10-12 手刷汇总)"

    st = None
    if hd and hd.get("intra") and hd.get("inter"):
        i, e = hd["intra"], hd["inter"]
        st = (sum(i) / len(i), max(i), sum(e) / len(e), min(e))

    stable = None
    tdir = data / "templates"
    if tdir.exists():
        sides = sorted(tdir.glob("*.stability.json"))
        if sides:
            sc = read_json(sides[0]) or {}
            mask = sc.get("7") or (next(iter(sc.values()), None) if sc else None)
            if isinstance(mask, str):
                stable = f"{mask.count('1')}/64"

    core = [
        ("认证延迟(全握手)", "~14 ms", "STATIC", flow_src),
        ("吞吐(次/秒)", "待板", "待板", "需上板实测(串口链路为瓶颈)"),
        ("认证成功率(loopback)", "S1–S7+golden 8/8 全过", "LIVE",
         "web/reviews/PhaseA执行记录.md 门禁(2026-10-17)"),
        ("认证成功率(板上)", "待板", "待板", "板卡 DS13 电源修复后实测"),
    ]
    fpga = [
        ("Slice LUTs", f"{lut} ({lut_pct}%)" if lut else "缺", "STATIC" if lut else "待板", util_src),
        ("Slice Registers(FF)", f"{ff} ({ff_pct}%)" if ff else "缺", "STATIC" if ff else "待板", util_src),
        ("WNS / 时钟频率", "待板(综合态 NA)", "待板", "timing_*.rpt 综合态无约束;实现后补"),
        ("判定阈值 TAU_PASS/TAU_REJECT", tau_cell, "STATIC",
         "src/python/server/threshold.py 代码常量(实读)"),
    ]
    sec = [("有效熵", "~44 bit", "STATIC", "docs/project_design.md(16 环信息论上限)")]
    if ml_a:
        acc = ml_a["accuracy"]["0.30"]["100000"]
        bay = ml_a["bayes_acc"]["0.30"]
        sec.append(("LR 建模攻击上限(α=0.30)",
                    f"{acc*100:.2f}%(贴 Bayes {bay*100:.2f}%)", "STATIC",
                    "data/ml_attack/exp_a_results.json(seed=42)"))
    if ml_b:
        ex = ml_b["aggregated"]["0.02"]["120"]["exact_rate"]
        sec.append(("排序重构(flip=0.02@120CRP)", f"精确率 {ex*100:.0f}% → CRP 轮换阈 ≥120",
                    "STATIC", "data/ml_attack/exp_b_results.json"))
    sec.append(("C2 重放拒止", "服务器窗 + 终端侧双路", "LIVE",
                "S3=REPLAY 门禁(PhaseA记录)+ tb GK 换电重放拒止"))

    rel = []
    if st:
        rel.append(("HD 分布(同设备 vs 跨设备)",
                    f"μ={st[0]:.2f}(max {st[1]}) / μ={st[2]:.2f}(min {st[3]}) bit",
                    "LIVE", "viz/hd_sample.json(离线采样;复现命令见文件内)"))
    if roc:
        rel.append(("ROC/EER", f"EER={roc['eer']*100:.2f}% · AUC={roc['auc']:.4f}"
                    f"(n={roc['n_intra']}+{roc['n_inter']})", "LIVE",
                    "viz/roc_summary.json(--roc 离线;参数见 params)"))
    else:
        rel.append(("ROC/EER", "未生成", "LIVE", "先跑 python tools/sample_hd.py --roc"))
    if stable:
        rel.append(("稳定掩码", stable, "STATIC", "templates sidecar(.stability.json)"))
    rel.append(("温度/电压 reliability", "见 viz 页 V6 曲线", "MODEL",
                "ROPairingPUF.measure 推演;导出件 desc 自带口径"))
    rel.append(("板上温漂实测", "待板", "待板", "DS13 修复后高低温实验"))

    files = {
        "core.md": "# Core 指标(时延/吞吐/成功率)\n\n" + table(core),
        "fpga.md": "# FPGA 资源与时序(ZC702 · XC7Z020)\n\n" + table(fpga),
        "security.md": "# Security 指标\n\n" + table(sec),
        "reliability.md": "# Reliability 指标\n\n" + table(rel),
        "README.md": (
            "# metrics(G5 指标表,生成于 " + stamp + ")\n\n"
            "四表:core / fpga / security / reliability。生成器 tools/gen_metrics.py"
            "(逐格来源;重跑即刷新,禁止手改数值)。\n\n"
            "分级:**STATIC**=仓库静态文件/代码常量 · **LIVE**=离线采样或会话门禁实测 · "
            "**MODEL**=黄金模型推演(非上板) · **待板**=需上板。\n"),
    }
    for name, text in files.items():
        (out / name).write_text(text, encoding="utf-8")
        print(f"[OK] {out / name}  ({len(text)}B)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
