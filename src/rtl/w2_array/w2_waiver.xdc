# W2 环振组合环豁免（改自 W1 的 w1_ro_waiver.xdc，覆盖 16 环）
# ⚠ 2026-10-20 实测勘误（auto-review 内容审查）：本文件的 get_nets -hierarchical 在
#   XDC 读取时（综合前）nets 不存在 -> 静默匹配 0 对象，豁免在 bitstream DRC 从未生效；
#   且 generate 块与实例间分隔符是 '.' 非 '/'，原层级模式即便综合后也匹配不上。
#   现由 build/tcl/build_w3_board.tcl 在综合后以 -hierarchical + {*u_ro_ring/n1} 应用
#   （32 网响亮校验，BITSTREAM_SUCCESS WNS=1.060 实证）。本文件保留作文档与 dev 流。
# 环振本体就是组合环，这是设计使然；不加豁免 write_bitstream 会被 DRC LUTLP-1 ERROR 阻断。
# W2 的 16 个环在 ro_array 的 gen_ro_ring[0..15] 生成块里，网名带方括号索引，
# 用 -hierarchical + name 过滤一次覆盖全部实例（层次网名经 DONT_TOUCH 保持稳定）：
set_property ALLOW_COMBINATORIAL_LOOPS TRUE [get_nets -hierarchical -filter {NAME =~ "*gen_ro_ring*/u_ro_ring/n1"}]
# ⚠ auto-review P3 注记（2026-11-01）：每次板级构建本 XDC 在综合前/实现前各触发一次
#   WARNING 12-1023 + CRITICAL WARNING 17-55（静默 0 匹配，已知无害模式）——请勿以"清零
#   CRITICAL WARNING"为由删除 build_w3_board*.tcl 里综合后重应用段，否则 32 个 LUTLP-1
#   将回到 bitstream DRC 才暴露。
