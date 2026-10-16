# Metrics

Competition metrics summary tables. Populate during W5 (G5 gate).

## Required Tables (per competition guide §3.2.4)

| Category | Metrics | Source |
|---|---|---|
| Core | Authentication latency, throughput, success rate | E2E test |
| FPGA | LUT/FF/BRAM/DSP utilization, clock frequency, WNS | Vivado MCP synthesis |
| Security | Entropy (bits), ML attack resistance, replay rejection | ML experiment + threat_poc |
| Reliability | Bit stability, HD distribution | puf_model evaluation |
