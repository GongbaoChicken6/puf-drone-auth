# Testbench 编写规约

> 2026-10-27/28 两次真硅事故（uart_rx 挂死、serve 超时钉死）换来的四条硬规则。
> CI 门禁按 `TB_.*_PASS` 正则判定，违反任一条的 TB 可能"绿着骗人"。

## 规则一：每个 TB 必须自带看门狗 + 双向确定性收尾

- 看门狗超时与正常结束都必须 `$finish`，且输出唯一判定行（`TB_XXX_PASS` / `TB_XXX_FAIL errors=N`）
- 失败路径的内部诊断必须先于看门狗打全：**看门狗预算 > TB 内部所有超时上限之和**（反例：tb_uart_rx v1 的 80µs 看门狗 < 最坏失败路径 ~140µs，变异跑时诊断被截断）

## 规则二：活性锁规则（最重要）

凡"通过条件"是**死逻辑也能到达的终态**（超时→BLOCKED、等待→默认态、静默→空闲），必须配**正向证据计数器**。

- 病例：tb_w3_top T1 原判据 = TX 活动 + 超时后 led_result=3(BLOCKED)。uart_rx 整体挂死时同样超时进 BLOCKED——判据对 RX 死亡完全失明，bug 带病上线两天
- 良方：tb_w3_top T1 现为 TX/RX 等价锁（rx_valid_cnt === tx_done_cnt + TX 活性下界），任何挂死/丢字节/多字节都会被抓

## 规则三：修 bug 配的新 TB 必须做变异验证

把 pre-fix（旧 bug）代码喂给新 TB 跑一次，**必须 FAIL**——证明测试真能抓住它要防的 bug。两个先例：
- tb_uart_rx：旧 bit_idx 清零版喂入 → FAIL_ZERO_ECHO ✓
- TestServeReadSemantics：idle read(read_size) 还原 → 延迟断言 2950ms FAIL ✓

## 规则四：激励源优先用被测件的孪生件（BFM 模式）

- 手工驱动波形（blocking/non-blocking + @(posedge/negedge)）在快速时钟（CPB 小）下有采样竞态，v1 版 tb_uart_rx 连翻三次车
- 良方：用同协议的成熟模块当激励源（tb_uart_rx 用 uart_tx 作 BFM；tb_w3_top 用回环），时序天然精确
- 回环 TB 判字节用"计数递增 + 字节锁存"（基线在发送前锁存），不要追单拍脉冲——回环里 tx_done 与 rx_valid 近同拍，先发后等会漏计

## 附：常量耦合警告

TB 内的等待上限（边沿数）与看门狗时长按特定 CLKS_PER_BIT 标定（如 tb_uart_rx 的 CPB=32），改 CPB 必须同步换算这些常量，否则会误报 TX 超时。
