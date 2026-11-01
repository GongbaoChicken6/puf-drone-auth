# 服务器端认证逻辑审计报告（ar-server-hd-r1）

日期：2026-11-01　范围：D:\puf-drone-auth\src\python\server\（只读审计，git 工作树 clean）
问题：REPL auth 1 打印的 total HD 是真比对吗？响应位真的来自串口对面的板子吗？

## 一、findings（JSON）

见同目录 findings JSON（与本报告结论一致，sources=ar-server-hd-r1）。

## 二、核心证据链（行级）

1. auth 数据流（串口模式）：main.py:846 → cmd_auth(main.py:630) → protocol.on_access_request(protocol.py:486 取种子、496 打包 CHALLENGE) → transport.respond(main.py:655) = SerialTransport.respond(main.py:236-257)：reset_input_buffer → serial.write(frame) → serial.read(44B) → 不足即 raise TimeoutError → HFIDAProtocol.parse(reply)（CRC 校验 protocol.py:396-398）→ 返回 fields["r1s"]。无任何本地生成路径。
2. 同一份 1101 证据日志里出现真实超时（got 0/44 bytes，日志 38/42/45 行），auth 直接 [ERROR] 中止、无判据输出——静默回退路径不存在的行为学反证。
3. total HD 计算：protocol.py:526-530 hds=templates.hamming_distances(tid, session.seeds, list(r1s)); hd_sum=sum(hds); decide_scaled。template_db.py:354-362 逐种子取 enrolled 响应做 (value ^ template_int).bit_count()。RESULT 帧 hd=min(hd_sum,0xFE)（protocol.py:749-753），_print_verdict 原样打印（main.py:569-576）。
4. 离线复核（本审计执行）：取日志 RXRAW/TXRAW 原始帧，按 templates.json 重算每响应 HD，三轮 serve 分别得 4/1/3，与 RESULT 帧 hd 字节 0x04/0x01/0x03 完全一致——打印的 HD 就是真实比对结果。
5. 门限：TAU_PASS=6/TAU_REJECT=16（每 64bit 响应），4 响应轮 PASS≤24、REJECT≥64（threshold.py:87-91）。HD=0/1、10-24 loopback HD=6 均≤24，PASS 与代码一致。
6. spoof 1 串口模式：SerialTransport.respond 接受 impostor 形参（main.py:241）但函数体从不使用；impostor 仅在 LoopbackTransport.respond（main.py:203-206）生效。故串口下 spoof≡auth，今晚 spoof PASS HD=0 是真板应答，假冒演示在串口模式从未测过任何东西。
7. 模板格式与种子复用：templates.json {"seed_hex16":"resp_hex16"}，enroll 存 3 次测量逐位多数票（enroll.py:86-90, majority_bytes 25-35）；auth 种子从同一 enrolled 池抽取（crp_pool.py:198-205, available−used）。已验证 pool_1.json 全部 100 available+32 used 种子均有模板条目；种子复用是 CRP 设计而非缺陷，且模板 100 个响应两两 HD 均值 32.00（19~48），不可能因种子复用产生 HD≈0。
8. 响应确具区分度：serve 三轮线上 R1 与模板逐响应差 0~2 bit 且逐轮漂移（4/1/3），既非恒等回显（会恒 0）也非随机（会 ~32/响应→REJECT）。应答方确实掌握 seed→response 映射。

## 三、结论

H3（服务器侧比对/数据源 bug）不成立。比对为真、数据源为串口线。双板 HD≤1 的根因在服务器上游（RTL 响应生成与硅片无关或弱相关），归 D2 RTL 审计。服务器侧局限：RESPONSE_R1 帧不含板卡标识（protocol.py 头注 22-23 行、serial_server.py:22-26），哪块物理板应答只能靠操作者 JTAG 记录旁证。

## 附：次要发现（不影响判定）

- spoof 串口语义缺陷（medium，见 findings）。
- staged 种子泄漏（low）：on_access_request 对同一 tid 覆盖 _staged（protocol.py:491-495），30s 清扫窗口内被超时中止会话的种子永久留在 used 池（今晚 pool_1 used=32=8×4 抽取，日志可见仅 7 轮）。
