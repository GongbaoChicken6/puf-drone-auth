# W1 环振组合环豁免（必加——不加则 write_bitstream 被 DRC LUTLP-1 ERROR 阻断）
# 环振本体就是组合环，这是设计使然；逐环豁免（层次网名经 DONT_TOUCH 保持稳定）：
set_property ALLOW_COMBINATORIAL_LOOPS TRUE [get_nets u_ro_a/n1]
set_property ALLOW_COMBINATORIAL_LOOPS TRUE [get_nets u_ro_b/n1]
