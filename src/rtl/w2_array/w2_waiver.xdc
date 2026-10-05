# W2 环振组合环豁免（改自 W1 的 w1_ro_waiver.xdc，覆盖 16 环）
# 环振本体就是组合环，这是设计使然；不加豁免 write_bitstream 会被 DRC LUTLP-1 ERROR 阻断。
# W2 的 16 个环在 ro_array 的 gen_ro_ring[0..15] 生成块里，网名带方括号索引，
# 用 -hierarchical + name 过滤一次覆盖全部实例（层次网名经 DONT_TOUCH 保持稳定）：
set_property ALLOW_COMBINATORIAL_LOOPS TRUE [get_nets -hierarchical -filter {NAME =~ "*gen_ro_ring*/u_ro_ring/n1"}]
