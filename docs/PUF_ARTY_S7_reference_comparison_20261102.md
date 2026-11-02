# 参考工程对照分析：老师给的 PUF_ARTY_S7 vs puf-drone-auth（2026-11-02）

> 对象：D:\文件\ssssssss\FPGA\PUF_ARTY_S7（SEAL, IIT Kharagpur 出品的 Arbiter/XOR-PUF 评估平台，ISE 14.7 时代，ARTY-S7/7 系器件；PicoBlaze6 软核控制器 + MicroBlaze Vitis 平台 + MATLAB 上位机全套）
> 方法：通读核心 RTL（apufClassic/switchChain/sw_dolut/xor_apuf/puf_controller）+ placement 脚本（placementType_*.m + APUF_64_a23.ucf）+ 评测脚本（crpProcessing/{uniformity,intra_uniqueness,reliability,comp_SAC_64}.m + rs232_COM/*）

## 一、参考平台画像

- 熵源：64 级 LUT6_2 开关链赛跑 + NAND 锁存仲裁（经典 APUF）；K=8 并联实例 XOR 输出（program_8/16/23XOR 变体，抗建模）
- 控制：PicoBlaze 软核 + UART 9600；挑战 64bit 经 MATLAB 下发，响应回收后离线分析
- **布局是一等公民**：MATLAB 生成逐级 LOC/BEL 约束（SLICE_X%dY%d + A6LUT..D6LUT），AAAA/ABAB/ABCD/RAND 等多种布局策略做对照实验
- 评测方法论：uniformity（位 1 比例≈50%）、**intra_uniqueness（同板 8 实例两两 mismatch，40%~60% 之外判相关并迭代剪枝剔除）**、reliability（11 次重复测量翻转率）、SAC 严格雪崩（单位翻转→输出翻转≈50%）

## 二、最重要的印证：两个项目在"布局主导熵"上殊途同归

参考平台的三项设计选择，全部指向我们 11-01 的根因结论（指纹=布局的函数）：
1. 每个实例逐级钉死 LOC/BEL 且各实例落位不同（RAND 策略带种子）——**主动制造实例间布局差异**；
2. 唯一性只在**同板实例间**测（8 实例），从不主张"同 bitstream 跨板唯一"——绕开了我们踩的坑；
3. 实例间相关性 >60%/<40% 的对**直接剪枝淘汰**——把"布局相关导致指纹相关"当作已知风险做数据防线。

结论：我们的 seed2（PBlock 差异化布局→跨板唯一性）与老师平台方法论同源，可互相印证引用；且我们比它更进一步——给出了序比较量化器的定量机理（全序反推/共模不变性/近平局对）并做了跨板干预实验。

## 三、逐项对照

| 维度 | 参考 PUF_ARTY_S7 | 我们 puf-drone-auth | 判定 |
|---|---|---|---|
| 熵源 | APUF 开关链赛跑 | RO 阵列两两序比较 | 各有取舍；RO 稳定性好，APUF 挑战空间大 |
| 量化 | 锁存仲裁 1 bit | 1ms 计数窗+序比较 64 bit | 我们的近平局对需 helper-data（已知 P2） |
| 布局控制 | 逐级 LOC/BEL+策略实验（UCF） | PBlock 区域级（XDC，seed2 起） | 可吸收：逐环 LOC 作为 seed3/布局策略章节 |
| 唯一性口径 | 同板实例间 + 相关性剪枝 | 跨板（差异化布局后） | 互补；论文两者都报 |
| 抗建模 | XOR-K（8/16/23 实例） | ml_attack 11/11 + R2 非线性金丝雀 | 等价防线；XOR 化列为 future work（会牺牲可靠性） |
| 可靠性 | 11 次测量翻转率 | enroll 3 次多数票 + 64/64 稳定位 | 应吸收：评测口径升级为标准三件套 |
| SAC 雪崩 | 有标准脚本 | 无 | **应补**：黄金模型上跑，纯软件 |
| 认证协议 | 无（纯评估平台） | 六帧双向认证+Speck+防重放+灰区加测 | 我们显著更强（系统 vs 平台） |
| 控制器 | PicoBlaze 软核（攻击面） | 纯 PL FSM（ARM 未用） | 我们更优，答辩主张保留 |
| 工程质量 | 无 CI/无版本化评测 | CI 18/18+auto-review 门禁+B-LOCK | 我们更优 |

## 四、可落地改进清单（按死线前性价比排序）

### 今天（D2 论文日）可完成
1. **标准三件套指标 Python 化**（抄 uniformity/reliability/uniqueness 公式）：uniformity 已有 48.7%；reliability 从 enroll 3-meas 数据算；uniqueness 等烧板 REJECT 后补跨板数 + （可选）同板 16 环两两口径。
2. **SAC 雪崩测试**：用 src/python/evaluation/puf_model 黄金模型，单位翻转挑战→响应翻转率，预期 ~50%；纯软件几分钟，论文表格加一行硬数据。
3. **enrollment 相关性守卫**（把参考平台剪枝思想搬到服务器）：新终端模板与既有模板两两 mismatch 若落在 [40%,60%] 之外 → 拒绝注册并告警（防"同布局双板"再次静默入库）；~20 行 + 单测，直接进 CI。

### 烧板后可选（D2 晚/D3）
4. **逐环 LOC 布局策略**（placementType 思想 XDC 化）：16 环按 RAND 种子逐环钉 SLICE/BEL——作为 seed3 方案或论文"布局策略实验"小节；与 seed2 的区域级 PBlock 形成方法论纵深。

### 论文 future work（不实现）
5. XOR-K 实例强化（注意可靠性代价）、板内多实例唯一性口径、ASIC 上序比较量化器预期可用性。

### 明确不抄的
- PicoBlaze/MicroBlaze 软核控制（我们纯 PL 无 CPU 攻击面是优势）；9600 波特轮询（我们 115200+帧协议）；UCF/ISE 流程（已 Vivado/XDC）。

## 五、结论

参考平台没有推翻我们任何结论，反而三处设计选择独立佐证了根因；我们的系统层（协议/密码/工程化）显著领先，评测方法论层（标准指标/SAC/相关性防线）值得照抄补齐——三项今天就能做完，不影响烧板主线。
