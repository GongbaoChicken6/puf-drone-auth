#!/usr/bin/env python3
"""V1「HD 双系列直方图」的离线采样器 —— 把 200 个 CRP 的双系列汉明距落盘。

为什么要有这个脚本(而不是让桥接每次都现算):
  1. **可引用**。报告 §9 的溯源矩阵要求页面上每个数字都能指回来源。现场采样出的
     直方图每刷新一次都略有不同,没法写进文档对账;落盘样本是一个固定文件,可以
     写进报告、可以被 §13 验收单逐值比对。
  2. **首屏快**。viz 页每次打开都要等一轮 200×2 的测量 + Speck 计算;有样本时
     直接读文件。
  3. 桥接的 /api/viz/hd 缺省优先消费本脚本的产物,**?fresh=1 才现场重采**。
     故本脚本不跑,页面照样能用(退回现场采样),不是必需步骤。

样本必须与**两端输入**都匹配,故落盘时记下两个指纹(实现均与桥接共用一份 ——
见 web_bridge.templates_sig / freqs_sig 的注释:两侧各写一份的话,签名对不上会
导致样本被静默弃用且毫无报错):
  - templates_sig:该 tid 的种子集合。跑过 S6 注册换了种子后样本作废;
  - device_sig:器件频率向量(ROPairingPUF freqs)的哈希。只换模板不换器件时它
    看不出问题 —— 状态文件被删或重建时 freqs 会重新随机,而种子集合可以一字未改,
    只有这一项能把样本判死。
桥接读到样本时两端都校,任一不符就自动弃用、退回现场采样,页面不会拿旧输入量出的
分离度冒充当前值。反过来,本脚本自己也**必须**从状态文件取回频率向量
(load_device_freqs):新造的 SimulatedTerminal 与模板登记的器件无关,直接量会得
到一对完全重叠的谱。

用法(在 web/ 下):
    python tools/sample_hd.py                                  # 缺省 tid 7、n 200
    python tools/sample_hd.py --terminal-id 9 --n 300
    python tools/sample_hd.py --data-dir .dev-data             # 开发态沙箱
    python tools/sample_hd.py --out D:/tmp/hd.json             # 另存一份(如交报告)
"""
from __future__ import annotations

import argparse
import json
import os
import random
import secrets
import sys
from datetime import datetime, timezone
from pathlib import Path

# 复用桥接的模块引导与签名实现 —— 刻意不复制这几段代码
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "bridge"))
from web_bridge import (  # noqa: E402
    DataDir,
    freqs_sig,
    load_server_modules,
    resolve_repo_root,
    templates_sig,
)

# 与桥接 _do_viz_hd 保持一致:200 个种子、每终端一条真品条 + 一条冒名条
DEFAULT_N = 200
DEFAULT_TID = 7


def load_device_freqs(data_dir: Path, tid: int) -> list[int]:
    """取回桥接落盘的该终端 PUF 频率向量(ROPairingPUF freqs)—— 没有它,量出来
    的根本不是「真品」。

    SimulatedTerminal 的 freqs 是每进程随机的(构造函数),新建的实例与模板表里
    登记的器件**毫无关系**。若照新实例直接量,两条谱会完全重叠(本机实测 Δμ≈0.2),
    而脚本照样吐出一份格式完全正确的 JSON —— 一个看不出问题的错数,进报告也不需要
    经过任何一道会报错的关卡。桥接自己也必须做同一件事才认得自己的模板,见
    web_bridge._do_bootstrap 的「freqs 再水化,必须早于任何 auth/enroll」。

    与桥接的一处**有意分歧**:桥接遇到「有模板、无持久 freqs」只发一条 warn 就继续
    (它还得服务别的终端,不跑到底代价更大);本脚本直接退出 —— 它的全部产出就是
    一个打算被引用的数字,不存在「勉强跑完」这个选项。
    """
    state_json = DataDir(data_dir).state_json
    try:
        raw = json.loads(state_json.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        raise SystemExit(
            f"[ERROR] 读不到桥接状态文件:{state_json}({e})\n"
            f"        先启动一次桥接 —— 它会 bootstrap 演示终端并把 freqs 落盘")
    if raw.get("schema") != "puf-drone-auth/web-bridge/v2":
        raise SystemExit(
            f"[ERROR] 状态文件 schema={raw.get('schema')!r},需 v2(freqs)。\n"
            f"        旧版(v1/secret_hex)已不兼容 —— 重启一次桥接让其迁移并重注册")
    rec = (raw.get("terminals") or {}).get(str(tid)) or {}
    freqs = rec.get("freqs")
    if not freqs:
        raise SystemExit(
            f"[ERROR] 状态文件里没有终端 {tid} 的 freqs:{state_json}\n"
            f"        没有它,新造的 SimulatedTerminal 与模板登记的不是同一个器件,\n"
            f"        两条谱会完全重叠,而输出仍然格式正确、毫无异常。\n"
            f"        先启动一次桥接,或选一个已经 bootstrap 过的 --terminal-id")
    if not isinstance(freqs, list) or len(freqs) != 16:
        raise SystemExit(
            f"[ERROR] freqs 应为 16 个整数,得到 {str(freqs)[:60]} —— 状态文件可能被"
            f"改过,或写它的不是本桥接")
    try:
        return [int(f) for f in freqs]
    except (TypeError, ValueError) as e:
        raise SystemExit(f"[ERROR] freqs 含非整数:{e}")


def sample(mods, templates, tid: int, n: int, freqs: list[int]) -> tuple[list[int], list[int]]:
    """返回 (intra, inter) —— 该器件自身 vs 模板、另一器件 vs 同一批模板。

    种子从模板表里抽(而不是凭空生成):HD 的定义是「响应与**已登记模板**的距」,
    拿一个没有模板的种子去量,分母根本不存在。故 n 的上限就是该终端的模板数。

    可复现性要分两半说清楚:intra 的**理想响应**由 (secret, seed) 唯一决定
    (main.py:127 ideal_response 是纯函数),故注入密钥后逐种子可比对;但两侧都叠加
    了逐位随机翻转的测量噪声(respond 里的 _rng),所以逐值复现做不到 —— 这个 JSON
    的价值是「一份固定的、可写进文档的产物」,不是「每次跑都一模一样」。
    inter 侧的冒名器件每次都是新的随机 secret(与桥接现场采样同款),刻意不做成定值:
    钉死一个冒名密钥等于把分离度押在某一次抽样的运气上,看分布才是要看的。
    """
    rows = templates.templates.get(str(tid))
    if not rows:
        raise SystemExit(
            f"[ERROR] 终端 {tid} 没有模板(模板表里没这一项)\n"
            f"        先在 console 页跑一次 S6 注册,或换 --terminal-id")

    seed_hexes = sorted(rows)
    if n > len(seed_hexes):
        print(f"[WARN] 模板只有 {len(seed_hexes)} 个种子,--n {n} 已收敛为 {len(seed_hexes)}")
        n = len(seed_hexes)
    # 打散后取前 n 个:模板表是按注册顺序追加的,直接切片会系统性地偏向早期的种子
    secrets.SystemRandom().shuffle(seed_hexes)
    seeds = [bytes.fromhex(s) for s in seed_hexes[:n]]

    genuine = mods.SimulatedTerminal(tid, freqs=freqs)   # 再水化 —— 决定 intra 是不是真品
    impostor = mods.SimulatedTerminal(-1 - tid)     # 与桥接同款:一个完全不同的器件
    intra = templates.hamming_distances(tid, seeds, genuine.respond(seeds))
    inter = templates.hamming_distances(tid, seeds, impostor.respond(seeds))
    return list(intra), list(inter)


def sample_roc(mods, templates, tid: int, freqs: list[int],
               impostors: int, seed: int) -> tuple[list[int], list[int], dict]:
    """B3:ROC/EER 大样本 —— intra 用**全部**模板种子(而非抽样 200);inter 由 K 个
    确定性冒名器件(random.Random(seed) 生成频率向量)在同一批种子上量出后池化,
    杜绝「把分离度押在某一次抽样的运气上」。应答翻位噪声仍随机(与协议口径一致),
    已在 params 里如实声明 —— 本文件的定位是「固定的、可写进文档的产物」。"""
    rows = templates.templates.get(str(tid))
    if not rows:
        raise SystemExit(f"[ERROR] 终端 {tid} 没有模板 —— 先跑 S1/S6 注册")
    seeds = [bytes.fromhex(s) for s in sorted(rows)]
    genuine = mods.SimulatedTerminal(tid, freqs=freqs)
    intra = list(templates.hamming_distances(tid, seeds, genuine.respond(seeds)))
    rng = random.Random(seed)
    inter: list[int] = []
    for i in range(impostors):
        imp_freqs = [rng.randint(3100, 9600) for _ in range(16)]
        imp = mods.SimulatedTerminal(-1 - tid - i, freqs=imp_freqs)
        inter.extend(templates.hamming_distances(tid, seeds, imp.respond(seeds)))
    params = {
        "impostors": impostors, "impostor_seed": seed, "n_seeds": len(seeds),
        "noise": "应答翻位噪声随机(与协议口径一致);冒名器件频率由 seed 确定性生成",
        "freq_range": "3100..9600(ROPairingPUF.DEFAULT_FREQ_MIN/MAX)",
    }
    return intra, inter, params


def roc_summary(intra: list[int], inter: list[int]) -> dict:
    """阈值扫掠 0..64:FAR=冒名被接受率(HD<=t),FRR=真品被拒绝率(HD>t)。
    EER 取 FAR/FRR 交叉点(段内线性插值);AUC=P(intra<inter)+0.5*P(=)，
    HD 越小越接受，故 AUC 即「真品得分优于冒名」的概率。"""
    taus = list(range(0, 65))
    ni, ne = len(intra), len(inter)
    far = [sum(1 for h in inter if h <= t) / ne for t in taus]
    frr = [sum(1 for h in intra if h > t) / ni for t in taus]
    eer = min(max(far[-1], frr[-1]), 1.0)
    for i in range(len(taus)):
        if frr[i] <= far[i]:
            if i == 0:
                eer = (far[0] + frr[0]) / 2
            else:
                d1, d2 = far[i - 1] - frr[i - 1], far[i] - frr[i]
                eer = (far[i] + frr[i]) / 2 if abs(d1 - d2) < 1e-12 else \
                    far[i - 1] + (far[i] - far[i - 1]) * (d1 / (d1 - d2))
            break
    gt = sum(1 for x in intra for y in inter if x < y)
    eq = sum(1 for x in intra for y in inter if x == y)
    return {"taus": taus, "far": far, "frr": frr,
            "eer": round(eer, 6), "auc": round((gt + 0.5 * eq) / (ni * ne), 6)}


def mean(xs: list[int]) -> float:
    return sum(xs) / len(xs) if xs else 0.0


def main() -> int:
    p = argparse.ArgumentParser(description="V1 HD 双系列离线采样(落盘供 /api/viz/hd 消费)")
    p.add_argument("--repo-root", default=None,
                   help="组员仓库根(默认:本文件上两级;须含 src/python/server)")
    p.add_argument("--data-dir", default=None,
                   help="运行态数据目录(默认 <repo-root>/data;开发态指到本地沙箱)")
    p.add_argument("--terminal-id", type=int, default=DEFAULT_TID,
                   help=f"采样终端(默认 {DEFAULT_TID})")
    p.add_argument("--n", type=int, default=DEFAULT_N,
                   help=f"种子数(默认 {DEFAULT_N},上限为该终端的模板数)")
    p.add_argument("--out", default=None,
                   help="输出路径(默认 <data-dir>/viz/hd_sample.json)")
    p.add_argument("--roc", action="store_true",
                   help="B3:ROC/EER 大样本模式 —— intra 用全部模板种子,inter 由 K 个确定性冒名器件池化,并额外出 roc_summary.json")
    p.add_argument("--impostors", type=int, default=8,
                   help="ROC 模式冒名器件数(默认 8)")
    p.add_argument("--roc-seed", dest="roc_seed", type=int, default=42,
                   help="冒名器件频率向量生成种子(默认 42,与 ML 实验同值便于对账)")
    p.add_argument("--roc-out", dest="roc_out", default=None,
                   help="ROC 摘要输出路径(默认 <data-dir>/viz/roc_summary.json)")
    args = p.parse_args()

    repo_root = resolve_repo_root(args.repo_root)
    data_dir = Path(args.data_dir).resolve() if args.data_dir else repo_root / "data"
    out = Path(args.out).resolve() if args.out else data_dir / "viz" / "hd_sample.json"

    templates_json = data_dir / "templates" / "templates.json"
    if not templates_json.exists():
        raise SystemExit(
            f"[ERROR] 模板表不存在:{templates_json}\n"
            f"        先启动一次桥接(它会 bootstrap 演示终端),或指对 --data-dir")

    mods = load_server_modules(repo_root)
    templates = mods.TemplateDB(str(templates_json))
    sig = templates_sig(templates, args.terminal_id)

    # 器件频率向量必须在建终端之前取到 —— 取不到就退出,不留「看起来量过了」的样本
    freqs = load_device_freqs(data_dir, args.terminal_id)

    roc_params = None
    if args.roc:
        intra, inter, roc_params = sample_roc(
            mods, templates, args.terminal_id, freqs,
            max(1, args.impostors), args.roc_seed)
        summary = roc_summary(intra, inter)
        roc_out = (Path(args.roc_out).resolve() if args.roc_out
                   else data_dir / "viz" / "roc_summary.json")
        roc_out.parent.mkdir(parents=True, exist_ok=True)
        roc_out.write_text(json.dumps({
            **summary,
            "n_intra": len(intra), "n_inter": len(inter),
            "params": roc_params,
            "templates_sig": sig,
            "device_sig": freqs_sig(freqs),
            "sampled_at": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
            "note": "REAL-STATIC(离线采样):复现 python tools/sample_hd.py --roc(参数见 params)",
        }, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"[OK] ROC: EER={summary['eer'] * 100:.2f}%  AUC={summary['auc']:.4f}"
              f"  (intra={len(intra)} inter={len(inter)})")
        print(f"     -> {roc_out}")
    else:
        intra, inter = sample(mods, templates, args.terminal_id, args.n, freqs)

    payload = {
        "terminal_id": args.terminal_id,
        "n_seeds": len(intra),
        "sampled_at": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
        "templates_json": str(templates_json),
        "templates_sig": sig,
        # 器件端签名:模板表一字未改、密钥却换过时(状态文件被删/重建),只有这一项
        # 能把样本判死。桥接读样本时两端都校,见 web_bridge.viz_hd。
        "device_sig": freqs_sig(freqs),
        **({"roc": roc_params} if roc_params else {}),
        "note": None,          # 桥接读到样本时会覆写成「离线采样样本(...)」
        "intra": intra,
        "inter": inter,
    }

    # 原子落盘:采样中途 Ctrl+C 不该留下半截文件。桥接对半截文件是按「不存在」处理
    # 的(read_hd_sample),但那样会静默退回现场采样 —— 与其让用户以为样本已生效,
    # 不如根本不留半个文件。
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(out.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, out)

    mi, xi = mean(intra), mean(inter)
    print(f"[OK] 终端 {args.terminal_id} · 种子 {len(intra)} · 签名 {sig}")
    print(f"     真品 intra: μ={mi:.2f} min={min(intra)} max={max(intra)}")
    print(f"     冒名 inter: μ={xi:.2f} min={min(inter)} max={max(inter)}")
    print(f"     分离度 Δμ={xi - mi:.2f}(越大越好)")
    print(f"     → {out}")

    # 分离度退化是**真正的**采样事故(器件密钥没随 tid 变、模板与器件对不上),
    # 而它的表现只是直方图上两条谱重叠 —— 不报警就会被当成「正常结果」放进报告。
    if xi - mi < 8:
        print("[WARN] 双系列均值差不足 8 —— 谱已显著重叠,检查模板与该终端器件是否同源", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
