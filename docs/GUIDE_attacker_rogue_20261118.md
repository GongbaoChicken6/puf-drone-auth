# 攻击PC（伪基站）部署与决赛演示指南 · 2026-11-18 v3

> 本文档同时是「攻击PC 上 AI 助手」的启动提示词：假设你对本项目零记忆，按本文从零执行。
> 主PC（另一台电脑）扮演真基站+板A；本机是决赛演示中的**伪基站攻击者（红队）**。

## 一、项目背景（30秒版）

- PUF 无人机认证：FPGA 板卡(ZC706) + HC-12 433MHz 无线 + MAVLink v2 自定义帧。
- 认证五帧：ACCESS_REQUEST(0x0090)→CHALLENGE(0x0091)→RESPONSE_R1(0x0092)→RESULT(0x0093)→CONFIRM(0x0094)。
- 板端双向认证：基站判板子（HD 距离），板子也判基站（RESULT 内 R2 因子，基站密钥推导）。
- 你的两个攻击场景（均已实现，**不需要改任何代码**）：
  - **场景B（主演示·N10）**：你在本机网页上点【发起伪基站认证】→ HC-12 直上信道 →
    主PC前端播放「检测到伪基站(IDS红横幅) → 有设备尝试接入 → 已拒绝 + BLOCKED」。
    **板A全程不参与、不受影响**（0x0090 板端不解析；0x0093 空闲态无视）。
  - **场景A（进阶·N8竞速）**：板A正常认证时监听 RESPONSE_R1，零延迟注入伪 RESULT
    （PASS+错误R2）→ 板A R2失配 → CONFIRM_FAIL 上行 + BLOCKED → 主PC三重证据同屏。

## 二、部署（现在就做）

1. 环境：Windows + Python 3.10+（实测 3.13 可用）+ Git；唯一依赖 `pip install pyserial`。
2. 克隆（私有仓库，首次访问弹 GitHub OAuth，用 Cheems520 或 Alison61 登录一次）：
   ```
   git clone -b finals-demo https://github.com/GongbaoChicken6/puf-drone-auth.git
   cd puf-drone-auth && git log --oneline -1
   ```
   **验收哨兵**：HEAD ≥ `20a0c95`（2026-11-18 晚 auto-review 后）。
   GitHub 连不上=晚高峰被断，隔几分钟重试或让用户开代理。
3. 回归自检：`python -m pytest tests/test_attack_tool.py tests/test_confirm_race.py -q`
   **验收哨兵**：`18 passed`。
4. 零硬件排练（必做）：
   ```
   python tools/attack/fake_result_attack.py --simulate --rogue
   ```
   **验收哨兵**：`[SIMULATE] heard=3 injected=1` + 两行 `[SIMULATE][ROGUE]`
   （banner_fake_result_0x0093 与 rogue_access_request_0x0090 terminal_id=99）。
   到此部署完成。伪基站页面已通过真浏览器点击验证（含 JS 修复），放心使用。

## 三、硬件接线（决赛日，断电操作）

CH340 USB-TTL + HC-12（天线必装）：
```
USB-TTL TX → HC-12 RXD（交叉！）   USB-TTL RX → HC-12 TXD
USB-TTL 5V → VCC                   USB-TTL GND → GND
```
设备管理器确认 `USB-SERIAL CH340 (COMx)`，记下 COMx。严禁带电插拔；天线拧好再上电。

## 四、HC-12 一次性信道配置（仅当模块是新的/参数被改过）

机队统一：FU3 / **115200** / **信道 C001**（与主PC侧、板A侧完全一致）。
SET 脚先接 GND 再上电，然后：`python tools/hc12/hc12_config_c001.py COMx`
**验收哨兵**：末行 `配置完成且验收全过 PASS`（日志 hc12_config_log.txt）。完成后断开 SET 与地。

## 五、决赛日·场景B：伪基站接入演示（主演示）

1. 主PC起真基站桥（主PC侧负责）；本机启动伪基站控制台：
   ```
   python tools/attack/fake_result_attack.py --port COMx --rogue-web
   ```
   浏览器开 **http://127.0.0.1:8643/**（端口被占就 `--rogue-web 8644`）。
2. 点击【发起伪基站认证】→ 空中两帧（间隔 0.3s）：
   - 0x0093 伪 RESULT → 主PC **IDS 红横幅**（疑似伪基站注入）
   - 0x0090 未注册接入(tid=99) → 主PC **弹窗/直接验证 → 拒绝动画 + BLOCKED**
   **成功哨兵（本机）**：页面显示「已发起 #N」+两帧 hex；终端两条 `>>> ROGUE …`。
   **成功哨兵（主PC侧）**：红横幅 + tid=99 被拒 + 状态 BLOCKED。
3. 板A全程不动（DS35 心跳不变），随后可无缝做正常认证演示。
4. 备用：`--rogue` 交互模式（Enter=发起一次）；`--no-banner` 只发接入请求。

## 六、决赛日·场景A：竞速注入三重证据（进阶）

1. 被动验证：`python tools/attack/fake_result_attack.py --port COMx --passive`
   板A正常认证一轮，**哨兵**：听到 ACCESS_REQUEST / CHALLENGE / RESPONSE_R1。
2. 竞速注入：`python tools/attack/fake_result_attack.py --port COMx`
   板A按 SW7 → 听到 RESPONSE_R1 → 零延迟注入。
   **哨兵**：`>>> INJECT fake RESULT … lag=<个位数>ms`；随后听到迟到真 RESULT 与板A CONFIRM(FAIL)。
   没触发重跑一次（半双工碰撞已知，重跑即好）。

## 七、故障排查

| 现象 | 处理 |
|---|---|
| 点击后主PC没反应 | 查双方 HC-12 是否同为 C001/115200；先 `--passive` 确认听得到帧 |
| 页面显示 失败:SerialException | HC-12 掉线/松动：重新插好再点（工具不会崩，串口日志有明细） |
| 端口起不来 | `--rogue-web 8644` |
| 注入后没 CONFIRM/没 BLOCKED | 半双工碰撞，重跑一次 |
| 全是乱码/0xFE | 刚烧完 bit 预热，第二轮正常 |

## 八、红线

1. 不改仓库任何代码/数据——默认参数就是剧本（R2=deadbeef…按构造即错；tid=99 未注册即拒）。
2. 本机不要运行 `web_bridge.py` 连同一信道——会和真基站抢发帧；攻击PC只跑攻击工具。
3. 场景B请在板A空闲时点击；拿不准先 `--simulate --rogue` 对照。

## 九、第一步行动清单

1. `python --version` ≥3.10、`git --version`；
2. 部署到 `--simulate --rogue` 哨兵全绿；
3. 向用户报告三样证据：HEAD hash、pytest 结果、simulate 输出；
4. 硬件在手就完成接线+信道配置，留档 hc12_config_log.txt。
