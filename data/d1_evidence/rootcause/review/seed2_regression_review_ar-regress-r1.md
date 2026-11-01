# seed2 修复链 · 回归/配置管理审查(ar-regress-r1,2026-11-01)

范围: git 242d9bd..1760b72 (c348baa → 062c776 → a94775f → 1760b72; HEAD==1760b72 已核实)
标尺: 后续改动会不会悄悄破坏这套修复而不被发现
方法: git log/diff/show/grep/check-ignore/ls-files + 逐文件行级核读,零仓库改动
结论: 无 P0;5×P1、4×P2、2×P3。四个提问的答案全部是"现在没有机制能发现/没有定义",且每项都有秒级~小时级的最低成本修复。

## 四问直答
1. bit↔源陈旧联动: 无任何机制(CI 不跑综合实现、无自动触发、bit 无内嵌标识、无 MANIFEST;生产 W3 bit 甚至未入库,.gitignore:85 忽略;1760b72 提交信息'production bit already tracked'与 git ls-files *.bit 事实不符)。
2. 三脚本保护: 零。scripts/ 对三个 tcl 零引用;arm_dap 教训(7fb8e69)未制度化,范围反而新增两个无保护脚本。修复=照 wrapper M-LOCK 范式加 board-tcl 文本锁+无参冒烟。
3. 双 bit 管理: 文件名可区分但仅止于此——program_zc706.tcl 接受任意路径只回显路径,bit 无 USR_ACCESS,协议无 VERSION 命令;P2/P3 对错烧不敏感,P1 翻转会被预登记失败分支误读为'PBlock 不足'。修复=文件名变体解析+横幅+USERID+MANIFEST 哈希核对。
4. 预登记回填: 未定义(表无回填列/owner/口径),且两个登记证据 .log 均被 .gitignore:8 '*.log' 静默拦截(build_seed2.log 现状即未入库),会复刻 D1 夜靠 force-add 才入库的先例。修复=加 '!data/d1_evidence/**/*.log' 否定行+prereg 追加结果回填表。

## 明细
### #1 P1 scripts/ci_regression.ps1:1 [bit-source-staleness / no-provenance]
Q1: seed2 变体 bit 与 RTL/约束源之间不存在任何陈旧联动检测。ci_regression.ps1 只覆盖 xvlog/xelab/xsim 仿真与 Python 门禁,从不运行 Vivado 综合/实现;仓库无 Makefile、无 .github/workflows 等任何自动触发(CI=README:33 手工一行)。seed2 bit 虽已入库(1760b72),但 outdir 无 MANIFEST 绑定源码 commit/哈希;生产 W3 bit 甚至完全不在版本库(.gitignore:85 整目录忽略,git ls-files *.bit 仅 4 个:seed2/两个 W1 旧 bit/一个 skill fixture)——1760b72 提交信息声称 'production bit already tracked' 与 HEAD 事实不符。同一生产 bit 名义路径历史上有 ≥4 个 WNS 版本(0.406/1.060/2.023/1.873),路径身份≠内容身份:明天改一行 src/rtl 注释重建,或换机器重建,没有任何机制报警。

> 证据: # ci_regression.ps1 -- Full regression: ALL RTL + ALL TBs (W1+W2+W3) | .gitignore:85 'build/board_zc706/' | sprint_1030_1103.md:11 '| 生产 bit | w3_top_zc706.bit（WNS=+1.873）双板验证过 | build/board_zc706 |' | bringuo_fix_20261022.md:30 'BITSTREAM_SUCCESS **WNS=2.023**' | phase1-4_8a_evidence.md:39 'BITSTREAM_SUCCESS WNS=1.060' | HANDOFF_20261023_根因翻案.md:61 'BITSTREAM_SUCCESS WNS=0.406'

### #2 P1 build/tcl/build_w3_board_seed2.tcl:95 [missing-build-manifest]
Q1(补充): 构建脚本产出 bitstream 时零溯源记录——不写 git commit、不写源文件/约束/脚本自身的 SHA256、不写 Vivado 版本,仅有 WNS 和区域名打进 stdout(而构建日志又被 *.log 忽略,见 P1#4)。bit 一旦离开构建机,既无法证明它由哪个源状态生成,也无法与重建结果做字节级比对。修复=在 write_bitstream 后追加 exec git rev-parse HEAD + 对 add_files 全部源/约束/tcl/bit 计算 SHA256,落盘 $OD/MANIFEST.txt 并随 bit 一起提交;ci_regression.ps1 加 10 行纯文本锁重算 MANIFEST 所列文件哈希比对工作区——无需跑 Vivado,秒级即可发现'源已变而 bit 未重建'。

> 证据: write_bitstream -force $OD/w3_top_zc706_seed2.bit
> puts "BITSTREAM_SUCCESS WNS=$wns SEED2_REGION=$pick"

### #3 P1 build/tcl/program_zc706.tcl:27 [unprotected-board-script / arm_dap-lesson-not-institutionalized]
Q2: program_zc706.tcl / build_w3_board_seed2.tcl / query_targets.tcl 三个板级脚本没有任何回归锁或冒烟测试保护:scripts/ 全目录对三者零引用(git grep 实证为空),ci_regression.ps1 唯一的文本锁是 w3_top_zc706.v 三元素锁,未延伸到任何 tcl。arm_dap 教训(7fb8e69:精确匹配防御误杀 FPGA、exit 7,只能靠 D1 实烧才发现并验证)没有任何制度化防线;本审查范围反而又新增两个无保护脚本(c348baa 加 query_targets.tcl、a94775f 加 build_w3_board_seed2.tcl),暴露面扩大。修复=照 wrapper M-LOCK 现成范式加 board-tcl 锁:断言 program 的 xc7z045* 前缀扫描/PROGRAM.FILE/错误退出码语义、seed2 的 PBlock 段/32 环守卫/TIMING_FAILED 门禁/ring_sites 写出、query_targets 只读(不含 program_hw_devices);可选 vivado -mode batch 无参冒烟(参数守卫先于一切硬件调用,无需板卡)。

> 证据: 7fb8e69: 'fix(tcl): program_zc706 selects xc7z045* device by PART prefix scan instead of blind index 0 -- ... exact-match defense rejected the FPGA and exited 7; prefix match keeps arm_dap rejection while accepting bare name (D1 burn verified: PROGRAM_OK, 8s)' | ci_regression.ps1:162 '# M-LOCK(auto-review #3): wrapper 3-element text lock - wrapper is NOT compiled by xsim' | scripts/ 内对三个 tcl 的引用: git grep 结果为空

### #4 P1 data/d1_evidence/rootcause/seed2_board_preregistration.md:22 [evidence-archival-blocked / backfill-undefined]
Q4: 预登记文件自己登记的两个证据文件都被 .gitignore 静默拦截:'rootcause/build_seed2.log' 与未来的 'd1_evidence/1101_seed2_唯一性实验.log' 均命中 .gitignore:8 '*.log'(git check-ignore 实证);build_seed2.log 当前状态即'已登记未入库'(git status '!!',1760b72 只提交了 rpt 未提交该 log)。若不 force-add,'做了实验没归档'必然复现(D1 夜 .log 是靠 force-add 才进库的先例)。同时判据表(第 9-14 行)只有 #/实验/预期/判定 四列,无实测回填列、无书写人/复核人、无 PASS/FAIL 口径、无日志行号引用与回填期限要求——回填机制完全未定义。修复:①.gitignore 加一行 '!data/d1_evidence/**/*.log' 解封整类证据;②prereg 追加'结果回填'表(P1-P4 各行:实测 HD/verdict/日志路径+行号/操作者/日期/bit SHA256),声明回填未完成实验不算关闭;③可选:tools/check_contract_sync.py 加'回填行非空'检查挂进 CI。

> 证据: - 构建：rootcause/build_seed2.log、board_zc706_seed2/ring_sites_seed2.rpt
> - 板端：d1_evidence/1101_seed2_唯一性实验.log（届时生成） | git check-ignore -v: '.gitignore:8:*.log	data/d1_evidence/rootcause/build_seed2.log' | git status --porcelain --ignored: '!! data/d1_evidence/rootcause/build_seed2.log'

### #5 P1 build/tcl/program_zc706.tcl:12 [bit-variant-unidentifiable / mis-burn-undetectable]
Q3: 双 bit 并存下烧错无法发现。文件名可区分(w3_top_zc706.bit vs w3_top_zc706_seed2.bit)但仅止于此:脚本接受任意存在的 bit 路径,唯一回显是路径字符串;两个 bit 均未内嵌 USR_ACCESS/USER_CODE(build/tcl grep 零命中),RTL/协议无任何 VERSION/构建 ID 查询命令(src/rtl grep 零命中)——烧完之后无法从板上问出'这是哪个布局变体'。且烧写易失(:7 注释)意味着每次上电都重新烧=反复冒险。危害路径:错烧生产 bit 到 seed2 板,P2/P3(自一致性)照常 PASS,只有 P1 翻转,而预登记失败分支(:17)会把结果误读为'PBlock 不足以致变'→得出错误根因结论+浪费 seed3 重建周期。修复:①program 脚本从文件名解析变体标签并打横幅(VARIANT: seed2@X1Y0 / PROD),非常规命名拒烧;②两个 build tcl 设 BITSTREAM.CONFIG.USERID(prod=0x00000001, seed2=0x5EED0002),烧后 Hardware Manager 回读核对;③烧前按 MANIFEST 重算 bit SHA256 并回显。

> 证据: set BIT [lindex $argv 0] | if {![file exists $BIT]} { puts "ERROR: bit 文件不存在: $BIT"; exit 2 } | puts "PROGRAM: 目标 $BIT" | # 说明：JTAG 烧写是易失的——断电后比特流丢失，重新上电需再次烧写（SW11=JTAG 启动模式所致）。 | 预登记:17 '- P1 得 PASS（HD≤24）：seed2 排序与生产仍相同（PBlock 不足以致变）→ 改用双区域拆分环阵列或逐环 LOC 重定位，重建再测'

### #6 P2 data/d1_evidence/rootcause/seed2_board_preregistration.md:1 [prereg-not-pinned-to-artifact]
Q4/Q3: 预登记判据未钉死适用对象的艺术身份——无 seed2 bit 的 SHA256(13321607 字节,1760b72)、无源码 commit、无区域码 X1Y0 的白纸黑字。若 seed2 在烧板前因任何原因重建(哪怕源未变,bit 也可能因时间戳差异不同字节),预登记在名义上仍'适用'于另一个产物;P4 的生产 bit 同样无哈希锚点。修复:prereg 头部加三行(生产 bit SHA256=…、seed2 bit SHA256=…、region=X1Y0、基线 commit=1760b72),烧板前现场重算核对,不一致即判'预登记失效需重立靶'。

> 证据: # 布局变体B（seed2）板端验收判据 · 预登记（2026-11-01 17:25，构建进行中、烧板之前立靶） | 生产 bit 与 seed2 bit：同 RTL/同约束/同时序门禁，唯一差异 = 32 个环振单元 PBlock 重定位到不同时钟区域。

### #7 P2 build/tcl/build_w3_board_seed2.tcl:69 [implicit-region-pick-not-pinned]
Q1: seed2 差异化的核心——目标时钟区域——不是常量,而是 '排序中点'运行时推导:换一个 -part 参数、或未来 Vivado 版本改变 get_clock_regions 枚举,区域会静默漂移,而预登记/提交信息/ring_sites 证据全都假设 X1Y0。修复:钉死 set pick "X1Y0" 并断言其 ∈ get_clock_regions(否则响亮退出),两行改动;同时把 pick 写进 MANIFEST。

> 证据: set allcr [lsort [get_clock_regions]]
> puts "SEED2 clock regions available: $allcr"
> set pick [lindex $allcr [expr {[llength $allcr] / 2}]] | ring_sites_seed2.rpt:1 '# seed2 ring cell placement (region X1Y0)'

### #8 P2 build/tcl/build_w3_board_seed2.tcl:20 [hand-duplicated-filelist]
Q1/Q2: seed2 脚本的 add_files 15 文件清单是对 build_w3_board.tcl:25-41 的手工复制,注释声称'其余逐字复用生产流程'(:10),实则是拷贝而非复用。未来生产清单增删文件而忘了同步 seed2(或反之),两变体的净表就开始分叉——缺文件通常响亮报错,但清单语义分叉(多列/少列一个非必需文件)可能静默改变 P&R 输入。修复(零 Vivado 成本):ci_regression.ps1 加一段纯文本比对,断言两个 tcl 的 add_files 列表元素级一致;或把清单抽成 build/tcl/w3_filelist.tcl 由两脚本 source。

> 证据: #   3) 其余逐字复用生产流程（同源/同约束/同豁免/同时序门禁） | add_files [list \ $SRC/rtl/w1_ratio/ro_ring.v ... $SRC/rtl/w3_protocol/w3_top_zc706.v ](与 build_w3_board.tcl:25-41 逐行同构的手工副本)

### #9 P2 .gitignore:104 [ignore-pattern-conflicts-with-new-artifact-convention]
配置管理矛盾未消除:1760b72 把 build/board_zc706_seed2/ 四个产物 force-add 越过的不仅是 *.bit(:30),还有 build/board_zc706_*/(:104)——该模式仍留在 .gitignore。后果:预登记失败分支(:17)明确计划的 seed3 变体,其 ring_sites_seed3.rpt 等新证据将再次被静默忽略(git check-ignore 实证:'build/board_zc706_seed2/ring_sites_seed3.rpt' 命中 :104),每次都要靠记得 force-add。修复:加否定行 '!build/board_zc706_seed2/**'(及未来变体目录的通配策略),或把变体证据统一迁入已放行的目录(如 build/reviews/、data/bitstreams/)并在 docs 里写明约定。

> 证据: build/board_zc706_*/ | git check-ignore -v: '.gitignore:104:build/board_zc706_*/	build/board_zc706_seed2/ring_sites_seed3.rpt' | 1760b72 message: 'artifact: layout-variant-B bitstream + placement/timing evidence (force-added past *.bit ignore; production bit already tracked)'

### #10 P3 build/board_zc706_seed2/ring_sites_seed2.rpt:2 [evidence-report-partially-empty]
Q1(轻微): 落位证据 192 数据行中 32 行(每个 gen_ro_ring[*].u_ro_ring 层次单元一行)SITE 列为空——get_property SITE 对层次单元返回空串;有效站点信息在 160 个叶子单元行(SLICE_X125~141/Y34~51,与 X1Y0 带宽吻合)。证据可用但有噪,且报告自身不校验'全部站点确在目标区域内'(目前靠 placer 遵守 pblock 这一间接保证)。修复:改用叶子单元过滤(如 -filter {IS_PRIMITIVE} 或 LOC 属性),并在报告尾加 REGION_CHECK 行(min/max X,Y 落在区域内→OK)。

> 证据: u_top/u_ro_array/gen_ro_ring[0].u_ro_ring (SITE 列为空) | u_top/u_ro_array/gen_ro_ring[0].u_ro_ring/n1_inferred_i_1 SLICE_X127Y39 | 统计: 192 数据行,160 行含站点,32 行为空

### #11 P3 scripts/ci_regression.ps1:106 [wrapper-not-compiled-in-ci (known/accepted,compounding)]
Q1(已知缺口的叠加项): CI 的 RTL 编译清单不含 w3_top_zc706.v(板级 wrapper,因 clk_wiz IP 不可 xsim 而只被三元素文本锁覆盖)——wrapper 上三个锁定模式之外的任何语法/结构破坏(如括号失衡)CI 全绿,直到板级 Vivado 构建才炸。这是文档自认的取舍(zc706_polarity_fullfix_plan_20261023.md:27),非本范围引入,但它与本报告 P1#1/P1#2 同向叠加:源→bit 的链路上,CI 的最后一段护栏只覆盖 wrapper 的 3 个正则。低成本缓解:xvlog 清单里尝试加 w3_top_zc706.v 并对 clk_wiz 实例做 stub(或至少加括号配平/info complete 级文本检查)。

> 证据: $rtl = @( "src\rtl\w1_ratio\ro_ring.v", ... "src\rtl\w3_protocol\w3_top.v" )(清单止于 w3_top.v,无 w3_top_zc706.v) | docs/process/plans/zc706_polarity_fullfix_plan_20261023.md:27 '- **CI 不编译 wrapper'


## 修复优先序(最低成本)
1. (10 分钟,.gitignore 两行) '!data/d1_evidence/**/*.log' + '!build/board_zc706_seed2/**' —— 立即解封证据归档。
2. (30 分钟,纯文本) prereg 头部钉 bit SHA256×2/commit/region;追加结果回填表(P1-P4: 实测 HD/verdict/日志行号/操作者/日期)。
3. (1 小时,纯文本) ci_regression.ps1 加两段锁: board-tcl 不变量锁(照 162-182 行范式) + 两 build tcl 的 add_files 清单一致使 + MANIFEST 源哈希重算比对。
4. (1-2 小时,需一次重建) 两个 build tcl 末尾写 MANIFEST(git HEAD+全源 SHA256+WNS+region);seed2 tcl 钉死 pick=X1Y0+断言;设 BITSTREAM.CONFIG.USERID。
5. (下次烧板前) program_zc706.tcl 解析文件名变体打横幅、烧前重算 bit SHA256、烧后回读 USERID 核对。
