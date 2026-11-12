# 集成指南 · 基于 PUF 的无人机身份认证系统（厂商对接版）

> 面向希望把本系统接入自家无人机/地面站的厂商与工程师。系统分两端：**终端侧**是一块可综合的 FPGA RTL IP（认证终端，装在无人机上），**站端**是一套 Python 软件（地面基站）。两端之间是一条 UART 透传链路（有线 USB-TTL 或无线 HC-12 同信道）。

## 1. 系统形态

```
无人机端(FPGA PL)                     地面站端(PC / 服务器)
┌────────────────────┐   UART 115200  ┌─────────────────────────┐
│ w3_top_zc706 (RTL) │◄──8N1 透传链路─►│ web_bridge.py (HTTP+SSE)│
│  16环RO-PUF        │  (USB-TTL 或    │  + src/python/server    │
│  Speck64/96        │   HC-12 无线)   │  (protocol/enroll/hsm/  │
│  五帧HF-IDA状态机   │                │   crp_pool/threshold)   │
└────────────────────┘                └──────────┬──────────────┘
                                                 │ http://…:8642
                                          浏览器演示控制台(可选)
```

每轮认证 5 帧：ACCESS_REQUEST→CHALLENGE→RESPONSE_R1→RESULT→CONFIRM（灰区自动加测 EXTRA_CHALLENGE）。密钥不预存于终端：认证时由芯片物理指纹现场派生/验证。

## 2. 终端侧接口（RTL IP）

例化板级 wrapper `w3_top_zc706`（或通用顶层 `w3_top`）即可，对外接口极简：

| 端口 | 方向 | 宽度 | 说明 |
|---|---|---|---|
| clk_p/clk_n | in | 1 | 差分时钟（ZC706: 200MHz；其他板见 §5 迁移） |
| sys_rst_btn_n | in | 1 | 复位按键（**高有效**，板上实测） |
| auth_btn | in | 1 | 认证启动（SW7，消抖+熵就绪门控在 IP 内完成） |
| term_id_dip | in | 4 | 终端 ID 拨码（0001=终端一，0010=终端二；0011 可演示冒充） |
| radio_txd/radio_rxd | out/in | 1 | UART 115200 ↔ 数传电台/USB-TTL |
| led_busy / led_result[1:0] / led_heartbeat | out | — | 01=PASS 10=REJECT 11=BLOCKED；心跳 0.75Hz |
| ext_led[3:0] / ext_buzzer | out | — | （finals-demo）外接大 LED/蜂鸣器 |

**参数**（例化时可覆写）：FREQ_HZ=100_000_000、BAUD=115_200、TIMEOUT_S=2、ENROLL_EN=1（站端驱动注册）、SEED_GATE_EN=1（熵门控）。

**资源与时序**（xc7z045 实测）：LUT 4375（2.0%），WNS +1.873ns @100MHz，全约束通过；CI 18 项回归 + 135 项 Python 测试。

**注意**：bit 是器件相关的——PUF 指纹绑定具体芯片与布局，每块板需独立注册（见 §4 步骤 3）；同设计不同布局（seed2 变体）指纹互异，这正是防克隆机制。

## 3. 站端 Python API

| 模块 | 关键接口 | 用途 |
|---|---|---|
| protocol.py | HFIDAProtocol.pack/parse；字节级契约唯一真相源（docs/protocol_contract.md） | 帧构造/解析 |
| enroll.py | enroll_device(protocol, transport, tid, n=100, measurements=3, on_progress) | 注册（传输无关：loopback/串口皆可） |
| hsm.py | SpeckHSM；设备密钥(12B)管理 | 站端密钥保管 |
| crp_pool.py | CRPPoolRegistry；挑战一次性消费 | 挑战池 |
| threshold.py | TAU_PASS=6 / TAU_REJECT=16（双阈值+灰区加测） | 判决 |
| web_bridge.py | REST /api/auth /api/enroll /api/poll /api/status；SSE /api/events | 服务与演示 |

## 4. 集成流程（厂商视角四步）

1. **硬件**：终端 IP 例化进你的 FPGA 工程（或直接用我们的 wrapper），UART 接你的数传电台；站端 `pip install pyserial` 后运行 `web/bridge/web_bridge.py --serial-port COM<x> --data-dir <空目录>`（**--data-dir 必须指向空目录**，默认目录会被清理）。
2. **密钥预置**：站端 `/api/setkey`（或 REPL provisionkey）装入该终端的设备密钥——演示形态为预置 K，产品路线见 §6。
3. **注册准入**：站端发起 enroll（100 组挑战×3 次重复测量，多数表决建模板，约 2 分钟）；板端须处于空闲态。注册后即可认证，亦可随时 `/api/poll` 主动巡检（finals-demo 新增：下发 AUTH_POLL，板端等效按下认证键，走完整双向认证）。
4. **运行**：无人机上电→按认证键（或站端巡检）→ 看灯语/订阅 SSE verdict 事件拿判定（PASS/REJECT/灰区加测/重放嫌疑，含逐响应 HD）。

## 5. 迁移到其他板卡

本仓库自身就是 ZC702→ZC706 的迁移实例（w3_top_zc702.v 与 w3_top_zc706.v 并存）。迁移步骤：

1. 写新板 wrapper（时钟适配 + 引脚）与 XDC 约束——协议/密码/PUF 核心零改动；
2. 构建脚本参照 build/tcl/build_w3_board.tcl（含时序门禁与环振 LUTLP-1 豁免）；
3. 新板**重新注册**（指纹绑定器件与布局，旧模板不可复用）；
4. 视噪声水平**重标定阈值**（TAU_PASS/TAU_REJECT 按 16 环实测 HD 分布）。

预估 2-3 天/板（引脚核对为主）。

## 6. 诚实边界（对接前须知）

- **设备密钥形态**：当前演示用预置 K（注册时装入站端 HSM）；PUF 派生密钥路径（KDF 冻结、S_KEY_MEASURE→S_KEY_DERIVE）已实现并仿真验证，板级启用需 0x0096 注册通道 + K_boot 纠错（见 docs/protocol_contract.md §9.6），有效熵 ≈44bit。
- **会话加密**：本协议是接入认证协议；认证后的业务流量保护走"会话密钥 = Speck(K, C2)"扩展（双侧密码原语已具备，未实装）。
- **DoS**：任何认证协议都无法阻止信道拥塞；本系统把拥塞显式暴露为信道 IDS 告警（channel.noise）而非静默。
- **重放窗**：站端 C2 窗 128；终端 C2 上电由环振熵种子初始化，跨断电重放失效。
- 站端密钥当前为演示级存储（JSON），产品部署请接真 HSM。

## 7. 参考文档

- docs/protocol_contract.md —— 字节级协议契约（唯一真相源 + 黄金向量）
- docs/zc706_board_runbook.md —— 板级操作手册
- docs/integration_guide.md —— 本文
- 提交包内设计报告（32 页）与 metrics 实测数据
