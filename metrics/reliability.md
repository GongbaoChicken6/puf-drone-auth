# Reliability 指标

| 指标 | 值 | 分级 | 来源 |
|---|---|---|---|
| HD 分布(同设备 vs 跨设备) | μ=1.38(max 5) / μ=36.49(min 16) bit | **LIVE** | viz/hd_sample.json(离线采样;复现命令见文件内) |
| ROC/EER | EER=0.00% · AUC=1.0000(n=500+4000) | **LIVE** | viz/roc_summary.json(--roc 离线;参数见 params) |
| 稳定掩码 | 64/64 | **STATIC** | templates sidecar(.stability.json) |
| 温度/电压 reliability | 见 viz 页 V6 曲线 | **MODEL** | ROPairingPUF.measure 推演;导出件 desc 自带口径 |
| 板上温漂实测 | 待板 | **待板** | DS13 修复后高低温实验 |
