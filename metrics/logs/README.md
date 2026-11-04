# metrics/logs — 原始日志

所有文本日志均为 **UTF-8**（个别文件带 UTF-8 BOM，不影响 `grep`、Python 或编辑器读取）。

2026-11-04 将以下 8 份原 UTF-16LE 日志转为 UTF-8，正文与换行未改：

- `1101_ci_regression_full.txt`
- `1101_ml_expA.txt` / `1101_ml_expB.txt` / `1101_ml_expC.txt`
- `1101_muttest_xelab.txt` / `1101_muttest_xsim.txt` / `1101_muttest_xvlog.txt`
- `1101_threat_poc.txt`

Speck64/96 的 53 周期时延证据在 `sim/tb/tb_speck.v` 的 T9 断言（`start→done ≤ 60` 周期，标称 53）；`tb_speck` 的 18/18 CI 通过记录见 `sim/results/ci_summary_20261103.txt`。
