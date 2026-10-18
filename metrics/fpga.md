# FPGA 资源与时序(ZC702 · XC7Z020)

| 指标 | 值 | 分级 | 来源 |
|---|---|---|---|
| Slice LUTs | 4443 (8.35%) | **STATIC** | build/vivado_mcp/util_t2fix.rpt(最新) |
| Slice Registers(FF) | 6545 (6.15%) | **STATIC** | build/vivado_mcp/util_t2fix.rpt(最新) |
| WNS / 时钟频率 | 待板(综合态 NA) | **待板** | timing_*.rpt 综合态无约束;实现后补 |
| 判定阈值 TAU_PASS/TAU_REJECT | 6 / 16 | **STATIC** | src/python/server/threshold.py 代码常量(实读) |
