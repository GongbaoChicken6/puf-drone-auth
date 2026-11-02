# D2 全天会话交接文档（2026-11-02 20:50 · 详细版）

> 供新对话 AI 无缝接手。审查报告：data/d1_evidence/rootcause/review/1102_ar-spec-r1_handoff_review.md

## 1. 今天完成了什么（按时间线）

### 上午：M1-M4 方案审查 + M1-M3 实现
- M1-M4 集成方案两轮 auto-review（R1 FAIL 改阶序签名 → R2 PASS → 终稿 a8a21fb）
- **M1-M3 纯PC实现完成**（commit c5e1f96）：阶序守卫+三件套+SAC+演示tid清理

### 中午：板端唯一性实验（论文核心数据）
- 完美 2×2 对称矩阵：生产vs tid1 PASS HD=0 / vs tid2 REJECT 149；seed2 vs tid1 REJECT 143 / vs tid2 PASS 0
- 证据：data/d1_evidence/1102_seed2_唯一性实验.log（commit 5d75e99）

### 下午：统计+无线+攻击+前端
- 跨板HD分布10轮：均值145.8=57.0%（1102_跨板HD分布统计.log，fb9deeb）
- 板A无线：5轮PASS HD=0 + serve全六帧CONFIRM 57ms
- 板B无线攻击：5轮REJECT均值144.4 + serve 4帧REJECT HD=133 36ms（1102_无线攻击实验_板B.log，2601e24）
- 板B补充：自认证+重放+c2reset+时延（1102_板B_完整实验数据.log，9bceb3a）
- web桥串口真实硬件模式（--serial-port + RealSerialListener）
- 前端视觉调优（Vite重建+emissive修复+按钮脚本，但bloom未完全解决）

## 2. 证据文件指针表

| 实验 | 文件 | Commit |
|---|---|---|
| 唯一性矩阵 | data/d1_evidence/1102_seed2_唯一性实验.log | 5d75e99 |
| 跨板HD | data/d1_evidence/1102_跨板HD分布统计.log | fb9deeb |
| 无线攻击 | data/d1_evidence/1102_无线攻击实验_板B.log | 2601e24 |
| 板B完整 | data/d1_evidence/1102_板B_完整实验数据.log | 9bceb3a |
| M1三件套 | data/d1_evidence/puf_metrics_1102.json | c5e1f96 |
| M2 SAC | data/d1_evidence/puf_sac_1102.json | c5e1f96 |
| 论文材料包 | docs/paper_fillin_20261102/（mapping+必改+CSV） | c8a6d06 |
| 预登记v2 | data/d1_evidence/rootcause/seed2_board_preregistration.md | - |

注意：puf_metrics_1102.json 的 uniqueness 为空（板端实验前生成），跨板数据在跨板HD分布统计.log

## 3. 运行环境

### COM口映射（20:35实测）
- COM12 = 丢石头CH340 = 板B HC-12 B-PC（桥用这个）
- COM6 = WCH-LinkE = 板A适配器（不要用于板B）

### 板B硬件
- JTAG SN: 210251A04F2C（板A: 210251A0195C）
- bit: build/board_zc706_seed2/w3_top_zc706_seed2.bit（易失，断电需重烧）
- 重烧：vivado.bat -mode batch -source build/tcl/program_zc706.tcl -tclargs <bit路径> 210251A04F2C
- SW12=0001（冒充tid=1），SW13复位后按SW7发起

### 桥启动命令（在D:/puf-drone-auth目录）
python web/bridge/web_bridge.py --repo-root . --data-dir web/.dev-data --loopback --serial-port COM12 --serial-baud 115200 --port 8642
- 前端：http://127.0.0.1:8642/console.html
- --data-dir web/.dev-data 是沙箱铁律（防模板覆盖）
- 桥的RealSerialListener会自动注入真实模板(tid=1/2)到沙箱

## 4. 前端构建与注入

### 源码位置
- 3D场景：web/src/stages/three/scene.ts（材质:213-280，标签:109-115）
- 特效：web/src/stages/three/fx.ts（bloomBoost:96,260,270,289,308,435）
- 文字：web/src/stages/three/palette.ts（Label类）

### 构建流程
1. 修改 web/src/ 下的 TypeScript 源码
2. cd web && npm run build（7秒）
3. **构建覆盖 console.html → 必须重新注入按钮脚本**（见下）
4. 用户浏览器普通刷新（新hash文件名自动绕过缓存）

### 按钮样式脚本（注入到 console.html 的 body 末尾）
在 </body> 前加入：
<script>(function(){var C={1:'#22c55e',2:'#ef4444',3:'#f97316',4:'#eab308',5:'#6b7280',6:'#3b82f6',7:'#8b5cf6'};var I={1:'✓',2:'✗',3:'↻',4:'±',5:'∅',6:'⟳',7:'⚠'};function a(){document.querySelectorAll('button').forEach(function(b){var t=(b.textContent||'').trim();for(var i=1;i<=7;i++){if(t.indexOf('S'+i)===0){b.style.borderLeft='4px solid '+C[i];if(!b.getAttribute('data-iconed')){b.setAttribute('data-iconed','1');var s=document.createElement('span');s.style.cssText='color:'+C[i]+';font-weight:900;margin-right:4px;';s.textContent=I[i]+' ';b.prepend(s);}break;}}});}setInterval(a,500);setTimeout(a,100);setTimeout(a,500);setTimeout(a,1000);setTimeout(a,2000);})();</script>

### 确认脚本存在
Select-String applyStyles web/dist/console.html（应返回匹配）

### 浏览器缓存大坑（今天最贵的教训）
症状：改了dist里的JS → 刷新 → 没变化
原因：Vite产物文件名含hash，浏览器按URL缓存，内容变文件名不变=不失效
正确做法：改TypeScript源码 → npm run build（新hash自动失效）→ 注入脚本 → 用户F5
错误做法：直接改dist压缩JS（改了白改）

## 5. bloom问题现状（用户最不满意项）

### 已修
- 无人机glow emissive .95->.12（scene.ts:280，Vite重建生效）
- 基站trim .8->.15（scene.ts:217）
- 文字shadowBlur=14已删改黑边白字（palette.ts，旧JS改的，重建后需验证）

### 未修（新对话最优先）
- fx.ts bloomBoost：动态0~1全场呼吸效果
  - :96 bloomBoost=0（初始）
  - :260/:270/:289 设为1（判定后）
  - :308 max(bloomBoost, 0.85)
  - :435 衰减 dt*0.85
  - 建议：所有设1处改为0.3~0.5
- stage3d.ts中UnrealBloomPass的strength：需检查是否设了高值
- 修完必须build+注入+截图验证再交用户（用户原话要求）

## 6. 用户铁律

1. 证据必须落盘（data/d1_evidence/），断言用正向哨兵（PROGRAM_OK等），超时不算数
2. 先全量虚拟验证再上板（用户对反复上板极不满）
3. PMOD严禁带电插拔（板子数千元）
4. 前端改动必须build+截图验证后再交用户
5. web桥永远用--data-dir web/.dev-data沙箱
6. 板B(tid=2)必须先setkey 2 0001020308090a0b10111213再enroll 2 100
7. 每次按SW7前先按SW13复位（板子BLOCKED态特性）

## 7. Git工作区

### 待推送（3个commit，等VPN）
d2e3b08 > 83b6921 > 664b569（注意664b569信息写COM11，实际当前用COM12）

### 未提交修改
data/device_keys/audit.log + device_keys.json（实验自动更新）

### 未跟踪（根目录，可清理）
_*.py x12（bloom/text调试脚本）、_*.png x3（截图验证）、_page.html、_screenshot.js

## 8. 下一步优先级

1. 前端bloom调优（fx.ts bloomBoost降低 → build → 注入 → 截图验证）
2. 论文冲刺（D2晚/D3，死线11-03保守）
   - 入口：docs/paper_fillin_20261102/（c8a6d06）：主映射表+必改清单12条+raw CSV
   - 论文PDF：工作区根目录 基于PUF的无人机身份认证系统.pdf（30页）
3. prereg v2回填表（:47-55全空，数据在唯一性实验log中，10分钟可填）
4. 板子可收起（数据全落盘）

## 9. M1-M3代码速查

| 模块 | 文件 |
|---|---|
| 阶序反演 | src/python/server/puf_order.py |
| 守卫(AGREE_REJECT=0.85) | src/python/server/template_db.py enroll() |
| sidecar | templates.orders.json（同目录） |
| 测试 | tests/test_template_guard.py（G1-G7） |
| 三件套 | tools/puf_metrics.py |
| SAC | tools/puf_sac.py |
| CI | scripts/ci_regression.ps1（新测试需加行） |

## 10. 记忆库
新对话自动注入D2交接记忆（id=4ea676e1）。审查报告：data/d1_evidence/rootcause/review/1102_ar-spec-r1_handoff_review.md
