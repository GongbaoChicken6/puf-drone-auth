# AUTO-REVIEW 报告：N10 伪基站接入演示 + 会话提交包（2026-11-18 21:40）

- 模式：content（自动检测：本会话代码变更）
- 范围：0044a51..9c594de（4 提交）+ 审查中工作树修复（后为 49e1fa4）
  - tools/attack/fake_result_attack.py（N10 rogue 模式 +160 行）
  - tests/test_attack_tool.py（+4 测试）
  - web/bridge/web_bridge.py（N5/N6 收尾 +62）、enroll_real.py（+14）
  - web/src/components/access-popup.ts（+5）、src/rtl/.../w3_top_zc706.xdc（v5 换脚）
- **降级声明：子代理派遣不可用**。实测 list_agents 仅 lead；send_message 派遣新名返回
  "subagent unavailable"（探针留痕）。按技能降级条款执行单代理多视角串行审查
  （缺陷/静默失败/spec合规/安全/测试覆盖 五视角），置信度低于多代理交叉，已用可复现
  命令证据补偿。

## 发现与处置

| # | 级别 | 视角 | 发现 | 处置 |
|---|------|------|------|------|
| F1 | **P1** | 缺陷+浏览器验证 | _ROGUE_PAGE 内嵌 JS 换行转义错误：Python 三引号把 \n 变真换行→JS 语法错误→**按钮死**。urllib 冒烟未覆盖 JS，真浏览器 console 抓到 | ✅修复(49e1fa4)：源码改 \\n；真浏览器复验：console 干净、点击出「已发起 #1」+两帧、stub 空中日志 22B 0x93+28B 0x90 |
| F2 | P2 | 静默失败 | do_POST 串口异常→traceback 甩脸，页面只显 TypeError | ✅修复：JSON 500 {ok:false,error}+日志 |
| F3 | P2 | 静默失败 | --rogue 交互循环被串口异常杀死 | ✅修复：捕获+提示后继续等下一轮 |
| F4 | P3 | 缺陷 | --rogue-web 端口占用→OSError 裸栈 | ✅修复：友好提示换 8644，exit 3 |
| F5 | P3 | 文档 | --simulate --rogue-web 不起服务只打帧组，易误解 | 已在 help/提示词写明（rehearsal 语义），不改 |
| F6 | P3 | 遗留 | XDC 已提交 v5 换脚但 demo_start 烧 v4 bit（风扇子系统 P0 流，非本 diff 引入） | 挂账：决赛前风扇线定案时一并处理 |
| F7 | P3 | 遗留 | data/device_keys.json 被跟踪与 .gitignore"never commit"矛盾（历史遗留，私库） | 挂账：赛后清理或显式豁免注释 |

spec 合规：用户剧本（攻击PC前端点击→HC-12 上信道→真站动画"别的基站尝试连接→已拒绝"，板子不中转）→ 实现=点击发 2 帧（0x0093 触发 IDS 横幅 + 0x0090 tid=99 触发拒绝动画/BLOCKED）；RTL 实读证明板 A S_IDLE 对两帧均不理会。✅无范围蔓延。
安全：rogue-web 仅绑 127.0.0.1；静态页无输入面；无秘密泄漏。✅
测试覆盖：build_rogue_burst 4 测试；_rogue_* 薄层由真浏览器 e2e+进程内冒烟覆盖（证据在库）。⚠️_rogue_web 无 CI 测试（文件契约禁 socket），以证据文件代。

## 门禁判定

修复后 P0=0 P1=0 P2=0（P3×2 已修、×3 挂账已列）→ **PASS_WITH_NOTES**
回归：suite **220 passed 1 skipped**；GitHub finals-demo = 49e1fa4（ls-remote 实证）。

## 决赛日手动验证步骤（真硬件）

1. 主PC：.scriptsdemo_start.ps1 -SerialPort <PC侧HC-12口> → 桥就绪
2. 攻击PC：python tools/attack/fake_result_attack.py --port COMx --rogue-web → 浏览器 127.0.0.1:8643
3. 点击【发起伪基站认证】→ 主PC前端应出现：IDS 红横幅 + tid=99 拒绝动画 + BLOCKED
4. 板A全程不动（DS35 心跳不变），随后 SW7 正常认证 PASS 不受影响
5. 证据截图落 data/d1_evidence/finals_demo/attack/

## 证据
- 攻击页浏览器验证：data/d1_evidence/finals_demo/attack/rogue_web_{before,after}_click.png + rogue_web_stub_frames.log
- 工具验证：data/d1_evidence/finals_demo/n10_rogue_tool_20261118.md
- 部署验证：data/d1_evidence/finals_demo/attack_deploy_check_20261118.md
