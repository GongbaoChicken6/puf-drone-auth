# -*- coding: utf-8 -*-
"""模板数据取证：tid=1 的 100 CRP 响应位分布分析（rootcause 第4视角）
要回答：
1) 不同挑战的响应是否各不相同（响应依赖挑战？）
2) 响应位之间的两两海明距离分布（若都≈0=响应恒定；≈一半=正常伪随机；中间=确定性函数）
3) 0/1 比例（偏置）
"""
import json, sys, itertools
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from pathlib import Path
path = str(Path(__file__).resolve().parents[3] / "data/templates/templates.json")
d = json.load(open(path, encoding="utf-8"))
print("顶层类型:", type(d).__name__)
if isinstance(d, dict):
    print("顶层键:", list(d.keys())[:10])
    t = d.get("templates", d)
else:
    t = d
if isinstance(t, dict):
    print("模板 tids:", list(t.keys()))
    for k, v in t.items():
        print(f"--- tid={k} 类型={type(v).__name__}")
        if isinstance(v, dict):
            print("   字段:", list(v.keys())[:10])
        elif isinstance(v, list):
            print("   长度:", len(v), "首元素:", str(v[0])[:200])
