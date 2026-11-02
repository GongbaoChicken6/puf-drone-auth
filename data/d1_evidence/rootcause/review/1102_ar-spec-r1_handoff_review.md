# 交接文档完整性审查（ar-spec-r1，2026-11-02 20:4x）

对象：docs/HANDOFF_frontend_session_20261102.md（53 行）。方式：全文重读 + 逐项对仓库实态核验（git 6ed80a7..d2e3b08、四份 1102 日志、prereg v2 回填表、puf_metrics/puf_sac 产物、web 桥源码、scene.ts emissive 值、COM 映射）。

## 核验通过项
- 提交引用真实：c5e1f96（M1-M3，AGREE_REJECT=0.85+sidecar 已按第 2 轮放行条件落实）、c8a6d06（材料包）、83b6921（前端重建）；HEAD 实为 d2e3b08（交接提交本身），『≈83b6921』可理解。
- 数据主张与证据一致：2×2 矩阵（5d75e99：0/143/149/0）、无线攻击（2601e24/9bceb3a：板A PASS HD=0×5+CONFIRM；板B REJECT 均值 144.4+serve HD=133 无 CONFIRM）、跨板 10 轮均值 145.8=57.0%（1102_跨板HD分布统计.log 逐字吻合）。
- 前端硬细节基本盘在：桥完整命令行+前端地址、COM 口 20:35 实测映射+『COM6 禁用』警告、SSE schema 字段名坑、--data-dir 沙箱铁律、板B bit 易失+路径、SW7/SW13 BLOCKED 语义、三条未满意点+优先级。
## Findings（JSON）

```json
[
  {
    "severity": "P1",
    "file": "docs/HANDOFF_frontend_session_20261102.md",
    "line": 6,
    "category": "[A] 证据指针缺失",
    "description": "板端四大结果只写『详见 data/d1_evidence/』，未点名四份证据文件与论文材料包具体路径；新 AI 复核数据或写论文第一步就要自己翻目录。",
    "evidence": "",
    "function_context": "",
    "sources": [
      "ar-spec-r1"
    ]
  },
  {
    "severity": "P1",
    "file": "docs/HANDOFF_frontend_session_20261102.md",
    "line": 21,
    "category": "[B] 未解决的自相矛盾",
    "description": "bloomStrength『旧JS设0（新build用源码默认1）』——当前 dist 生效值是 1？该改哪个文件？用户最不满意的恰是 3D 清晰度（bloom=1 泛光直接掩盖细节），新 AI 第一脚就会踩。",
    "evidence": "",
    "function_context": "",
    "sources": [
      "ar-spec-r1"
    ]
  },
  {
    "severity": "P1",
    "file": "docs/HANDOFF_frontend_session_20261102.md",
    "line": 29,
    "category": "[A/D] 脚本来源/注入方法缺失",
    "description": "applyStyles 按钮脚本内容存哪、如何注入 console.html、如何确认存在（待办2 要求确认却无命令）均未写；脚本疑似只存在于未跟踪文件/内存中。",
    "evidence": "",
    "function_context": "",
    "sources": [
      "ar-spec-r1"
    ]
  },
  {
    "severity": "P2",
    "file": "data/d1_evidence/rootcause/seed2_board_preregistration.md",
    "line": 51,
    "category": "[C/D] 预登记关闭条件未满足",
    "description": "prereg v2 明文『未填完实验不算关闭』，回填表 5 行全空（mtime 停在 11-01 18:12）；交接宣称『全部闭环』却未提此流程债。",
    "evidence": "",
    "function_context": "",
    "sources": [
      "ar-spec-r1"
    ]
  },
  {
    "severity": "P2",
    "file": "docs/HANDOFF_frontend_session_20261102.md",
    "line": 16,
    "category": "[B] 缓存坑解法只给半句",
    "description": "『Vite重建，新hash文件名』未展开症状（改源码页面不变）、机理（浏览器持旧 bundle）、完整流程（build→dist 覆盖→注入脚本丢失→新 hash 失效+硬刷新）。",
    "evidence": "",
    "function_context": "",
    "sources": [
      "ar-spec-r1"
    ]
  },
  {
    "severity": "P2",
    "file": "docs/HANDOFF_frontend_session_20261102.md",
    "line": 38,
    "category": "[E] 用户工作风格未传达",
    "description": "仅有『铁律不碰真实模板』一条；证据落盘/断言正向/先虚拟后上板/超时不算数/PMOD 不带电插拔、改前端必须重建+截图验证、用户对反复无效迭代强烈不满等均未传达。",
    "evidence": "",
    "function_context": "",
    "sources": [
      "ar-spec-r1"
    ]
  },
  {
    "severity": "P2",
    "file": "docs/HANDOFF_frontend_session_20261102.md",
    "line": 41,
    "category": "[A] git 工作区实况未传达",
    "description": "只写 HEAD/待推；实际工作区不干净：data/device_keys/{audit.log,device_keys.json} 已改未提交 + 根目录 15+ 未跟踪 _*.py/_page.html/_*.png 调试脚本（含疑似注入脚本源），处置建议缺失。",
    "evidence": "",
    "function_context": "",
    "sources": [
      "ar-spec-r1"
    ]
  },
  {
    "severity": "P2",
    "file": "docs/HANDOFF_frontend_session_20261102.md",
    "line": 16,
    "category": "[A] 前端落点文件未点名",
    "description": "emissive .12/.15 与 label Y offset 实际在 web/src/stages/three/scene.ts（已验证），文档只说『源码级』；S1-S7 画布/按钮所属组件未指。",
    "evidence": "",
    "function_context": "",
    "sources": [
      "ar-spec-r1"
    ]
  },
  {
    "severity": "P2",
    "file": "docs/HANDOFF_frontend_session_20261102.md",
    "line": 52,
    "category": "[D] 论文待办无入口",
    "description": "『论文冲刺』未指 c8a6d06 材料包具体文件（master mapping 表/必改清单/CSV）与论文主文件路径。",
    "evidence": "",
    "function_context": "",
    "sources": [
      "ar-spec-r1"
    ]
  },
  {
    "severity": "P3",
    "file": "data/d1_evidence/puf_metrics_1102.json",
    "line": 5,
    "category": "[C] 产物与数据口径分离",
    "description": "uniqueness 为空数组（8:47 生成，板端实验 12:33 后未刷新）；跨板数据在 1102_跨板HD分布统计.log 与材料包，新 AI 引用时需知口径分离。",
    "evidence": "",
    "function_context": "",
    "sources": [
      "ar-spec-r1"
    ]
  },
  {
    "severity": "P3",
    "file": "docs/HANDOFF_frontend_session_20261102.md",
    "line": 46,
    "category": "[A] 硬件细节小缺口",
    "description": "板A JTAG SN（0195C）未列；板B 重烧命令未给（bit 路径有、program_zc706.tcl 用法无）；commit 664b569 信息写 COM11 与 20:35 实测 COM12 冲突（交接以实测为准但未提示此误导）。",
    "evidence": "",
    "function_context": "",
    "sources": [
      "ar-spec-r1"
    ]
  },
  {
    "severity": "P3",
    "file": "docs/HANDOFF_frontend_session_20261102.md",
    "line": 34,
    "category": "[B] 构建环境约定未提",
    "description": "web/README 的 TEMP=web/.dev-data/tmp 与 npm --prefix web 约定、node_modules 已装验证方式未提。",
    "evidence": "",
    "function_context": "",
    "sources": [
      "ar-spec-r1"
    ]
  }
]
```

## 总评
前端调优主线可接手（命令/端口/地址/坑警示齐）；板端与论文侧只有结论没有指针，加上 bloom 矛盾未解、注入脚本无源、prereg 回填空置三条债，新 AI 需花一整轮翻仓库才能『无缝』。

## 改进建议（按优先级）
1. 【P1】补『结果→证据文件』指针表：四份 1102_*.log + c8a6d06 材料包具体文件 + puf_metrics_1102.json/puf_sac_1102.json。
2. 【P1】解决 bloomStrength 矛盾：写明 dist 当前生效值（=1）、应改 web/src 何处何值、重建验证步骤——这是用户当前不满的直接相关项。
3. 【P1】applyStyles 脚本：内容存档位置（建议入库 web/.dev-data/ 或 docs/）+ 注入步骤 + 确认命令（Select-String applyStyles web\dist\console.html）。
4. 【P2】填 prereg v2 回填表（或列为显式待办并说明原因）——预登记自身关闭条件。
5. 【P2】补『缓存坑』完整段落：症状→机理→『build→覆盖→重注入→新 hash 失效+硬刷新』流程。
6. 【P2】补用户工作风格段：铁律四条（落盘/正向断言/先虚拟后上板/超时不算数；PMOD 不带电插拔）+ 前端『改完必须重建+截图验证再交用户』流程。
7. 【P2】补 git 工作区实况：未提交修改（device_keys）+ 未跟踪调试脚本清单与处置建议（保留注入源/清理一次性脚本）。
8. 【P3】板A JTAG/COM11 澄清、板B 重烧命令、metrics uniqueness 口径说明、Vite TEMP 约定。
