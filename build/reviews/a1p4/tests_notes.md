# tests 审查员断点笔记（CHECKPOINT — 明日继续）

状态：用户要求暂停。已完成部分已带证据落盘 tests.json（8 条：P2×3 + P3×5）。

## 已完成
- 通读 tests/test_a1_phase4.py（281 行，20 用例 = 6 SpeckHSM + 7 DeviceKeyStore + 4 C2ReplayGuard + 2 E2E + 1 SimulatedTerminalC2）
- 通读 git diff：hsm.py / protocol.py / main.py / ci_regression.ps1 / .gitignore
- 真相源核对 src/python/common/speck.py（NSA KAT：key=0001020308090a0b10111213 pt=65616e7320466174 ct=6c947541ec52799f）
- RTL 契约核对 terminal_fsm.v:88-117/150/402-403（C2 复位 0xA0+j、逐字节 +1 无进位、首挑战 a1..a8）
- 实跑 python tests\test_a1_phase4.py：20/20 OK，0.083s，exit 0

## 明日待办
1. 量化 flake 风险：读 src/python/server/threshold.py（TAU_PASS/TAU_REJECT/decide_scaled），算 4×64bit@p=0.02 落灰区概率，决定 F8 定级是否上调
2. 规格锚定：docs/HANDOFF_SUMMARY.md L41-45/L84-90 与 docs/plans/A1_speck_plan_v3_final.md L46-51 验收项 vs 测试矩阵逐条映射
3. 核对 LoopbackTransport.counter_challenge (main.py:162) 与 SimulatedTerminal 计数器语义一致性（E2E 走 transport 路径）
4. 补齐『缺失高价值测试 Top5』终稿并入 tests.json（草稿：①cmd_c2reset/setkey REPL 集成测试 ②重启重放拒绝 E2E ③on_response c2 覆盖分支 + None 回退 R2=Speck(K,0^8) ④精确回绕向量断言 ⑤E2E flip_prob=0 去随机化）
5. tests.json 终稿化（当前为断点快照，可直接覆写）后 send_message 汇报 lead

## 环境事实
- 输出目录 D:\puf-drone-auth\build\reviews\a1p4\ 已存在（defect.json/silent.json/spec.json 属其他审查员，勿动）
- 仓库根禁止建文件；探针一律放 $env:TEMP
- 黄金向量（tb_terminal_fsm）：key 0001020308090a0b10111213, C2 a1..a8, R2 7b45b0545e59aa94 —— tests:48-51 已锚定且实跑通过
