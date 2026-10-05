# W1 AI Collaboration Log

## 2026-09-25

### Task
Generate W1 dual-RO ratio measurement RTL for ZC702 (xc7z020clg484-1).

### AI Contribution
- Wrote all RTL modules (ro_ring, ro_div, ro_ratio_top) following team coding standards
- Designed the measurement architecture (ratio-based, pinless, VIO readout)
- Created Vivado batch build scripts (build_w1.tcl, measure_w1.tcl)
- Identified and fixed Nyquist aliasing issue (div_b same-rate sampling)
- Ran Artix-7 proxy synthesis to validate flow end-to-end

### Human Contribution
- Board bring-up (power, USB, Vivado installation)
- Device family installation (Zynq-7000)
- Physical verification on ZC702 (pending)

### AI Tool Usage
- Prompt: "Write a dual ring-oscillator ratio measurement design for ZC702, pinless, using VIO for readout"
- Iterations: 3 (initial → aliasing fix → UI precision update)
- Key human correction: caught ratio direction error (fA/fB vs fB/fA)

---

## W3 Session（2026-10-05 续）

### Task
实现 HF-IDA 协议的 RTL 侧通信栈（CRC 核 + MAVLink v2 帧构造器），并通过双代理 auto-review。

### AI Contribution
- 从 protocol.py 提取字节级契约文档（docs/protocol_contract.md），含 6 个黄金帧向量
- 位精确翻译 CRC-16/MCRF4XX（C→Verilog，30 行核心）
- 实现帧构造器 mavlink_frame.v（8 态 FSM + CRC_EXTRA 查表 + 载荷超时保护）
- 双代理 auto-review（defect PASS / silent-failure P0×1）：修复 P0 集成地雷
  （frame_valid 直连 UART 会丢 99.9% 字节——头注释宣传的错误用法）、
  P2 载荷握手脆弱性（挂死风险 → 超时保护 + payload_phase 握手输出）
- 仿真从 4 用例扩到 9 用例，全部通过；其中仿真过程抓出 4 个教科书级 RTL bug：
  参数位切片陷阱（32[4:0]==0）、CRC 采样差一拍、输出端口忘 assign、done 竞态
- 建立 tools/check_contract_sync.py 契约漂移检测器（protocol.py ↔ 契约 §4 联动）

### Human Contribution
- 触发并主持三轮 auto-review
- 确认"最小集成契约"（FIFO 强制、载荷窗口、SEQ 稳定窗）作为 terminal_fsm 的验收标准

### Key Lessons（已写入代码注释）
1. 对 parameter 做位切片是陷阱：32[4:0] == 0
2. 小端多字节字段中，低字节的时序错会被高字节的正确性部分掩盖——
   只有黄金向量逐字节比对才抓得住
3. "能跑的仿真"可能只是 TB 绕开了所有地雷——审查要问"TB 为什么这么写"

