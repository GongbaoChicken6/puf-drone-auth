# 攻击PC部署验证（本地文件协议克隆）2026-11-18 20:55

目的：模拟队友全新 clone finals-demo 后零硬件跑通伪基站攻击排练。
注：GitHub 当时直连不通（443 reset），先用本地 file 协议克隆验证 git 内容完整性；push 恢复后远端内容与此克隆同源（同 HEAD 4f38ae7）。

$ git clone --branch finals-demo (local file protocol)
4f38ae7 fix(finals-demo): bench-hardening batch -- N5/N6 follow-ups, v5 fan channel swap, real-board data state
git : Cloning into 'C:\Users\17395\AppData\Local\Temp\puf_teammate_verify'...
所在位置 行:1 字符: 129
+ ... ew($false); git clone --no-hardlinks --branch finals-demo D:/puf-dron ...
+                 ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
    + CategoryInfo          : NotSpecified: (Cloning into 'C...mate_verify'...:String) [], RemoteException
    + FullyQualifiedErrorId : NativeCommandError
 
done.

$ python tools/attack/fake_result_attack.py --simulate
python : [20:54:51] heard ACCESS_REQUEST (28B) fd100000000102900000010000000000��
所在位置 行:1 字符: 199
+ ... te_verify'; python tools/attack/fake_result_attack.py --simulate 2>&1 ...
+                 ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
    + CategoryInfo          : NotSpecified: ([20:54:51] hear...0010000000000��:String) [], RemoteException
    + FullyQualifiedErrorId : NativeCommandError
 
[SIMULATE] heard=3 injected=1
[20:54:51] heard CHALLENGE (44B) fd200000010102910000000000000000��
[20:54:51] heard RESPONSE_R1 (44B) fd200000020102920000000000000000��
[20:54:51] >>> INJECT fake RESULT (PASS + r2=deadbeefcafe0110) triggered by RESPONSE_R1, lag=0.0ms
[SIMULATE] sent msg=RESULT {'result': 0, 'hd': 5, 'r2': b'\xde\xad\xbe\xef\xca\xfe\x01\x10'}

$ pytest attack chain in fresh clone
..............                                                           [100%]
14 passed in 4.75s

$ deploy-critical file presence
tools\attack\fake_result_attack.py => True
src\python\server\protocol.py => True
web\dist\console.html => True
web\dist\assets\console-Ds986EZm.js => True
scripts\demo_start.ps1 => True
build\tcl\program_zc706.tcl => True
tools\hc12\hc12_config_c001.py => True
data\templates\templates.json => True

## GitHub 端到端复验（2026-11-18 21:00，push 成功后）

$ git clone -b finals-demo https://github.com/GongbaoChicken6/puf-drone-auth.git
→ clone OK, HEAD = 4f38ae7 fix(finals-demo): bench-hardening batch -- N5/N6 follow-ups, v5 fan channel swap, real-board data state

$ python tools/attack/fake_result_attack.py --simulate（GitHub 克隆内）
[21:00:15] heard ACCESS_REQUEST (28B) / heard CHALLENGE (44B) / heard RESPONSE_R1 (44B)
[21:00:15] >>> INJECT fake RESULT (PASS + r2=deadbeefcafe0110) triggered by RESPONSE_R1, lag=0.0ms
[SIMULATE] heard=3 injected=1
[SIMULATE] sent msg=RESULT {'result': 0, 'hd': 5, 'r2': b'\xde\xad\xbe\xef\xca\xfe\x01\x10'}

远端校验: refs/heads/finals-demo = 4f38ae7ffe8f34add738bfcf65f2a1b41d5d9b9c = 本地 HEAD（ls-remote 实测）。
临时克隆已删除。结论: 队友按此流程克隆即可零硬件演练假认证。
