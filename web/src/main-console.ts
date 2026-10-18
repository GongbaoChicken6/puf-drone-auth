/* ============================================================
 * console.html 入口 —— 报告 §6 全量装配
 *
 * 装配顺序(有依赖,勿调):
 *   1. 面板实例化并挂进 console.html 预置的五区容器;
 *   2. 总线 → store 汇聚(12 类 puf:* 事件全部落到 store);
 *   3. SSE 连接 + /api/status 首屏 + /api/golden-frames 黄金向量;
 *   4. 渲染循环(rAF 合并 + 运行中 120ms 补帧驱动耗时秒表)。
 *
 * 数据流向严格单向:SSE/REST → store → 各面板 update()。
 * 面板不回写 store 的业务状态(仅 ui 偏好),避免环形更新。
 * ============================================================ */
import './styles/tokens.css';
import './styles/base.css';
import './styles/console.css';

import { api, SseClient, type SseState } from './core/api';
import { STAGE_CAMERA, STAGE_SHOT, emit, onPuf } from './core/bus';
import { resultOfFrame } from './core/format';
import { SCENARIOS, ScenarioPlayer, type ScenarioId } from './core/scenario';
import { store } from './core/store';
import type { AuthMode, Envelope } from './core/types';

import { AuditLog } from './components/audit-log';
import { LeftPanel } from './components/left-panel';
import { RightPanel } from './components/right-panel';
import { Topbar } from './components/topbar';
import { Stage2d } from './stages/stage2d';

/* ---------- 1. 面板装配 ---------- */
const stage = new Stage2d();
const right = new RightPanel();

const player = new ScenarioPlayer({
  auth: (tid, mode) => doAuth(tid, mode),
  enroll: (tid) => doEnroll(tid),
});

const topbar = new Topbar({
  onFrameMs: ms => store.patchUi({ frameMs: ms }),
  onPlay: ids => player.play(ids as ScenarioId[]),
  onStep: () => player.step(),
  onPauseToggle: () => {
    const s = player.status().state;
    if (s === 'paused') player.resume();
    else if (s === 'running') player.pause();
    else player.step(SCENARIOS.map(x => x.id));
  },
  onStop: () => player.stop(),
});

const left = new LeftPanel({
  select: id => store.select(id),
  auth: (id, mode) => { void doAuth(id, mode); },
  enroll: id => { void doEnroll(id); },
  c2reset: id => { void doC2Reset(id); },
  setkey: id => { void doSetKey(id); },
  runScenario: id => {
    player.stop();
    player.play([id]);
  },
});

/* 原始信封账本(§6.2 导出＝答辩证据附件,要的是未加工的原始事件流) */
const ENV_CAP = 8000;
const envLedger: Envelope<unknown>[] = [];

const audit = new AuditLog({
  exportRun: runId => exportEvents(runId),
});

/* 组件元素**顶替**占位容器(而非塞进去):console.html 的五个容器就是
 * #app / #console-layout 的网格项,把组件套在容器里会让网格行高与实际
 * 元素脱节 —— 顶栏 transform 隐藏时会留下一条 48px 空洞。
 * 注意 #center-stage 被顶替,其中的 #stage-3d 必须已被 Stage2d 构造函数
 * 取走(见 stages/stage2d.ts),否则 §8.5 的挂载点会随占位容器一起消失。 */
const mount = (sel: string, node: HTMLElement): void => {
  document.querySelector<HTMLElement>(sel)?.replaceWith(node);
};
mount('#topbar', topbar.el);
mount('#left-panel', left.el);
mount('#center-stage', stage.el);
mount('#right-panel', right.el);
mount('#bottom-log', audit.el);

/* R7:顶栏「?」按钮 —— 快捷键浮层的可见入口(挨着既有的 H 小方块)。
 * 不放进 Topbar 组件:浮层属于页面级编排,组件不该反向知道它。 */
{
  const hb = document.createElement('button');
  hb.className = 'tb-help';
  hb.textContent = '?';
  hb.title = '快捷键帮助(?)';
  hb.setAttribute('aria-label', '快捷键帮助');
  hb.addEventListener('click', () => { toggleHelp(true); });
  topbar.el.querySelector('.tb-hint')?.after(hb);
}

/* ---------- 3D 认证舞台(动态分包,尽早起动) ----------
 * 三个要点:
 *  1. 必须在 mount('#center-stage') **之后**发起 —— #stage-3d 随占位容器一起
 *     被 Stage2d 取走并挂进它的舞台视图,元素不在文档里时 getElementById 找不到;
 *  2. 必须在上面这行同步代码之后 —— 动态 import 的回调最早也要等到当前宏任务
 *     结束,那时 DOM 已就绪,3D 模块第一次探测就能命中挂载点;
 *  3. 失败静默:3D 是可选增强,chunk 加载失败/WebGL 不可用都只由它自己
 *     emit stage.error,2D 保底会照常留在屏上。这里 catch 只为吞掉
 *     「chunk 本身取不到」这条到此为止的异常(它是 unhandledrejection,
 *     会被下方兜底处理器记进日志,故这里不再重复记录)。 */
void import('./stages/stage3d').then(m => m.startStage3d()).catch(() => { /* 见上 */ });

/* ---------- 2. 总线 → store ---------- */
/* puf:* 事件是单一真相通道:3D 舞台与 2D 保底各自订阅,store 也在此汇聚。
 * 12 类逐一登记(缺失任何一类都会让对应面板静默不更新)。 */
function wireStore(): void {
  let linkKey = '';
  onPuf('puf:frame', p => store.onFrame(p));      // frame.tx/rx 由 p.dir 区分
  onPuf('puf:gray', p => store.onGrayExtra(p));
  onPuf('puf:verdict', p => store.onVerdict(p));
  onPuf('puf:confirm', p => store.onConfirm(p));
  onPuf('puf:enroll', p => store.onEnroll(p));
  onPuf('puf:pool', p => store.onPool(p));
  onPuf('puf:replay', p => store.onReplay(p));
  onPuf('puf:log', p => store.onServerLog(p));
  onPuf('puf:runerror', p => store.onRunError(p));
  onPuf('puf:session', p => store.onSession(p));
  onPuf('puf:link', p => {
    store.setLink(p);
    /* 桥接每 5s 发一次 link.status 心跳(§8.3)。若逐条入日志,底栏会被
     * 「uptime 又涨了 5 秒」这种零信息行刷满,真正的认证事件被挤走 ——
     * 故只在链路**实质字段**变化时记一行。心跳本身不丢:导出原始事件流
     * (§6.2)走的是 onEnvelope 账本,每一条都在,不受此处影响。 */
    const key = `${p.mode}|${p.connected}|${p.proxy}|${p.version ?? ''}`;
    if (key !== linkKey) {
      linkKey = key;
      store.log({
        tone: 'info', sev: 'info', terminalId: null, runId: null, type: 'link.status',
        text: `链路 ${p.mode} connected=${p.connected}`
          + (p.proxy ? ' · 终端侧代演' : '') + (p.version ? ` · bridge ${p.version}` : ''),
      });
    }
  });
}
wireStore();

/* ---------- 3. REST 动作 ---------- */
function fail(what: string, e: unknown): void {
  const msg = e instanceof Error ? e.message : String(e);
  store.log({
    tone: 'error', sev: 'error', terminalId: null, runId: null,
    type: 'run.error', text: `${what} 失败:${msg}`,
  });
}

async function doAuth(tid: number, mode: AuthMode): Promise<string | null> {
  store.select(tid);          // 舞台按选中终端锁定(§6.4)
  try {
    const r = await api.auth({ terminal_id: tid, mode });
    store.beginRun(r.run_id, tid);
    return r.run_id;
  } catch (e) {
    fail(`POST /api/auth(mode=${mode}, tid=${tid})`, e);
    return null;
  }
}

async function doEnroll(tid: number): Promise<void> {
  store.select(tid);
  store.onAck(tid, 'enroll-start');
  try {
    await api.enroll({ terminal_id: tid });
  } catch (e) {
    store.upsertTerminal(tid, { enrolling: false });
    fail(`POST /api/enroll(tid=${tid})`, e);
  }
}

async function doC2Reset(tid: number): Promise<void> {
  try {
    await api.c2reset(tid);
    store.onAck(tid, 'c2reset');
    store.log({
      tone: 'info', sev: 'info', terminalId: tid, runId: null, type: 'server.log',
      text: 'C2 回放窗已清空 —— 重放演示可重新触发(S3)。',
    });
  } catch (e) { fail(`POST /api/c2reset(tid=${tid})`, e); }
}

async function doSetKey(tid: number): Promise<void> {
  try {
    await api.setkey({ terminal_id: tid });
    store.onAck(tid, 'setkey');
    store.log({
      tone: 'info', sev: 'info', terminalId: tid, runId: null, type: 'server.log',
      text: '已装入 W3 演示密钥(默认)。全新终端首次认证的 R2 应与黄金 R2 一致 —— 见右栏金角标。',
    });
  } catch (e) { fail(`POST /api/setkey(tid=${tid})`, e); }
}

/* ---------- 导出原始事件流(§6.2) ---------- */
function exportEvents(runId: string | null): void {
  const evs = runId == null
    ? envLedger
    : envLedger.filter(e => (e.payload as { run_id?: string } | null)?.run_id === runId);
  const artifact = {
    _what: 'PUF 无人机认证 · 演示控制台原始 SSE 事件流(未加工,逐条原样含 seq/ts/type/payload)',
    _note: '本文件即报告 §6.2 的「导出本次运行 JSON」产物,用作答辩证据附件。',
    _source: store.snapshot.source,
    _bridge_version: store.snapshot.link?.version ?? null,
    _filter_run_id: runId,
    _exported_at: new Date().toISOString(),
    _count: evs.length,
    events: evs,
  };
  const stamp = new Date().toISOString().replace(/[:.]/g, '-');
  const name = `puf-events-${runId ?? 'all'}-${stamp}.json`;
  const url = URL.createObjectURL(
    new Blob([JSON.stringify(artifact, null, 2)], { type: 'application/json' }));
  const a = document.createElement('a');
  a.href = url;
  a.download = name;
  a.click();
  window.setTimeout(() => URL.revokeObjectURL(url), 4000);
  store.log({
    tone: 'info', sev: 'info', terminalId: null, runId, type: 'server.log',
    text: `已导出 ${evs.length} 条原始事件 → ${name}`,
  });
}

/* ---------- 4. SSE + 首屏 ---------- */
let sseState: SseState = 'connecting';

async function resync(): Promise<void> {
  try {
    const st = await api.getStatus();
    store.hydrateFromStatus(st);
  } catch { /* 桥接不可达:保持旧状态,顶栏红徽章 + 退避重连会说明问题 */ }
}

const sse = new SseClient({
  onState: s => { sseState = s; schedule(); },
  // seq 断档与轮询降级都走同一条重同步路径(§6.4:seq 断档不回放,只重取快照)
  onGap: () => void resync(),
  onPoll: () => void resync(),
  onEnvelope: env => {
    envLedger.push(env as Envelope<unknown>);
    if (envLedger.length > ENV_CAP) envLedger.splice(0, envLedger.length - ENV_CAP);
  },
});

void resync();

// 页面卸载时主动关闭,免得退避重连定时器在 teardown 期间再发一轮请求
window.addEventListener('beforeunload', () => sse.close());

/* 黄金向量:从 /api/golden-frames 解析而非硬编码,右栏金角标据此比对。
 * 取向量集合里**名为 GOLDEN 的那条**(RESULT_A1_GOLDEN);取不到时退化为
 * 「最后一条带 R2 的 RESULT」—— 表内另有普通 RESULT(r2=C0..C7),按名字择取
 * 才不会把它当成金标准。 */
void api.getGoldenFrames().then(g => {
  const gold = g.frames.find(f => /GOLDEN/i.test(f.name) && resultOfFrame(f.hex)?.r2 != null)
    ?? [...g.frames].reverse().find(f => resultOfFrame(f.hex)?.r2 != null);
  const gr2 = gold ? resultOfFrame(gold.hex)?.r2 ?? null : null;
  right.setGolden({ r2: gr2, note: gold?.note ?? '' });
  store.log({
    tone: 'info', sev: 'info', terminalId: null, runId: null, type: 'server.log',
    text: `黄金向量已载入 ${g.frames.length} 条 · 金标准 ${gold?.name ?? '—'}`
      + ` R2=${gr2 ?? '—'} —— 右栏金角标据此逐字符比对。`,
  });
}).catch(e => fail('GET /api/golden-frames', e));

/* ---------- 5. 渲染循环 ---------- */
let raf = 0;
function schedule(): void {
  if (raf) return;
  raf = requestAnimationFrame(() => {
    raf = 0;
    const s = store.snapshot;
    const ps = player.status();
    topbar.update(s, sseState, ps);
    topbar.el.classList.toggle('hidden', s.ui.topbarHidden);
    left.update(s, ps.current);
    right.update(s);
    audit.update(s.logs, s.run?.run_id ?? null);
    stage.update(s);
  });
}
store.subscribe(schedule);
player.onChange(schedule);

/* 运行中的耗时秒表要靠补帧驱动(store 只在事件到达时广播) */
window.setInterval(() => {
  const r = store.snapshot.run;
  if (r && r.endedAt == null) schedule();
}, 120);

/* ---------- 6. 快捷键与自适应 ---------- */
/* R7:场景快捷键 Shift+1–7。答辩演示的高频动作是「来,看一下仿冒」——
 * 每次都去左栏找按钮,演示节奏就断了。Shift+数字单手可及,且与纯数字
 * (相机 1–4)不冲突:按没按 Shift,e.key 同是 '1',分流必须显式判 shiftKey。 */
function runScenario(id: ScenarioId): void {
  player.stop();
  player.play([id]);
}

/* R7:快捷键帮助浮层。H/R/1–4/F/Shift+1–7 此前只活在源码里,顶栏那个
 * 20px 的「H」小方块谁也不会去点 —— 交互入口藏起来等于不存在。
 * role=dialog + Esc 关闭 + 点背板关闭;再开再关不重建节点,只切 hidden。 */
const helpOv = document.createElement('div');
helpOv.className = 'help-ov';
helpOv.hidden = true;
helpOv.setAttribute('role', 'dialog');
helpOv.setAttribute('aria-modal', 'true');
helpOv.setAttribute('aria-label', '快捷键帮助');
helpOv.innerHTML = `
  <div class="help-card card" tabindex="-1">
    <div class="help-title">快捷键</div>
    <dl class="help-list">
      <dt><kbd>Shift</kbd><kbd>1</kbd>–<kbd>7</kbd></dt>
        <dd>触发场景 S1–S7(单跑该幕)</dd>
      <dt><kbd>1</kbd>–<kbd>4</kbd></dt><dd>3D 相机:全景 / 跟踪 / 特写 / 俯瞰</dd>
      <dt><kbd>F</kbd></dt><dd>导出当前舞台画面</dd>
      <dt><kbd>H</kbd></dt><dd>隐藏 / 显示顶栏(录屏用)</dd>
      <dt><kbd>R</kbd></dt><dd>右栏抽屉开合(窄屏)</dd>
      <dt><kbd>?</kbd></dt><dd>本浮层</dd>
    </dl>
    <div class="help-foot">3D 舞台可按住拖拽旋转、滚轮缩放;审计日志行悬停可读全文。</div>
  </div>`;
document.body.append(helpOv);
helpOv.addEventListener('click', (e) => {
  if (e.target === helpOv) toggleHelp(false);
});
function toggleHelp(force?: boolean): void {
  const show = force ?? helpOv.hidden;
  helpOv.hidden = !show;
  if (show) helpOv.querySelector<HTMLElement>('.help-card')?.focus();
}

/* 修复(按钮审计 P2-4):2D 保底下相机/截图键无人应答、零可见反馈。
 * 现给节流提示(审计日志琥珀行),3D 接管后行为不变。 */
let stageKeyHintAt = 0;
function stageKeyHint(msg: string): void {
  const now = performance.now();
  if (now - stageKeyHintAt < 3000) return;
  stageKeyHintAt = now;
  store.log({
    tone: 'replay', sev: 'warn', terminalId: null, runId: null, type: 'server.log',
    text: `2D 保底模式:${msg},按键已忽略(3D 接管后可用)。`,
  });
}

window.addEventListener('keydown', (e) => {
  const tag = (e.target as HTMLElement | null)?.tagName;
  if (tag === 'INPUT' || tag === 'SELECT' || tag === 'TEXTAREA') return;
  if (e.ctrlKey || e.altKey || e.metaKey) return;
  if (e.key === 'Escape') { toggleHelp(false); return; }
  if (e.key === '?') { toggleHelp(); schedule(); return; }
  if (e.shiftKey && /^[1-7]$/.test(e.key)) {
    runScenario(`S${e.key}` as ScenarioId);
    schedule();
    return;
  }
  switch (e.key.toLowerCase()) {
    case 'h':
      store.patchUi({ topbarHidden: !store.snapshot.ui.topbarHidden });
      break;
    case 'r':
      store.patchUi({ rightDrawerOpen: !store.snapshot.ui.rightDrawerOpen });
      break;
    case '1': case '2': case '3': case '4':
      if (!store.snapshot.ui.stage3d) { stageKeyHint(`相机预设 ${e.key} 仅 3D 舞台可用`); break; }
      emit(STAGE_CAMERA, { preset: Number(e.key) });
      break;
    case 'f':
      if (!store.snapshot.ui.stage3d) { stageKeyHint('截图 F 仅 3D 舞台可用'); break; }
      emit(STAGE_SHOT, { name: 'stage' });
      break;
  }
  schedule();
});

/* <1280px 时右栏是离屏抽屉,需要一枚可见的开关(§6.1 断点) */
const narrow = window.matchMedia('(max-width:1280px)');
const drawerBtn = document.createElement('button');
drawerBtn.className = 'btn ghost';
drawerBtn.textContent = '判定面板';
drawerBtn.title = '右栏在 <1280px 下折叠为抽屉(快捷键 R)';
drawerBtn.addEventListener('click', () => {
  store.patchUi({ rightDrawerOpen: !store.snapshot.ui.rightDrawerOpen });
  schedule();
});
const stageTitle = stage.el.querySelector('.stage-title');
if (stageTitle) stageTitle.insertBefore(drawerBtn, stageTitle.querySelector('.st-hud'));

function applyNarrow(): void {
  const on = narrow.matches;
  drawerBtn.hidden = !on;
  // 宽屏时抽屉状态无意义,强制关闭,避免切回窄屏时抽屉莫名弹开
  if (!on && store.snapshot.ui.rightDrawerOpen) store.patchUi({ rightDrawerOpen: false });
}
applyNarrow();
narrow.addEventListener('change', applyNarrow);

/* 抽屉开合落到 body 上(class 驱动 CSS transform,见 console.css 断点段) */
store.subscribe(s => {
  const open = s.ui.rightDrawerOpen && narrow.matches;
  document.body.classList.toggle('drawer-open', open);
  // 开合态此前只体现在 body 的 class 上,读屏听不到;aria-expanded 说出来
  drawerBtn.setAttribute('aria-expanded', String(open));
});

window.addEventListener('error', (e) => {
  store.log({
    tone: 'error', sev: 'error', terminalId: null, runId: null,
    type: 'run.error', text: `页面异常:${e.message}`,
  });
});
window.addEventListener('unhandledrejection', (e) => {
  store.log({
    tone: 'error', sev: 'error', terminalId: null, runId: null,
    type: 'run.error', text: `未处理的 Promise 拒绝:${String(e.reason)}`,
  });
});

/* 首次渲染 */
schedule();
