# PUF 无人机认证 · 前端模块（交接说明）

> 读者：接手/合并本模块的组员。本文件回答四件事 —— **怎么放进来、怎么跑、和报告对不上的地方在哪、出问题先看哪**。
> 本模块的设计依据是《前端探索报告.md》v1.1（与本目录内那份逐字节一致），下文所有 §x 均指它。

本模块的交付承诺是：**把 `web/` 整个文件夹拷进 `puf-drone-auth` 仓库根目录，不改动你仓库里任何现有文件**。
唯一一个与你的仓库同名的文件是 `web/前端探索报告.md`，它与 `puf-drone-auth/web/前端探索报告.md` 的
SHA256 相同（`020c1e8c94bb31eb3aecbcb2144c0bc686cab3a1d4155de2a0c5d531eb9541b1`），直接跳过即可。

---

## 1. 怎么放进来

```powershell
# 1) 先 dry-run 看清单（不写任何文件）
pwsh -File web\tools\merge-into-repo.ps1 -RepoRoot C:\Users\<teammate>\Desktop\puf-drone-auth

# 2) 确认无误后实拷
pwsh -File web\tools\merge-into-repo.ps1 -RepoRoot C:\Users\<teammate>\Desktop\puf-drone-auth -Apply
```

脚本对每一对同名文件**逐字节比 SHA256**，只做三种判定：

| 判定 | 动作 |
| --- | --- |
| 只存在于本模块 | 新增 |
| 两边字节一致 | 跳过，报告「未改动」 |
| 两边内容不同 | **拒绝整个合并**（exit 1），列冲突，磁盘一个字节不写 |

**不提供强制覆盖开关**。要覆盖你的文件，得先自己删掉它 —— 那是一个有意识的动作，不该由脚本代劳。
合并完成后脚本会再逐文件复核一次 SHA256，并打印「既有文件改动数」。

> 当前实测（2026-10-14，对 `puf-drone-auth` 原目录）：新增 63、一致 1（即上面那份报告）、冲突 0。
> 实拷演练（对组员仓库的**全量副本**）：63 个新增文件哈希全部一致；副本内 2018 个既有文件
> 前后全量 SHA256 对账，改动 0、消失 0 —— 对账独立于脚本自检另行重算，不采信它的复述。

也可以不用脚本，手工 `Copy-Item -Recurse web\ <仓库>\web\` —— 但那样就没有冲突拒止这道闸了。

---

## 2. 怎么跑

### 合并后（组建/答辩用）

```bash
python web/bridge/web_bridge.py --loopback --open
```

不带任何路径参数即可：`--repo-root` 缺省 = 本文件上两级（即 `web/bridge/` 的 `parents[2]` = 仓库根），
`--web-dist` 缺省 = `web/dist`。默认只绑 `127.0.0.1:8642`，端口被占会自动顺延（最多 6 个），
顺延前若探测到那里已经跑着一个桥接，直接复用它并打开页面而不是再起一个。

打开后：`http://127.0.0.1:8642/console.html`（演示控制台）、`/viz.html`（数据可视化）、`/`（首页壳）。

### 开发态（改前端源码时）

```bash
python web/bridge/web_bridge.py --loopback                 # 终端 A：桥接，退出码/日志都在这里
npm --prefix web run dev                                    # 终端 B：Vite dev server，/api 代理到 8642
```

Vite 的 `server.proxy` 只把 `/api` 转给 `127.0.0.1:8642`，并在转发时剥掉 CORS 那层；
**dev server 只用于开发，交付链不依赖它**（产物是 `web/dist/` 纯静态）。

### 自检（不起 HTTP，跑完即退，退出码表达成败）

```bash
python web/bridge/web_bridge.py --loopback --once s1     # s1|s2|s3|s4|s5|s6|s7|golden
python web/bridge/web_bridge.py --loopback --reset-demo 99   # S5 小池重演前重置
```

事件流直接以 JSON 行打到 stdout，用于「桥接侧说了什么」与「页面显示了什么」的交叉核对。

### 构建

```bash
npm --prefix web install
npm --prefix web run typecheck      # tsc --noEmit，本模块唯一的静态门禁
npm --prefix web run build          # typecheck + vite build → web/dist/
```

`web/dist/` **入库**（离线交付），改源码后请重建并单独提交，提交信息注明构建机。
入库的产物是**可复现**的：本机重建后 `git status` 为空，即 `dist/` 每个字节与仓库里那份相同
（文件名带内容哈希，重建若产生不同字节会立刻以未跟踪文件的形式暴露）。

**交付/提交前须删掉 `web/dist/_probe_*.html`。** 它们是开发期的自检探针页，由 `.dev-data/mkp_r5.py`
生成到 `dist/` 才好在桥接的静态服务下跑；留着不影响功能，但会把两个只服务于开发流程的文件
带进你的仓库 —— 而 `.gitignore` 只挡 git，挡不住整目录拷贝。`dist/` 里应只有
`index.html`、`console.html`、`viz.html` 与 `assets/`。

---

## 3. 目录结构

```
web/
├── README.md                     ← 本文件
├── 前端探索报告.md                ← 设计依据(v1.1,与你仓库内那份逐字节一致)
├── package.json / tsconfig.json / vite.config.ts / .gitignore / .gitattributes
├── index.html / console.html / viz.html      ← Vite 三入口
├── bridge/
│   └── web_bridge.py             ← 桥接层(全标准库,零 pip 依赖)
├── tools/
│   ├── sample_hd.py              ← V1 的 HD 双系列采样脚本(§11 D9 交付物)
│   └── merge-into-repo.ps1       ← 合并助手(开发工作区工具,**不随模块进仓库**)
├── src/
│   ├── main-index.ts / main-console.ts / main-viz.ts
│   ├── core/       api bus store types format mock scenario
│   ├── styles/     tokens base console viz
│   ├── components/ topbar left-panel right-panel terminal-card frame-timeline
│   │               hex-viewer hd-gauge audit-log
│   ├── chart-svg/  axis legend tooltip export figure metrics placeholder
│   │               v1-hist v2-roc v3-matrix v4-jitter
│   └── stages/     stage2d stage3d + three/{scene,fx,particles,palette}
└── dist/                         ← 构建产物(入库,离线交付)
```

`src/core/types.ts` 是 §8.2/§8.3 的逐字段 TS 镜像 —— **它就是合约**。端点或事件字段若与上游漂移，
`tsc --noEmit` 会先炸，页面不会带着半个字段静默跑下去。

---

## 4. 对外契约

### 4.1 REST（§8.2 全量落地）

| 方法 路径 | 请求 | 响应 |
| --- | --- | --- |
| GET `/api/status` | — | `link{mode,uptime_s,proxy}`、`sessions[]`、`templates[]`、`pools[]`、`hsm` |
| GET `/api/golden-frames` | — | 7 条黄金帧（名称＋hex＋注记），读 `docs/protocol_contract.md §4` |
| POST `/api/auth` | `{terminal_id, mode: normal∣spoof∣replay∣gray∣evilbase}` | `{run_id}` |
| POST `/api/enroll` | `{terminal_id, n}` | `{run_id}` |
| POST `/api/c2reset` | `{terminal_id}` | `{ok}` |
| POST `/api/setkey` | `{terminal_id, key_hex}` | `{ok}` |
| GET `/api/viz/hd` | `?fresh=1` | `{intra[], inter[], note, source}` |
| GET `/api/viz/templates` | — | `{terminals{tid{responses,stability_mask}}, source}` |
| GET `/api/viz/measurements` | `?terminal_id=` | `{…, source}` |
| GET `/api/events` | — | SSE 流 |
| GET 其余路径 | — | `web/dist` 静态文件 |

### 4.2 SSE（§8.3 的 12 型，**零增量**）

信封 `{"seq", "ts", "type", "payload"}`，具名事件（`event: <type>`，不是 `onmessage`）：

`link.status` `session.update` `frame.tx` `frame.rx` `gray.extra` `verdict`
`confirm.done` `enroll.done` `pool.warning` `replay.reject` `server.log` `run.error`

启动期注册演示终端的进度走 `server.log`，**没有新增事件类型**。每 15s 一条 `: ping` 心跳。

> 踩过的坑记一笔：桥接发的是 `event: <type>`，前端若用 `EventSource.onmessage` 订阅，**永远不会触发**。
> 必须按类型 `addEventListener`。这条已修（提交 `539d451`），但如果你自己写客户端会遇到同样的事。

### 4.3 语义要点（容易读错的两处）

- **阈值是缩放口径**：`verdict.payload.thresholds` 的 `scaled_pass/scaled_reject` 由桥接按本轮
  `n_responses` 以 `decide_scaled` 口径算出后下发，前端**不硬编码** 6/16。
  `hd` 是 `min(Σ hd, 0xFE)`，比较对象是 `n × τ`，不是 τ —— 量程跟 `n` 走，否则 PASS 会画到绿区外。
- **判定是三态不是二态**：`hd <= τ_pass` → PASS(0)，`hd >= τ_reject` → REJECT(1)，中间是 GRAY。
  GRAY 不是一个可用的工作点，页面把它当作需要加测的信号（S4 分支）。

---

## 5. 偏差声明

以下是本模块与报告 v1.1 原文**不一致**的全部条目。**D10 是唯一的对外契约增量**，其余均为实施取舍（D11 为环境项；D13 起为 2026-10-15 用户授权的 UI 升级计划之登记项，方向「系统化精修」—— 结构性需求五区/七图/契约/断点等全部不动，仅视觉层演进）。后续条目若推翻前条的某句结论，**不回改前条**，而是在前条尾部标注「见 Dxx」保留审计轨迹。

| # | 报告原文 | 实际 | 理由 |
| --- | --- | --- | --- |
| **D1** | §8.1：新增单文件 `src/python/server/web_bridge.py`，启动 `python -m src.python.server.web_bridge` | 落位 `web/bridge/web_bridge.py`，启动 `python web/bridge/web_bridge.py`（§8.1 明文允许的唯一变体） | 若放进 `src/python/server/`，模块就不再是「整个文件夹拷进去」，而是往你的包里塞第 10 个文件。桥接用 `sys.path` 引导复用你的 server 包公共 API（与 `main.py` 脚本模式同一先例），**你的 9 个文件零改动**。缺省路径口径已对准合并后的布局，故命令行不带参 |
| **D2** | §4.4：三态 `REAL-STATIC / REAL-LIVE / MOCK` | 增加第四值 `IMPORTED`（导入文件） | 导入的 JSON 是真实测量，但既不是本次运行实测（LIVE 不成立），也不是仓库静态文档（STATIC 不成立）。三态里挑一个贴都是在说谎，而 §4.4 立这条规矩正是为了禁绝含糊 |
| **D3** | §10 树只列 `styles/tokens.css`、`styles/base.css` | 另加 `styles/console.css`、`styles/viz.css` | §6 五区布局与 §7 七张图的版式量远超 base 该承担的职责；拆开是为了改 console 不会碰到 viz |
| **D4** | §10 树列 core 6 / components 5 / chart-svg 4 | 另加 `core/scenario.ts`、`components/{topbar,left-panel,right-panel}.ts`、`chart-svg/{figure,metrics,placeholder,v1-hist,v2-roc,v3-matrix,v4-jitter}.ts`、`stages/{stage2d,stage3d}.ts`、`stages/three/{scene,fx,particles,palette}.ts` | §10 是初稿清单；按 §6/§7 的实际职责拆分，**未新增职责**。`chart-svg/*.ts` 也**不是** §10 里那批「微图表基元」的替代 —— axis/legend/tooltip/export 四个基元照旧存在，多出来的是每张图各自的绘制函数 |
| **D5** | §10 树无 `tools/` | 新增 `tools/sample_hd.py`（§11 D9 的交付物）；`tools/merge-into-repo.ps1` **不随模块进仓库** | 采样脚本是 V1 数据管道的产源（§12 风险表点名要新建），需要有归属；合并助手只服务于「从开发工作区搬进来」这一步，搬完就没用了 |
| **D6** | §8.5 `TAKEN_TIMEOUT_MS` = 600 | 1500 | 桥接首次启动要幂等注册三台代演终端，boot 期握手会超过 600ms，600 会让舞台误判 `stage.taken` 超时并放弃挂载 |
| **D7** | §10 未列类型包 | devDependency `@types/three` | 本模块不引 ESLint / 测试框架，`tsc --noEmit`（§10）是唯一静态门禁；没有 three 的类型，3D 那部分就等于没有门禁 |
| **D8** | vite 默认 `chunkSizeWarningLimit` 500 | 700 | three 独立 chunk 实测 546.76 kB（gzip 136.46 kB，§12 已预期「three 包体较大」），500 会让**每次**构建都刷一条必然出现的告警，把真告警淹掉 |
| **D9** | §8.2 `/api/viz/hd` 备注「现场计算…**或**消费采样脚本落盘产物」 | 缺省消费落盘样本；`?fresh=1` 才现场重算 | 报告给了两条路而没定缺省。选「缺省读样本」是为了让 V1 在断网机器上可复现、且首屏不等采样；现场重算留给页面的「刷新」按钮。**落盘样本两端校时效**：模板签名变了（跑过 S6 注册）或器件密钥变了（状态文件被删重建）都会自动退回现场采样，并在桥接日志点名是哪一端变了 —— 否则页面会继续展示一对已经不成立的谱，且一声不响 |
| **D10** | §8.2 三个 viz 端点的响应字段 | `/api/viz/hd` 增 `note`；`/api/viz/hd`、`/api/viz/templates`、`/api/viz/measurements` 各增 `source`（`SAMPLE`∣`LIVE`∣`MOCK`） | **唯一的对外契约增量，需你确认**。§4.4 与 §9 要求「任何新数字入页必须先登记来源」，而「这数是谁、什么时候算的」只有服务端知道 —— 页面自己推断不出来。纯增量，既有字段一个没动 |
| **D11** | — | 在本工作区机器上构建需要临时指走 TEMP | 环境问题非代码问题，见 FAQ 第 2 条。不影响你在自己机器上的构建 |
| **D12** | §6 动效约束：「帧推进默认 600ms／帧（滑杆 200–2000ms）」 | 滑杆不驱动帧推进：200–2000ms 线性映射到 3D 光束飞行时长并钳在 0.22–0.55s；帧呈现节奏由剧本层固定（帧事件到达即画） | §6 顶栏组件表对同一滑杆写的职责是「实时调动画节奏（**不影响后端**）」，与动效约束行互有张力。按后者字面实现的话，loopback 下 0ms 完成的轮次要演 2.4s，与时序 note 的「0ms」自相矛盾；故取组件表口径，「生效」落在顶栏读数随动＋光束速度变化＋服务端轮次耗时不随之（已实测） |
| **D13** | 附录 B 设计 tokens（:root 具体值）＋「禁止另造」约束 | **改值三处**：表面阶梯加深一档（`--bg` #0a0e1a→#070b14 等 4 值）、边框实色改蓝白发丝线（`--border` rgba(148,178,255,.10)/.22，随所在表面自适应）、`--dim` #4a5a78→#5e7290。**纯增量**：间距标尺（4px 基准）、字号阶梯（六档收敛 9.5–14px 散值）、键盘焦点环、抬升面板顶部微光、`--blue-bg`、`color-scheme:dark` | 暗色界面分层靠表面提亮与发丝线而非实色描边（Linear／Datadog 暗色实践）。`--dim` 提亮有硬依据：色板验证脚本实测原值对四级表面对比度仅 2.3–2.8:1，低于 3:1 下限，而它承担审计日志时间戳等信息性文字；新值最差表面 3.28:1（**其中「`--dim` 承担信息性文字」这一取向已被 D14 推翻：dim 的适用范围收紧为纯补充/占位，凡需读出内容的小字改走 `--muted`；本条其余结论仍然有效。另注：色板验证脚本里的 `--dim` 常量当时未随本条同步，D14 已修正**）。色相与语义色（green/red/amber/cyan/域配色）**一字未动**，全部实际共显组（V1 绿红、2D 帧时序青紫、状态三元）CVD ΔE≥11.3 且对表面 ≥4.7:1，验证通过。新增 token 覆盖的是附录 B 未涉及的维度（间距/字号/焦点），不否定任何既有语义 |
| **D14** | §7 图表实现细节（未在报告中规定形制）；§4.1/§4.2 语义色**未改** | **V1**：图例移出绘图区到框外上沿；新增两条**均值直接标注**（`同设备 μ=…`／`跨设备 μ=…`，各随本系列取色）取代原先塞在图例注记里的 μ；框内标注分两行（均值行 / τ 行）；柱体改「顶部圆角」路径（`rx` 是四角圆角，会让柱底离开基线）+ 两系列间 2px 缝 + 实心 .92；悬停整列反白。**V2**：ROC 由折线改**阶梯**路径（灰区段同步阶梯）；65 个 τ 全部可悬停读 FAR/TPR/FRR。**V3**：0 位由 `--bg4`（最亮表面）改 `--bg2`+发丝边（原先「亮=0、青=1」与全页「亮=有数据」相反）；不稳定位加斜纹 pattern。**共性**：新增统一悬停高亮层（`.pl-hl`，由 `tooltip.ts` 单点实现，导出前物理删除）；数字类文字统一 `tabular-nums`；**`--dim` 适用范围收紧**为「非信息性」（占位图注／参照基线／镜像冗余标签），凡需读出内容的小字一律走 `--muted` | 均属图表形制与信息层次，不涉及任何数据口径、溯源角标、MOCK 标注、五区/七图结构或对外契约。**V1 的两条均值线是判据本身**（分离度），原先只以小字挤在图例注记里、且色相是红绿色盲最先丢的线索，故改为直接标注并带上系列名 —— 这样即使完全分不出绿红也读得出「哪条是 genuine」。故 V1 **不做**斜纹冗余：bin 宽仅 ~10.6px、每系列柱宽 ~4px，6px 周期的斜纹在这个宽度上只会变成噪点，直接标注是更有效的非颜色线索（V3 掩码格 8×18px 才够宽，斜纹落在那儿）。**V3 斜纹线宽/不透明度是量出来的**：初版 .55/1.8 抠出来光栅化后最暗像素仍在 90 以上（琥珀底 166），等于没纹，改 .72/2.2 后最暗 54.9、约 11% 像素 <80。**V2 改阶梯**：HD 是整数、FAR/TPR 是阶跃函数，折线会画出「τ=8.4 时 FAR=0.13」这种协议里不存在的中间态。**`--dim` 收紧**修正 D13 的取向（见 D13 行说明）：层次不能靠读不清的字去买，3:1 只够图形对象；实测新指派下信息性小字 ≥4.67:1（`--muted` 对最亮表面），且改后**修掉了色板验证脚本里 `--dim` 常量未随 D13 同步的脱节**（脚本一直拿已作废的 #4a5a78 判定，导致「记录与工具各说一套」），并新增「实际 ink 指派表」把代码里的用法钉进验证脚本。V1/V2 的均值线与双系列沿用既有绿/红，CVD ΔE 13.3（脚本实测，未改色）。**注：`--dim` 的最终处置见 D15**（本轮把它整个退役为图形色，不再有任何文字用它） |
| **D15** | §6 动效约束「仅 transform／opacity」、§4.3「prefers-reduced-motion 全关」；报告未规定无障碍条款 | **动效**：新增 `barScale()`（`core/format.ts`），三处水位条由 `transition:width` 改为 `transform:scaleX()`＋`transform-origin:left center`（顶栏 ×3／右栏 ×2／终端卡 ×1 共 6 个写入点）；`.btn` 过渡收窄为 `opacity,transform`、`.term-card` 收窄为 `transform`、`.viz-fig` 的 `border-color/box-shadow` 过渡整条删除。**键盘**：终端卡（`<div class="card term-card">`）加 `tabindex=0` ＋ Enter/Space 选中 ＋ `aria-current` ＋ 自述 `aria-label`（**刻意不用** `role="button"`——卡内已有四个真按钮，按钮套按钮是无效结构）；顶栏链路/数据源徽章、抽屉开关、指标卡溯源开关、审计日志「跟随」、数据源三态、场景按钮、帧选择 chip 依次补 `aria-expanded`／`aria-pressed`／`aria-valuetext`；浮层补 Esc 关闭＋焦点归还＋`focusin` 自动收起；帧速滑杆与 τ 滑杆补 `aria-label`。**`--dim` 退役为纯图形色**：console 13 处 ＋ viz 3 处 `color/fill:var(--dim)` 全部提到 `--muted`，此后 `--dim` 只剩描边与状态条底色 | 三条都是**实测驱动**，不是审美判断。① 动效：写成 `transition:width` 的进度条每帧触发布局，而 §4.3 的 60fps 目标正是为录屏立的；改 `scaleX` 后走合成器。`.btn` 过渡里的 `border-color/color` 与 `.viz-fig` 的 `box-shadow` 都不在许可属性内——去掉过渡只是让变色**立刻**发生，状态反馈一点没少。② 键盘：改动前全库 `aria-*`／`role`／`tabindex` **零命中**，29 处 click 处理器里终端卡是唯一的「能点却 Tab 不到」，而右栏（判定／HD／R2／池／会话）整片跟着「当前选中终端」走——等于键盘用户进不了右栏。真按钮都在，缺的只是这一个入口和「开着还是关着」这句自述。③ `--dim`：D14 把它的适用范围收成「纯补充」，R5 拿这条规矩去量**真实文字节点**（console 155 个／viz 243 个），剩下的 dim 文字没有一处真是纯补充：审计时间戳、帧方向、仪表量程上限、R2 口径、HUD 快捷键提示。在 11px 暗底上「补充」与「读不清」是同一件事。故立一条**可机检**的规矩「**--dim 只画线**」，由 `palette_check.mjs` 的 `dimTextGate()` 把关（出现 `color/fill:var(--dim)` 即 FAIL 并报出 `文件:行号`），取代逐条人肉登记——人肉表会腐烂，门禁不会；门禁本身用「注入一行 → exit 1 并指认行号 → 还原 → exit 0」做过红绿对照。**实测**：对比度 console 155/155、viz 243/243 全过 4.5:1（`--muted` 对四级表面 4.67–5.72:1）；`--force-prefers-reduced-motion` 下全页仍带动画的元素 3→0、仍留非零过渡的元素 65→0（console 351 节点）、0（viz 5863 节点）；可聚焦元素 51／27 个全部有可达名称，`cursor:pointer` 却够不着的元素 0 个。**已知登记项**：色板验证脚本「八色全谱」一栏有 4 条 CVD FAIL（green↔cyan ΔE 3.7、blue↔purple 5.7），系组员四看板域配色原样沿用、七个色相从不同框；已在脚本内标 `registered` 不计入 exit code（否则脚本永远返回 1、没人再看），数字照印——谁要把 cyan 与 green 放进同一组标记，它会当场喊出来 |
| **D16** | 报告未规定页面图标；§4.3「禁 CDN／全离线」与 §8.1「零足迹」间接约束了它 | **图标内联为 `data:` URI**（三个页面各一行 `<link rel="icon" href="data:image/svg+xml,…">`，同心弧图形，青＝主强调／底＝画布色），**不新增任何可请求文件**。同时：`src/main-index.ts` 三处行内 `style="color:var(--dim)"` 提到 `--muted`；`palette_check.mjs` 的 `dimTextGate()` 从「只扫 `src/styles/*.css`」扩到「扫 `cwd` 下全部 `.css/.ts/.html`」（**43 个文件**），正则可命中行内 `style` 属性；`COLOR.dim` 加「**只许画线**」注释；`run_once()` 的判定改按 `run_id` 认领并把断言收紧到具体结果码 | ① 图标：不内联的话浏览器会自动请求 `/favicon.ico`，而桥接的静态服务里根本没有这个文件 —— 实测桥接日志已积 13 条该 404，答辩当场也会在 DevTools 里再刷一条。「加一个 ico 文件」看似更省事，但那是往组员的目录里多塞一个只服务于演示页面的二进制；内联 40 个字符就消掉这条必然请求，也不违反离线约束。实测：`index.html` 加载 200 且窗口内 favicon 请求数 **0**（改前同一窗口为 2）。② 行内 `dim` 文字：`dimTextGate()` 原先只扫 `src/styles/`，于是 `main-index.ts` 里三处行内样式它看不见 —— **门禁当时印的是 PASS，而违规就在那里**，这比没有门禁更糟（它会让人放心）。扩到全文件类型后当场报出 3 处并修掉；红绿对照重做：「注入一行 → exit 1 且指认行号 → 还原 → exit 0」。③ `COLOR.dim`：R5 删它时只 grep 了定义行、漏了 `v4-jitter.ts:138` 的用法，构建当场 `TS2339` 失败。该用法是 V4 的「报告注释口径」参照线**图例项**（`kind:'line'`，color 落在 `stroke` 上），属 D15 允许的图形用法，故恢复该键并就地注明「只许画线」。**教训留在代码里**：R5 那条「留着一个叫 dim 的色键，下一个人迟早会拿它写字」的推理方向对、但下手狠了 —— 退役一个 token 的正确姿势是「把允许的用法写进名字和注释」，不是「把键删掉」，否则漏网的调用点会在构建期才炸。④ `--once`：它取 `seen` 里**第一个** verdict 当本场景的结果，而引导期 tid 7 的预热认证是异步的、其 verdict 会在 `seen.clear()` 之后才落表 —— `--once s3` 于是把上一轮的 `PASS` 印成 replay 的结果名，**而 §13 恰恰要求 S3 读作 `result=4`**。自检工具一旦开始张冠李戴，整套 §13 走查就失去意义。改成按 `run_id` 认领，并把「有 verdict 就算过」收紧成「结果码等于该场景的规定值（S1→0／S2→1／S3→4／S4→0／S7→0）」，否则把 mode 接错线也能一路 OK。红绿对照：故意把 S1 的期望写成 1 → 打印 `-> FAIL` 且 **exit 1**；还原 → exit 0 |
| **D17** | 报告 §6 未规定场景的快捷触发与帮助浮层；相机预设（1–4）与截图（F）原只在 HUD 一行小字里；右栏判定区在无 run 时的形态报告未规定 | **console 交互可见性**：① 顶栏新增「?」按钮＋快捷键浮层 `.help-ov`（`role=dialog`＋`aria-modal`＋Esc／点背景关闭），逐条列出 Shift+1–7 场景／1–4 相机／F 截图／H 顶栏／R 抽屉／? 本浮层；② **Shift+1–7 直接触发场景**——keydown 先判 `shiftKey` 再落相机数字分支（`e.key` 带不带 Shift 都是 `'1'`，判序反了相机就把场景吞了），纯数字保持相机预设语义不变；③ 3D 接管后场景标题条出现**相机按钮组** `#st-cams`（全景/跟踪/特写/俯瞰＋⤓ 截图），相机预设自此有鼠标通道，2D 保底时按钮组不出现；④ 拖拽暗示条 `#stage-hint`（「按住拖拽旋转 · 滚轮缩放」，首次 pointerdown 后淡出）＋ 3D canvas `grab/grabbing` 光标；⑤ 右栏**空态引导** `#rp-idle`（虚线框：左栏 S1–S7 · Shift 快捷 · ? 帮助；`runCount===0` 且无 run 时可见，跑过一次即永久消失——它只对「一次都没跑过」的新会话有意义）；⑥ 场景按钮 running 态扫光（`scen-sweep`，translateX）；⑦ index 入口卡 `hoverlift` 悬停上浮 | 起因是用户实测反馈「交互感太差」。R7 前的走查（截图＋视觉模型＋源码对读）结论：**能力大都在，但没有一条可见**——相机预设只有 HUD 里一行 9px 小字提到数字键，场景只有左栏按钮，新会话右栏大字判定区整片空白，答辩观众第一眼读不出「这页能点」。新增的全部是「把既有能力亮出来」的通道而非新功能；键盘／按钮原路径一条没动，鼠标通道只是冗余。动效全在 §4.3 白名单内（扫光/上浮 translate、暗示条 opacity），`?` 是真 `<button>` 吃焦点环，浮层 Esc 关闭沿用 D15 的浮层纪律。**探针**（`mkp_r7.py` console 段）：浮层 opened=true 且 Esc 关闭（kbd 9 条、role=dialog）；纯数字按下 `plainDigitFiredScenario=false`，Shift+1 后 S1 进 running（+150ms 采样）且首跑后 idle 消失；相机按钮组可见性与 hud 文本一致（无头下 3D 能否接管取决于 WebGL，断言只认「两分支自洽」） |
| **D18** | §7.2 阈值联动报告指定**滑杆**为通道；图内直拖报告未规定 | **viz 图内拖 τ**：① V1 绘图区按住水平拖＝直接改 τ（指针 x → 最近 bin 边界）；② V2 曲线附近按住拖＝沿 FAR 轴**吸附最近阶梯点**改 τ（指针不必压在曲线上——ROC 的横轴就是 FAR，横扫总落一个 τ；并列取较小 τ）；③ τ 拖进灰区 7–15 时 V1 的 τ 线与标签变琥珀 `vl-tau-gray` 并注「(灰区)」——此前灰区只在 V2 工作点与滑杆读数可见，**V1 自己那根线拖进灰区仍是青色，等于本图在附和「这也是个合法门限」**；④ `.fig-body svg` 加 `touch-action:pan-y`：触摸上横向拖 τ 不被页面滚动吃掉、纵向滚动保留；⑤ vt-note 补「图内直拖」说明 | 技术纪律（这是本条真正的难点）：**move 阶段只平移两个活节点**（τ 线＋标签／工作点 dot＋标签）并回调 `onTauPick(t,'move')`，调用方只更新滑杆读数**不重渲染**；松手 `end` 才派发滑杆同一条 `input` 提交路径全量重绘。原因：`renderAll` 会销毁重建整棵 svg，pointer capture 随之失效，拖拽当场断线——每帧重绘在拖拽类交互里不可行。`setPointerCapture` 对合成指针（自动化／部分辅助技术）抛 NotFoundError，try/catch 后降级为 svg 冒泡监听，丢 capture 只降级不报错。滑杆在图卡头部、与图形分离，「指哪改哪」是阈值类图表的业界常规（Grafana／Datadog 阈值线皆直拖）；但拖拽是**冗余通道不承担可达性**，键盘／滑杆路径原样保留。**探针**（`mkp_r7.py` viz 段，合成 pointer 序列）：V1 拖 6→16 且 τ 线 `x1` 与新值对应（不是只改了滑杆读数）；灰区拖 τ=9 且线带 `vl-tau-gray`；V2 左拖 τ 变小；探针末恢复 τ=6。探针自身踩过两个坑已修：`end` 后 svg 被替换，**引用必须每次拖前现查**（攥旧脱树节点派发，`getBoundingClientRect()` 全零、映射全错）；灰区目标坐标按实测几何（x0≈56、binW≈10.38）校准到 fx=0.21 |
| **D19** | 报告 §6 规定右栏「大字判定 48–72px + result 0–4 中文释义配色」、日志「严重级配色」；**未规定**判定卡卡体的状态呈现、终端卡/场景键/相机键形制、时序节点等宽与舞台取景框 | **console 视觉精修（R8，全在 D13「系统化精修」授权范围内，语义色 token 一字未动）**。① **判定卡状态场**：卡体随结果挂 `st-pass/st-reject/st-drain`（error 并入 reject、replay 并入 drain）——顶部发光式分层渐变（高→低 alpha 双停）＋.55 档描边＋同色系外辉光（静态阴影）；大字辉光同步收敛一半（26px/.5→16px/.35——卡体已带状态底色，文字不必再喊）；阈值词「绿＜/红≥」上语义色（`.th-ok/.th-no`；值取自 /api/status 的数字字段，拼 innerHTML 无注入面）。② **状态外显到边缘**：终端卡最近判定左轨（`.tc-ok/.tc-warn/.tc-fail`，与 decChip 同一映射 0=绿／3、4=琥珀／其余=红；绝对定位 `::after` 不占布局）；审计日志 severity 左缘条（所有行 2px 透明占位，warn/error 行只换色、行间零位移）。③ **数字层级**：顶栏池读数 11→12px 实重、右栏池读数 14px 实重、会话计数值 12px 半粗，均 `tabular-nums` 且穿 text 色（数字不穿系列色）。④ **布局补漏**：S7 假基站键独占整行（七键两列必落单，死区变特殊场景强调位）；时序五节点等宽（`flex:1 1 0`＋104–168px）＋箭头定宽；R2 hex 降半档字号收窄字距求单行（`break-all` 留作窄屏兜底）；判定卡与仪表卡主从间距修正（原 5px，且旧注释与值不符，一并修正为 12px）。⑤ **键形制与取景框**：场景键圆角走 `--radius-sm`、悬停青描边＋青底＋1px 上浮（过渡仍只 opacity/transform）；相机键当前预设常亮（`.st-cam.active`，按钮与键盘 1–4 两通道经 STAGE_CAMERA 总线同源刷新，不会「按钮亮 A 实际是 B」）；舞台四角 L 形发丝角标（22px/1.5px/alpha .5，蓝白系 recessive HUD，`pointer-events:none` 不挡拖拽/滚轮） | 起因是用户反馈「console.html 的 ui 还是不够好看」并指定**截图→视觉模型迭代环**。无头 Edge 晚态截图三件套：动态 `<script src="/api/events?probehold=1">` 挂起 load（SSE 永不结束）＋1Hz 心跳防网络静默退出＋`--timeout=20000` 截止（`--dump-dom` 在 load 即触发、`--virtual-time-budget` 会被 SSE 卡死，皆不可用）；探针以 404 信标（POST `/_probe_rpt?…` → 桥接访问日志）留行为痕迹。裁片按 右栏/左栏/日志/舞台 四区送视觉模型评审，**逐条对源码/像素核伪再动手**：约 20 条意见驳回 7 条并留证——「CRP 83/84% 该琥珀」语义反了（warn 阈值是 remaining_pct＜20，余量高是健康，改了就是伪造语义）、「通过徽章该绿底」早已实现、「场景/舞台缺分隔线」border-top 都在、「n_pairs=4 该琥珀」无契约依据、「hex 前几段同色」是 §6.2 三段式合同本身、「节点被截断」是裁片伪影、「角标再加料」模型自认角标不在其视野内——**防的是两件事：把语义改反、为不存在的问题空转**。采纳项重建后探针复跑自证（信标 `big=通过`×12 落桥接日志）＋**像素仲裁**：判定区 PASS 绿像素 737→834（状态场确实落进了画面，非自说自话）；复验评审结论「成立、克制得当、阈值上色变好、节点等宽生效」。设计取向一句话：**状态色留给信号**——判定卡是「全页最重要的一瞬间」要压得住，日志与终端卡的状态画在边缘、正常态不上色。全部为静态阴影与颜色变化，**零新增动效**（`--force-prefers-reduced-motion` 计数不变） |

| **D20** | 报告 §8.1「全公共 API」措辞 | 桥接两处触碰 server 私有结构:`transport.inner._terminals[tid]` 注入重建器件、`term._auth_count` 恢复(Phase A A1) | LoopbackTransport 构造无参、terminal() 懒创建,公共注入路径不存在;auth_count 不恢复则 C2 回卷撞服务端重放窗。升级 main.py 时须复查这两处(代码内已加注释标记) |
| **D21** | 报告 §8.2 端点表无 /docs 路由 | 桥接新增 `--docs-dir` 参数与 `/docs/` 静态映射(缺省 <repo-root>/docs,存在才映射;`is_relative_to` 路径净化) | index 看板互链在桥接交付形态下的可达性(按钮审计 P1-1);开发工作区不可达时页面给琥珀提示 |
| **D22** | 报告 §4.4 三态词汇(REAL-STATIC/LIVE/MOCK) | Figure 分级增第五值 **MODEL**(琥珀实线 chip);`/api/viz/reliability` source=MODEL;V7 走 REAL-STATIC | ROPairingPUF 推演数据:算法与输入真实但非上板——三态挑一个都在说谎,与 D2 增 IMPORTED 同理 |
| **D23** | 报告 §8.1 `_ensure_device_key` 随机铸钥 | 注册即 **provisionkey 语义**(derived_key→store+hsm 双写);桥接状态升 **v2**(freqs 取代 secret_hex,一次性迁移级联清理) | 对齐 W4-P4 interop 口径(K 由终端 PUF 派生);随机铸钥仅 _do_auth 内保留 no-op 兜底 |
| **D24** | 报告 §7.1 V6/V7=MOCK 占位;§8.2 无 ml/reliability 端点;§11 B3 未定载体 | B1–B4 落地:`/api/viz/ml`(STATIC)、`/api/viz/reliability`(MODEL)、`sample_hd --roc`(roc_summary.json: EER/AUC/FAR/FRR)、`tools/gen_metrics.py`(四表→.out/metrics) | Phase B 执行(计划 v1.1 §4);G5 三图+指标表就绪 |
| **D25** | 报告 §6/§7 交互细节若干 | 按钮审计修复:6×P1/P2 + 7×P3(index chip 双断、3D 迟到竞态、剧本代际令牌、2D 键反馈、幽灵按钮、导出范围错位、焦点归还、轮询去重、mock tid/mode 保真、单步空队列、刷新防重、断线 run 收尾、tid 组显隐、_serve_static 加严) | 逐项证据与复测记录见 web/reviews/按钮接线审计-auto-review.md(修复轮) |

已在报告口径内、故不列为偏差的两条，一并说明以免被当成偏差：

- **`--mock` 模式**：`--mock` 下桥接**完全不 import** 你的 server 包、不写任何数据目录文件，`source` 一律 `MOCK`。
  这条是配合 §4.4 的：页面在 `--mock` 下 URL 仍是 `/api/*`、数据源徽章仍是「运行实测」，
  若分级只信 URL，三张伪造的图会被标成 REAL-LIVE 并配上「loopback 仿真理想性的直接体现」的图注 ——
  把一句编出来的分离度说成实测结论。故分级**以数据自述为优先**（已实测：`srcLabel="运行实测"` 同时 V1–V4 全为 MOCK）。
- **`/api/viz/hd` 落盘样本里的 `templates_sig` / `device_sig` / `sampled_at` / `templates_json` 不回传**：
  它们是样本的**校验输入**而非展示数据。尤其 `templates_json` 是采样那台机器上的绝对路径，
  对浏览器毫无意义，却会出现在答辩截图上。

---

## 6. 自检与验收

§13 的验收清单在这里逐条对应到可执行的命令：

| §13 条目 | 怎么验 |
| --- | --- |
| 打开即连桥接、显示 LOOPBACK 徽章 | 打开 `/console.html`，顶栏链路徽章 |
| S1 五帧全绿 + PASS + 缩放阈值仪表指针在绿区 | `--once s1`，或控制台点「认证」；仪表量程应为 `n×τ` |
| S2 spoof → REJECT + 逐响应 HD 差异高亮 | `--once s2`，注意 `verdict.hd_per_response` |
| S3 replay → result=4 日志高亮 | `--once s3` |
| S4 灰区加测分支展开 | `--once s4` |
| S5 小池粒子枯竭 | `--reset-demo 99` 后 `--once s5` |
| S6 注册后 stable bits 刷新 | `--once s6` |
| S7 假基站 → 终端侧 BLOCKED | `--once s7`，右栏应同时给出服务端与终端侧两个结论 |
| 导出 JSON 与日志一致 | 底栏「导出」键；导出件的事件数／判定数与日志窗口计数（`N / M 行`）对读 |
| 帧速滑杆生效 | 顶栏滑杆 200–2000ms：读数随动、3D 光束速度随之变化、服务端轮次耗时不随之（口径见 D12） |
| 连播剧本 + 逐帧单步可用 | 顶栏「S1→S2／全场景／单步／暂停」；暂停态单步到末幕，序号读作 `n/n` 不溢出 |
| 黄金帧 7 条 | `--once golden` 与 `/api/golden-frames` 对读 |
| V1 双系列来自采样脚本真实数据 | `python web/tools/sample_hd.py --help`；页面 V1 副标题显示「离线样本」 |
| V2 ROC 含 EER 且阈值滑杆联动 | `/viz.html` 拖阈值滑杆，看 V1 分割线 / ROC 工作点 / 混淆矩阵同步 |
| V3 位矩阵 + 掩码条来自 templates+sidecar | `/viz.html` V3 卡片 |
| V5–V7 显式 MOCK | V5/V6/V7 卡片应为灰显 + amber 边框 + 占位原因 tooltip |
| 每图可导出 SVG / PNG | 图卡右上两键。导出件内置 `<desc>` 记录「分级 + 副标题 + 注记」，脱离页面仍可溯源 |
| 指标卡逐数可溯源 | 指标卡角标对应的 §9 矩阵行 |
| 断网可跑、Network 无 CDN 请求 | 断网后重开页面，DevTools Network 应只有 `127.0.0.1` 的请求 |
| 1280×720 布局可用 | 窗口收到 1280×720，右栏应折叠为抽屉 |

**§13 之外的补充门禁**（R5 起，均不在 §13 清单内，故单独列出；都是可重跑的脚本，不是一次性截图）：

| 门禁 | 命令 | 通过标准 |
| --- | --- | --- |
| 色板与文字对比度（含 `--dim 只画线`） | `node .dev-data/palette_check.mjs` | exit 0；文字行全 PASS（`--muted` 对四级表面 4.67–5.72:1）；「八色全谱」的 4 条 CVD FAIL 属登记项，不计入 exit code |
| 动效合规（仅 transform／opacity） | 同上探针的 `motion` 段 | `badTransitions`／`badKeyframeProps` 为空；`prefers-reduced-motion` 规则带 `!important` |
| 动效真实关闭 | `launch.ps1 -ReducedMotion` 跑 R5 探针 | `animated` 与 `transitioning` 均为 0（对照：常态 3 与 65） |
| 键盘与名称 | R5 探针的 `focus` 段 | 可聚焦元素全部有可达名称；`cursor:pointer` 却不可聚焦的元素 0 个 |
| 浮层与状态自述 | R5 探针的 `kb`／`popup`／`follow` 段 | Enter 选中终端后右栏跟随；Esc 关浮层并归还焦点；上滚解除「跟随」时 `aria-pressed` 同步翻转 |
| 场景矩阵端到端（§13 逐场景行的合并跑法） | `for s in s1 s2 s3 s4 s5 s6 s7 golden; do python bridge/web_bridge.py --once $s; done` | 八项**退出码全 0**；`--once` 的结果名按 `run_id` 认领（S3 必须读作 `REPLAY`／result=4，不是 `PASS`）；黄金帧 R2 = `7b45b0545e59aa94`。断言到具体结果码，故把 mode 接错线会 FAIL 而非静默通过 |
| 产物无自动图标请求 | 桥接日志窗口内 `grep -c favicon` | 0（三个页面均内联 `data:` URI 图标）；改前同一窗口为 2 |
| R7 交互走查（帮助浮层／Shift 场景／相机按钮／idle 引导／图内拖 τ） | `python .dev-data/mkp_r7.py` 后无头浏览器开 `dist/_probe_r7_console.html`、`dist/_probe_r7_viz.html`，读桥接日志解码 `/diag?…` | console：浮层开＋Esc 关、纯数字不触发场景而 Shift+1 触发、首跑后 idle 消失、相机按钮可见性与 hud 一致；viz：V1 拖后 τ 变且线 `x1` 对应、灰区拖带 `vl-tau-gray`、V2 左拖 τ 减小、探针退出前恢复 τ=6 |

（R5 探针由 `.dev-data/mkp_r5.py`、R7 探针由 `.dev-data/mkp_r7.py` 生成，需先 `npm run build` 再指向 `dist/`；`.dev-data/` 是开发沙箱、不入库，故这些门禁只在开发工作区可跑。）

---

## 7. FAQ

**1. 页面 404 / 打不开？**
先看是不是端口顺延了 —— 桥接启动时会打印实际端口。若 8642 上已有一个桥接，新版会复用它并直接开页面，
不会起第二个。若 `web/dist/` 不存在（只拿到源码没拿到产物），要么用 `npm run dev` 走 dev server，
要么 `npm run build` 重建。

**2. `npm run build` 报 `remove ...\Temp\esbuild-xxxx: Access is denied`？**
这是本工作区机器上 esbuild 清理系统临时目录被拒（安全软件/权限），不是代码问题。绕开：

```bash
mkdir -p web/.dev-data/tmp
TEMP=$(pwd)/web/.dev-data/tmp TMP=$(pwd)/web/.dev-data/tmp npm --prefix web run build
```

你在自己机器上大概率不会遇到；若遇到，用同样的方式把 TEMP 指到一个**项目内**的目录即可
（别去扫系统临时目录里其他构建的残留）。

**3. 页面数据变了但我没改代码？**
桥接的运行态数据默认落在 `<repo-root>/data/`（开发态可用 `--data-dir` 指到别处）。
S5 重演前记得 `--reset-demo 99`，否则小池还是上回耗剩的。V1 的落盘样本若失效，
桥接会在日志里点名原因（模板表变过 / 器件密钥换过）并自动退回现场采样。

**4. 3D 舞台没出来？**
无 WebGL 时整块**全量降级**为 2D SVG 五帧时序图，功能不减（§8.5 的保底要求）。
无头浏览器注意：当前版无头 Edge/Chrome 默认自带 SwiftShader，WebGL 开箱即用，
**不需要** `--enable-unsafe-swiftshader`（旧版才需要）；反过来，想在无头环境里验证
2D 保底通路，得在页面加载前把 `getContext` 对 webgl 补丁成返回 null。

**5. 需要装什么？**
运行只要 Python 3.10+（桥接全标准库，**零 pip 依赖**）+ 一个浏览器。
`npm` 只在你要改前端源码时才需要 —— 交付链（`dist/` + 桥接）完全不需要 Node。

---

## 8. 已知边界

- **串口真机链路是 EXPERIMENTAL**：桥接的 loopback 代演已完整驱动 §8.3 全时序；
  串口模式复用你的 `SerialServer.serve_forever`（不用一问一答的 `SerialTransport`），但无硬件实测，
  演示一律走 loopback。UI 侧零改动即可切换。
- **不支持 `file://` 直开**：ES 模块在 `file://` 下会被浏览器安全策略拦掉（§3）。必须经桥接的 HTTP 服务打开。
- **V4（注册测量抖动）是缓冲项**：无捕获数据时显示占位并注明，不显示编造的抖动。
- **V5–V7 永远是 MOCK**，直到上板数据到位；替换 conditions 写在卡片 tooltip 里。
- 本模块不引 ESLint / 测试框架（§10 的取舍：周期紧，靠 `tsc --noEmit` + §13 清单兜底）。
