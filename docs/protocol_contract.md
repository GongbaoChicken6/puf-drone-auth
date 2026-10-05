# HF-IDA 字节级协议契约（RTL ↔ PC 唯一依据）

> **真相源声明**：本契约从 `src/python/server/protocol.py` 的实际实现中逐字节提取。
> **RTL 实现必须与本文件一致，而非与 docs/project_design.md 一致**——B 线实现时对原设计做了
> 5 处修正（C2 位置、N_CHALLENGES=4、CRC_EXTRA 占位表等），代码是唯一真相源。
> 文中所有黄金向量由 protocol.py 生成并用 parse() 回验通过（2026-10-05）。

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

**RESULT 码**：0=PASS, 1=REJECT, 2=ERROR, 3=POOL_EMPTY；HD 特殊值 0xFF=HD_NONE（即错误路径无 HD）。

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
```

每个向量的验收方式：RTL 解析后字段值必须与 §3 布局一致，且 `protocol.py parse()` 能无异常解析 RTL 构造的同构帧。

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
   [终端验证 R2: 与 BRAM 中基站模板做 HD 比对,
    通过才发 CONFIRM, 失败进 BLOCKED]
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

## 7. 变更控制

- 本契约的任何修改必须**同步修改 protocol.py 并重跑黄金向量生成**，双侧一起提交
- hfida.xml dialect 生成后，CRC_EXTRA 占位表（0x5A~0x5F）将被 mavgen 计算值替换——届时两侧同步更新并重跑全部 TB
- 序号 SEQ 由发送方各自维护（终端、基站独立计数），接收方不校验 SEQ 连续性（MAVLink 惯例，丢包容忍）
