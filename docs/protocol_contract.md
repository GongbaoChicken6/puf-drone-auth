# HF-IDA 字节级协议契约（RTL ↔ PC 唯一依据）

> **真相源声明**：本契约从 `src/python/server/protocol.py` 的实际实现中逐字节提取。
> **RTL 实现必须与本文件一致，而非与 docs/project_design.md 一致**——B 线实现时对原设计做了
> 5 处修正（C2 位置、N_CHALLENGES=4、CRC_EXTRA 占位表等），代码是唯一真相源。
> 文中所有黄金向量由 protocol.py 生成并用 parse() 回验通过（2026-10-05）。
> §4.1 与 §4 的 RESULT_A1_GOLDEN 于 A1（2026-10-08）新增：向量经 speck.py/protocol.py 双侧回验，
> tools/check_contract_sync.py 重跑全绿（该工具现覆盖全部 §4 向量）。

---

## 1. 帧格式（所有消息共用）

```
偏移  宽度  字段             值/说明
──────────────────────────────────────────────────────────────
[0]   1B   STX             固定 0xFD
[1]   1B   LEN             载荷长度（字节），≤ 32
[2]   1B   INCOMPAT_FLAGS  固定 0x00
[3]   1B   COMPAT_FLAGS    固定 0x00
[4]   1B   SEQ             8-bit 序号，0xFF 后回绕到 0x00
[5]   1B   SYSID           默认 0x01（protocol.py 构造参数）
[6]   1B   COMPID          默认 0x02（protocol.py 构造参数）
[7]   3B   MSGID           小端 24-bit（见 §3 消息表）
[10]  LEN  PAYLOAD         见 §3 各消息载荷布局
[10+LEN] 2B  CRC16         小端（低字节在前），见 §2
──────────────────────────────────────────────────────────────
总帧长 = 12 + LEN；MSG_CHALLENGE / MSG_RESPONSE_R1(4条) = 44B
```

## 2. CRC-16/MCRF4XX（位精确规格）

- **初值**：0xFFFF（每帧独立计算，不跨帧累积）
- **计算域**：`frame[1..9]`（除 STX 外的头 9 字节）+ `payload` + `CRC_EXTRA`（1 字节，按消息查 §3 表）
- **输出**：16-bit 值按小端写入帧尾（低字节在前）
- **每字节迭代公式**（与 c_library_v2/checksum.h 位精确一致）：

```
tmp = (crc[7:0] ^ byte)          // 8-bit
tmp = tmp ^ (tmp << 4)           // 8-bit 截断
crc = (crc >> 8) ^ (tmp << 8) ^ (tmp << 3) ^ (tmp >> 4)   // 16-bit 截断
```

**CRC 单元黄金向量**（TB 第一测试用）：
| 输入字节 | 输出 CRC |
|---|---|
| 0xFD | 0x23ED |
| 0xAA | 0x05D7 |

## 3. 消息目录（6 条，ID/CRC_EXTRA/载荷布局）

| MSGID | 名称 | 方向 | CRC_EXTRA | 载荷布局 |
|---|---|---|---|---|
| 0x0090 | ACCESS_REQUEST | 终端→基站 | 0x5A | 16B：terminal_id(u32LE) + nonce(u32LE) + c2(8B) |
| 0x0091 | CHALLENGE | 基站→终端 | 0x5B | 32B：seed0(8B)+seed1+seed2+seed3 背靠背 |
| 0x0092 | RESPONSE_R1 | 终端→基站 | 0x5C | 32B（4条响应）或 24B（灰区复测 3 条） |
| 0x0093 | RESULT | 基站→终端 | 0x5D | 10B：result(u8) + hd(u8) + r2(8B) |
| 0x0094 | CONFIRM | 终端→基站 | 0x5E | 5B：terminal_id(u32LE) + status(u8) |
| 0x0095 | EXTRA_CHALLENGE | 基站→终端 | 0x5F | 24B：3×8B 种子 |

**多字节字段一律小端**（u32、msgid、CRC）。8B 种子/响应为不透明字节串，原样传输不做字节交换。

**RESULT 码**：0=PASS, 1=REJECT, 2=ERROR, 3=POOL_EMPTY, 4=REPLAY（C2 落入服务端重放窗→疑似重放，A1 阶段 4 新增；终端侧对任意非零码一律拒绝，与 W3 RTL 兼容）；HD 特殊值 0xFF=HD_NONE（即错误路径无 HD）。

## 4. 黄金帧向量（TB 直接硬编码）

```
# ACCESS_REQUEST tid=42 nonce=0xDEADBEEF c2=000102...07 (28B)
FD 10 00 00 42 01 02 90 00 00 2A 00 00 00 EF BE AD DE 00 01 02 03 04 05 06 07 3A D2

# CHALLENGE seq=0x43 seeds=A0 00*7 / A1 01*7 / A2 02*7 / A3 03*7 (44B)
FD 20 00 00 43 01 02 91 00 00 A0 00 00 00 00 00 00 00 A1 01 01 01 01 01 01 01
   A2 02 02 02 02 02 02 02 A3 03 03 03 03 03 03 03 F2 F7

# RESPONSE_R1 seq=0x44 (44B)
FD 20 00 00 44 01 02 92 00 00 B0 00 00 00 00 00 00 00 B1 01 01 01 01 01 01 01
   B2 02 02 02 02 02 02 02 B3 03 03 03 03 03 03 03 A7 15

# RESULT pass hd=5 r2=C0..C7 (22B)
FD 0A 00 00 45 01 02 93 00 00 00 05 C0 C1 C2 C3 C4 C5 C6 C7 A5 D2

# CONFIRM tid=42 status=1 (17B)
FD 05 00 00 46 01 02 94 00 00 2A 00 00 00 01 78 F4

# EXTRA_CHALLENGE seq=0x47 (36B)
FD 18 00 00 47 01 02 95 00 00 D0 00 00 00 00 00 00 00 D1 01 01 01 01 01 01 01
   D2 02 02 02 02 02 02 02 7A 9F

# RESULT_A1_GOLDEN seq=0x50 result=PASS hd=5 r2=Speck(W3 key,C2=a1..a8) (22B)
FD 0A 00 00 50 01 02 93 00 00 00 05 7B 45 B0 54 5E 59 AA 94 FF 1D
```

每个向量的验收方式：RTL 解析后字段值必须与 §3 布局一致，且 `protocol.py parse()` 能无异常解析 RTL 构造的同构帧。

### 4.1 R2 生成算法定义（A1 冻结——RTL ↔ PC 逐位一致的唯一依据）

**算法定义**：R2 = Speck64/96(K_terminal, C2)

- Speck64/96（NSA 2013 规范）：字长 32 bit / 分组 64 bit / 密钥 96 bit / 26 轮 ARX（无 S 盒）；最好公开攻击 19/26 轮
- K_terminal = 终端设备密钥（12 字节）。W3 演示 = NSA 公开 KAT 密钥（安全=零，HANDOFF P1-1，W4 从 PUF 稳定位提取）；PC 侧经 DeviceKeyStore 持久化或 REPL setkey 安装
- C2 = 终端反挑战（8 字节计数器，语义见下）。明文即 C2 线上原字节，**无预异或、无重排**

**字节序（speck.py ↔ speck64_96.v ↔ terminal_fsm.v 三方冻结，NSA 官方约定，全小端）**：

- 密钥装载：K 字节 [0:4]→k0→key_in[31:0]，[4:8]→l0→key_in[63:32]，[8:12]→l1→key_in[95:64]。
  W3 演示密钥 `96'h13121110_0b0a0908_03020100` ≡ 字节串 `0001020308090a0b10111213`
- 明文装载：C2[0:4]→y→plaintext_in[63:32]，C2[4:8]→x→plaintext_in[31:0]。
  PC 侧 `Speck6496(K).encrypt(c2)` 直接使用线上字节即得一致结果
- 密文拆包：y_ct（ct[63:32]）先序列化、x_ct（ct[31:0]）后——与 terminal_fsm 的 r2_byte_0..7 映射逐位一致

**C2 计数器语义（terminal_fsm.v 冻结）**：复位值 c2_counter[j] = 8'hA0 + j（字节串 A0..A7）；每次认证每字节独立 +1（无进位传播），周期 256；首次认证 C2 = a1..a8。服务器侧防重放：持久化重放窗（protocol.py C2_REPLAY_WINDOW=128，刻意小于周期以免误拒回绕的真终端；aged-replay 残余仅 CRP 池消耗，R2 签发仍被 PUF 轮门控——权衡与 W4 待办见 HANDOFF）。

**R2 黄金向量（tb_terminal_fsm / tb_level3_protocol / Python tests / REPL 冒烟共用）**：K = `0001020308090a0b10111213`、C2 = `a1a2a3a4a5a6a7a8` → R2 = `7b45b0545e59aa94`。首次认证 RESULT 帧（seq=0x50, result=PASS, hd=5）字节为 `FD 0A 00 00 50 01 02 93 00 00 00 05 7B 45 B0 54 5E 59 AA 94 FF 1D`（与 tb_level3 result_gold 数组同源）。

**线性和金丝雀（A1 阶段 5 接入 CI）**：scripts/test_r2_nonlinearity.py 验证 R2 无仿射/GF(2) 线性结构（含宽扇入；C4 精确判定 + 仿射/宽扇入/xor-tree 三重负对照），防止算法退化回 ~C2 类可预测形态。

**终端侧 R2 验证**：见 §5 第⑥步注——终端用自身 DEVICE_KEY 重算 Speck(K,C2) 与帧中 R2 逐字节精确比对（非 HD 比对）。

## 5. 终端侧消息交换时序（terminal_fsm 的协议视角）

```
终端(PL)                                基站(PC protocol.py)
   │                                           │
   │── ACCESS_REQUEST(tid,nonce,C2) ──────────►│ ①终端主动接入
   │                                           │
   │◄───────────────── CHALLENGE(4 seeds) ─────│ ②基站出题
   │                                           │
   │ [PL 内部: 4 种子→challenge_decode→测量]     │
   │                                           │
   │── RESPONSE_R1(4×8B) ─────────────────────►│ ③终端交卷
   │                                           │
   │◄── RESULT(pass/R2) ───────────────────────│ ④a 直接过 (HD≤TAU_PASS)
   │◄── RESULT(reject) ────────────────────────│ ④b 直接拒 (HD≥TAU_REJECT)
   │◄── EXTRA_CHALLENGE(3 seeds) ──────────────│ ④c 灰区加测
   │                                           │
   │ [灰区分支: 3 种子→再测量]                    │
   │── RESPONSE_R1(3×8B, 24B载荷) ────────────►│ ⑤灰区复测交卷
   │◄── RESULT(最终判决) ───────────────────────│
   │                                           │
   │── CONFIRM(tid,status) ───────────────────►│ ⑥终端确认（验证 R2 后）
   │                                           │
   [终端验证 R2: 用自身 DEVICE_KEY 重算 Speck(K,C2) 与帧中 R2 逐字节
    精确比对, 通过才发 CONFIRM, 失败进 BLOCKED（A1 语义, 非 HD 比对）。
    已知限制: 上电 C2 确定性复位使该验证无跨断电新鲜度——终端侧
    RESULT 帧重放风险见 HANDOFF P1-5（W4 修复）]
```

**关键时序约束**：
- 帧与帧之间无严格间隔要求（字节流传输，靠 STX+LEN 定界）
- 终端收到 CHALLENGE 后到发出 RESPONSE_R1 的延迟 = PUF 测量时间（W2 方案 ~10ms 量级）
- 超时策略：terminal_fsm 对每个等待态设超时计数器（建议 2s，可参数化）

## 6. RTL 实现映射（三个模块的职责边界）

| 模块 | 职责 | 输入 | 输出 |
|---|---|---|---|
| **crc16_mcrf4xx.v** | 纯 CRC 计算：每时钟吃 1 字节，可链式累积 | clk, rst, din, din_valid, init(载入0xFFFF) | crc[15:0]（组合或寄存输出） |
| **mavlink_frame.v** | 帧构造器：字段→完整帧字节流 | msgid, payload 字节流+长度, seq, sysid, compid | frame 字节流 + crc_extra 查表(§3) |
| **帧解析器**（并入 terminal_fsm 或独立 rx_frame.v） | STX 搜索 → 读 LEN → 收满 → CRC 校验 → 提取 msgid+payload | UART 字节流 | msg_id, payload 字节流, frame_ok |
| **terminal_fsm.v** | 协议编排：§5 时序图的 6 态机 | 解析后帧 + PUF done + 64-bit 响应 | 待发帧请求 + 状态指示 |

**RTL 端 CRC_EXTRA 查表**（组合逻辑，case 语句）：
```
msgid == 0x0090 → 0x5A;  0x0091 → 0x5B;  0x0092 → 0x5C;
msgid == 0x0093 → 0x5D;  0x0094 → 0x5E;  0x0095 → 0x5F;
default → 0x00（未知消息，帧应被丢弃）
```

### 6.1 最小集成契约（terminal_fsm 作者必读，auto-review B-F1/F2/F3/F8 结论）

1. **FIFO 强制**：`mavlink_frame` 的 `frame_valid` 以每拍 1 字节输出，而 `uart_tx` 忙时**静默丢弃** `tx_valid`（UART 一字节 ≈8680 拍）。**禁止 frame_valid 直连 tx_valid**——必须经 ≥12B（建议 64B）FIFO：写使能 = frame_valid，读节奏 = 每 tx_done 取 1 字节。
2. **载荷窗口**：`payload_valid` 只允许在 `payload_phase=1` 期间断言（本模块已输出该信号）；窗口外字节被静默丢弃。字节短缺超过 `PAYLOAD_TIMEOUT` 拍 → `frame_err` + 回 IDLE（不挂死）。
3. **SEQ/ID 稳定窗**：`seq_num / sys_id / comp_id` 从 start 前一拍到 frame_done 保持稳定（SEQ 在帧头第 5 字节被采样）；SEQ 自增在 frame_done 之后进行。sysid/compid 本模块无默认值，terminal_fsm 必须显式驱动 8'h01/8'h02（与 protocol.py 默认一致）。
4. **start 纪律**：仅在 busy=0（或复位后）断言，单拍；busy 期间的 start 被静默忽略。
5. **frame_err**：单拍脉冲，上游必须粘滞捕获（tb_mavlink_frame.v 的 err_seen 已示范）。
6. **无线链路容错**（W4 联调验收项）：terminal_fsm 帧解析器必须容忍电台噪声产生的垃圾字节——超时（§5 的 2s）+ 回 STX 搜索 + CRC 失败计数；uart_rx 无 framing-error 输出，字节流不保证干净。
7. **RX payload read discipline** (review B-F4): frame_parser's frame_ok is a single-cycle
   pulse - terminal_fsm MUST latch it sticky. After latching, read payload bytes via
   payload_rd_addr (0-31, combinational). Byte order = frame order (byte 0 at address 0).
   Seed assembly: byte[i] maps to seed[i*8 +:8] (little-endian, same as w2_top.v).
   Read window = frame_ok latch until next frame's first payload byte overwrites
   (>=3.8ms @115200, ample margin). Aborted frames also invalidate the buffer.
8. **w2_top integration gating** (review B-F3): w2_top.v S_IDLE triggers seed reception on
   ANY rx_valid - W3 integration MUST NOT connect frame_parser and w2_top's seed path to
   the same uart_rx in parallel. terminal_fsm must fully replace w2_top's receive path
   (or gate w2_top so it does not receive in W3 mode).

### 6.2 板级前置（W3 顶层 w3_top.v 验收项）

- **时钟单点参数**：顶层以 FREQ_HZ 参数推导 uart 的 CLKS_PER_BIT 与测窗 MEAS_CYCLES，禁止散落硬编码 868/100000（时钟换档时避免 RO 标定静默漂移）；加 1Hz LED 心跳实证时钟频率。
- **复位同步器**：板上异步复位源须经异步断言/同步释放 2FF 后再进全同步复位域。
- **XDC 三件套**：时钟约束 + UART/电台引脚 + w2_waiver.xdc 必须一起 add_files 进 build_w3.tcl（waiver 遗漏 → LUTLP-1 挡比特流；若手绕 DRC → 组合环被优化、RO 频率全错的静默灾难）。
- **比特流-协议配对**：W2 比特流（裸频率协议）与 W3 比特流（MAVLink）不可与错误的 PC 侧脚本混用，README 须写明配对表。

## 7. 变更控制

- 本契约的任何修改必须**同步修改 protocol.py 并重跑黄金向量生成**，双侧一起提交
- hfida.xml dialect 生成后，CRC_EXTRA 占位表（0x5A~0x5F）将被 mavgen 计算值替换——届时两侧同步更新并重跑全部 TB
- 序号 SEQ 由发送方各自维护（终端、基站独立计数），接收方不校验 SEQ 连续性（MAVLink 惯例，丢包容忍）。安全后果：RESULT 帧无新鲜度来源，叠加 C2 上电确定性复位构成终端侧跨断电重放路径（HANDOFF P1-5，W4 修复：nonce 随机化回显或 C2 种子非易失）

## 8. PUF 响应语义与黄金配对表（W4 冻结，2026-10-13）

R1 语义（位级冻结，双侧唯一依据 = src/python/evaluation/puf_model.py，RTL 对拍锚 = tb_challenge_decode 黄金用例）：

- seed → challenge_decode 配对表：8 轮 × 8 对；对 p 的载荷字节 = (order[2p+1]<<4) | order[2p]（低 4bit=环 A，高 4bit=环 B）
- 响应位 bit(r,p) = 1 当且仅当 freq[B] > freq[A]（相等取 0）
- 组装：R1[63-8r-p] = bit(r,p)；序列化大端（byte 0 = 第 0 轮 8 对，MSB 在前）
- 熵：单路 = 16 环总排序 ≈ 2^44；灰区加测每种子同管线独立 64bit
- 信任边界：配对表为纯公开确定性逻辑（无秘密）；设备秘密只在频率向量

冻结黄金配对表（512-bit 寄存器镜像；hex MSB-first 首字节 = round 7 / pair 7；由 scripts/gen_puf_fixtures.py --golden 生成；tb_challenge_decode 与本表与 puf_model 三方一致）：

# PUF_SEED_A  (seed 64'hC0FF_EEBE_EF12_3456)
  ED 95 C6 42 73 1B 8F 0A 3D 64 75 9E 18 2A 0B CF
  54 DE 39 C8 6A 0F 7B 12 49 10 25 86 BA 7F EC 3D
  17 49 F5 08 CD A2 6B E3 09 D6 43 E7 B2 CA 85 F1
  C3 74 51 DF 82 A6 90 BE 0F E8 B7 25 1A C3 D4 69

# PUF_SEED_B  (seed 64'h0F1E_2D3C_4B5A_6978)
  C1 FE 30 D6 87 5A B2 94 31 5B 0F 4E 2D AC 68 97
  30 47 8C EF 9A 5B D1 26 04 B1 6C E3 AF 89 75 2D
  5B 6D 30 2A 84 9E 1F 7C D7 E6 51 9A F4 C3 20 B8
  49 A0 F3 2C B1 87 5E D6 F0 38 D2 5B E7 1C A4 96

# PUF_SEED_C  (seed 64'hFEED_FACE_CAFE_BABE)
  48 67 C9 15 FE A0 BD 23 F8 B2 43 DC 1A 7E 65 90
  CD 50 16 2E A8 7F B9 34 61 40 B2 AC 8F ED 95 73
  87 5E D2 03 F6 1A B4 9C 1A B2 45 C0 9F D6 83 7E
  38 C4 96 A2 EF 50 1D 7B EC FB A1 6D 28 39 57 40

变更控制：任何一侧（puf_model.py / challenge_decode.v / 本节）改动都必须三方同步重生成并重跑 CI（§7 纪律同样适用）。

