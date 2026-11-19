# BIT_MANIFEST_20261119 — 决赛最终位流清单（可复现性证据）

单一真源：RTL 提交 `d9277f6`（N14 点名窗口 + 全部 auto-review 修复）；仓库收尾提交 `4e49aa8`。

| bit | 板 | 大小(B) | 构建时间 | SHA256 | 时序/布局 |
|---|---|---|---|---|---|
| `w3_top_zc706.bit` | 板A (tid=1) | 13321607 | 2026-11-19 18:37 | `D1262FD65D52ABA509A26A13365E138F3B1774830CEDD50DC05DB2BAEA0332D2` | WNS=1.954 |
| `w3_top_zc706_seed2.bit` | 板B (tid=2) | 13321605 | 2026-11-19 18:41 | `F9AD47324C99870D27C723834FF460A32998239CCB77F804F72FBA8D60528B9E` | WNS=2.201 / WHS=0.060 / SEED2_REGION=X1Y0 |

## 说明

- 位流二进制不入库（`.gitignore`：`*.bit`），以本清单的 SHA256 作为发布指纹；重建命令见 `build/tcl/build_w3_board.tcl` / `build_w3_board_seed2.tcl`。
- **换 bit 必重录 PUF 模板**：模板与 RO 环物理布局强绑定；v4c/seed2c 上板后必须重录 tid1/tid2。
- 板B 使用 seed2 布局变体（PBlock 强制 X1Y0 时钟区域），与板A 的指纹可区分——"一机一布局"叙事实物依据。
- 验收链：`VERIFY_WRAPPER_PASS` + xsim 7/7 PASS（含 `tb_poll_gate`）+ `pytest 220 passed`；详见 `build/reports/AUTO-REVIEW_single_hc12_20261119.md`。
