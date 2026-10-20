# verify_wrapper.ps1 -- 板级 wrapper 离板语法门禁（xvlog + xelab，迁移计划 Phase 4）
# 用法: powershell -File build\ps1\verify_wrapper.ps1 [-Wrapper w3_top_zc706]
#
# 背景：wrapper 不在 ci_regression.ps1 的编译清单内（设计如此，clk_wiz IP 不入仓库），
#       CI 全绿不代表 wrapper 可编译——本脚本是唯一语法门禁，换板/改 wrapper 后必跑。
# 语义：不带 -d PUF_MODEL_SIM（走真 ro_array 板级网表，环振组合环 WARNING 属设计
#       使然）；clk_wiz_0 stub 写 %TEMP%（不入仓库，防与 Vivado 工程内真 IP 冲突）。
param(
    [string]$Wrapper = "w3_top_zc706"
)
$ErrorActionPreference = "Continue"
Set-Location (Join-Path $PSScriptRoot "..\..")
$vivado = "D:\vivado\2026.1\Vivado\bin"
if (-not (Test-Path "$vivado\xvlog.bat")) {
    Write-Host "VIVADO NOT FOUND at $vivado"; exit 1
}

# clk_wiz_0 仿真 stub（与真 IP 端口一致：差分入 + reset + 单端出 + locked）
$stub = Join-Path $env:TEMP "clk_wiz_0_stub.v"
@'
module clk_wiz_0 (input wire clk_in1_p, input wire clk_in1_n, input wire reset,
                  output wire clk_out1, output wire locked);
  assign clk_out1 = clk_in1_p;
  assign locked   = ~reset;
endmodule
'@ | Set-Content -Path $stub -Encoding ascii

# 编译清单 = build_w3_board.tcl 的 add_files 集（w2_top 不需要：w3_top 不例化它）
$rtl = @(
    "src\rtl\w1_ratio\ro_ring.v", "src\rtl\w1_ratio\ro_div.v",
    "src\rtl\w2_array\ro_array.v", "src\rtl\w2_array\challenge_decode.v",
    "src\rtl\w2_array\ro_entropy.v",
    "src\rtl\common\crc16_mcrf4xx.v", "src\rtl\common\mavlink_frame.v",
    "src\rtl\common\frame_parser.v", "src\rtl\common\byte_fifo.v",
    "src\rtl\common\uart_tx.v", "src\rtl\common\uart_rx.v",
    "src\rtl\common\speck64_96.v",
    "src\rtl\w3_protocol\terminal_fsm.v", "src\rtl\w3_protocol\w3_top.v",
    "src\rtl\w3_protocol\$Wrapper.v"
)

Write-Host "=== verify_wrapper: xvlog ($Wrapper + 14 RTL + clk_wiz stub) ==="
& "$vivado\xvlog.bat" @rtl $stub
if ($LASTEXITCODE -ne 0) { Write-Host "VERIFY_WRAPPER_FAIL (xvlog exit $LASTEXITCODE)"; exit 1 }

Write-Host "=== verify_wrapper: xelab $Wrapper (real ro_array netlist) ==="
& "$vivado\xelab.bat" -debug typical $Wrapper -s "$($Wrapper)_chk"
if ($LASTEXITCODE -ne 0) { Write-Host "VERIFY_WRAPPER_FAIL (xelab exit $LASTEXITCODE)"; exit 1 }

Write-Host "VERIFY_WRAPPER_PASS"
exit 0
