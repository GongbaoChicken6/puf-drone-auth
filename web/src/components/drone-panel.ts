/* ============================================================
 * finals-demo-drone · 无人机演示 HUD(右下悬浮)
 *
 * 自订阅组件模式(同 ids-banner.ts):不占 console.html 网格,悬浮 body。
 * 数据源 = store.drones(与 3D 舞台/审计日志同源);选中 tid 绑定
 * store.selectedTerminal,无选中时置灰。
 * 按钮禁用矩阵与桥端 DroneSim._transition 逐格镜像(设计 §4.3,R2-P2)——
 * 防"现场点出 409":前端先按状态禁,后端仍是唯一裁决者。
 * ============================================================ */
import { api } from '../core/api';
import { store, type DroneEntry } from '../core/store';
import type { DroneCmdRequest, DroneFlightState } from '../core/types';

const STATE_CN: Record<DroneFlightState, string> = {
  LANDED: '待命', ARMED: '已解锁', TAKEOFF: '起飞', HOVER: '悬停',
  MOVE: '巡航', LAND: '降落', RTL: '返航',
};

/* 按态禁用矩阵:launch/takeoff 合并在 [起飞] 键(LANDED=launch,ARMED=takeoff) */
type Btn = 'takeoff' | 'wpA' | 'wpB' | 'hold' | 'rtl' | 'land' | 'lock';
const ENABLE: Record<DroneFlightState, Record<Btn, boolean>> = {
  LANDED: { takeoff: true, wpA: false, wpB: false, hold: false, rtl: false, land: false, lock: true },
  ARMED:  { takeoff: true, wpA: false, wpB: false, hold: false, rtl: false, land: false, lock: true },
  TAKEOFF:{ takeoff: false, wpA: false, wpB: false, hold: false, rtl: false, land: true, lock: true },
  HOVER:  { takeoff: false, wpA: true, wpB: true, hold: true, rtl: true, land: true, lock: true },
  MOVE:   { takeoff: false, wpA: true, wpB: true, hold: true, rtl: true, land: true, lock: true },
  RTL:    { takeoff: false, wpA: false, wpB: false, hold: false, rtl: false, land: true, lock: true },
  LAND:   { takeoff: false, wpA: false, wpB: false, hold: false, rtl: false, land: false, lock: true },
};

const REASON_CN: Record<string, string> = {
  AUTH_REQUIRED: '未认证,飞行已锁定',
  'BAD_PARAM:x,y required': '缺航点参数',
  'BAD_PARAM:non-finite x/y/alt': '航点参数非有限数',
};
const reasonCn = (r?: string | null): string =>
  r == null ? '' : (REASON_CN[r] ?? (r.startsWith('BAD_STATE:') ? `当前状态不可用: ${r.slice(10)}` : r));

/* 航点(与演示剧本 §11 一致:A=北5m东-2m,B=北-3m东4m) */
const WP_A = { x: 5, y: -2 }, WP_B = { x: -3, y: 4 };

export class DronePanel {
  readonly el: HTMLElement;
  private chip!: HTMLElement;
  private horizonG!: SVGGraphicsElement;   // 滚转+俯仰变换组
  private pitchBar!: SVGGraphicsElement;   // 俯仰平移条
  private vAlt!: HTMLElement;
  private vSpd!: HTMLElement;
  private vYaw!: HTMLElement;
  private vPos!: HTMLElement;
  private hint!: HTMLElement;
  private flash!: HTMLElement;
  private btns = new Map<string, HTMLButtonElement>();
  private raf = 0;
  private bridgeDownUntil = 0;   // content-review P3:桥不可达时按钮置灰 2s

  constructor() {
    this.el = document.createElement('div');
    this.el.className = 'drone-panel';
    this.el.innerHTML = `
      <div class="dp-head">
        <span class="dp-title">无人机演示 HUD · <span class="dp-tid mono">tid —</span></span>
        <span class="dp-chip" data-chip>未解锁</span>
      </div>
      <div class="dp-body">
        <svg class="dp-horizon" viewBox="-50 -50 100 100" aria-hidden="true">
          <defs><clipPath id="dp-clip"><circle cx="0" cy="0" r="44"/></clipPath></defs>
          <g data-horizon>
            <g data-pitch>
              <rect x="-90" y="-90" width="180" height="90" class="dp-sky"/>
              <rect x="-90" y="0" width="180" height="90" class="dp-ground"/>
              <line x1="-40" y1="0" x2="40" y2="0" class="dp-hline"/>
              <line x1="-20" y1="-10" x2="20" y2="-10" class="dp-hline dim"/>
              <line x1="-20" y1="10" x2="20" y2="10" class="dp-hline dim"/>
            </g>
          </g>
          <circle cx="0" cy="0" r="44" class="dp-ring"/>
          <g class="dp-plane"><line x1="-26" y1="0" x2="-8" y2="0"/><line x1="8" y1="0" x2="26" y2="0"/><circle cx="0" cy="0" r="2.2"/></g>
        </svg>
        <div class="dp-reads mono">
          <div><span>alt</span><b data-alt>—</b><i>m</i></div>
          <div><span>v</span><b data-spd>—</b><i>m/s</i></div>
          <div><span>yaw</span><b data-yaw>—</b><i>°</i></div>
          <div><span>pos</span><b data-pos>—</b></div>
        </div>
      </div>
      <div class="dp-hint" data-hint>先认证解锁 —— 板上 SW7 或终端卡「巡检」</div>
      <div class="dp-actions">
        <button class="btn green" data-cmd="takeoff">解锁起飞</button>
        <button class="btn" data-cmd="wpA">航点 A</button>
        <button class="btn" data-cmd="wpB">航点 B</button>
      </div>
      <div class="dp-actions">
        <button class="btn" data-cmd="hold">悬停</button>
        <button class="btn amber" data-cmd="rtl">返航</button>
        <button class="btn amber" data-cmd="land">降落</button>
        <button class="btn ghost" data-cmd="lock">上锁</button>
      </div>
      <div class="dp-flash" data-flash hidden></div>`;
    this.chip = this.el.querySelector('[data-chip]')!;
    this.horizonG = this.el.querySelector('[data-horizon]')!;
    this.pitchBar = this.el.querySelector('[data-pitch]')!;
    this.vAlt = this.el.querySelector('[data-alt]')!;
    this.vSpd = this.el.querySelector('[data-spd]')!;
    this.vYaw = this.el.querySelector('[data-yaw]')!;
    this.vPos = this.el.querySelector('[data-pos]')!;
    this.hint = this.el.querySelector('[data-hint]')!;
    this.flash = this.el.querySelector('[data-flash]')!;
    this.el.querySelectorAll<HTMLButtonElement>('[data-cmd]').forEach(b => {
      this.btns.set(b.dataset.cmd!, b);
      b.addEventListener('click', () => void this.send(b.dataset.cmd!));
    });
    store.subscribe(() => this.schedule());
    this.render();
  }

  private schedule(): void {
    if (this.raf) return;
    this.raf = requestAnimationFrame(() => { this.raf = 0; this.render(); });
  }

  private cur(): DroneEntry | null {
    const tid = store.snapshot.selectedTerminal;
    if (tid == null) return null;
    return store.snapshot.drones.get(tid) ?? null;
  }

  private async send(cmd: string): Promise<void> {
    const tid = store.snapshot.selectedTerminal;
    if (tid == null) return;
    try {
      const r = await api.droneCmd(this.body(tid, cmd));
      if (!r.ok) this.showFlash(`✗ ${reasonCn(r.reason) || '指令被拒'}`);
    } catch {
      /* 网络(fetch reject):置灰 2s + 桥不可达提示(设计 R2-P3-5,content
       * review 指出原版只闪红未置灰、注释与行为不符) */
      this.bridgeDownUntil = performance.now() + 2000;
      this.showFlash('✗ 桥不可达');
      this.render();
    }
  }

  private body(tid: number, cmd: string): DroneCmdRequest {
    if (cmd === 'wpA') return { terminal_id: tid, cmd: 'goto', ...WP_A };
    if (cmd === 'wpB') return { terminal_id: tid, cmd: 'goto', ...WP_B };
    /* content-review P1:[起飞]键按态映射 —— LANDED 发 launch(arm+takeoff
     * 合并命令),ARMED 发 takeoff。此前恒发 takeoff,而 _T.takeoff 源态仅
     * ARMED:面板解锁后第一击必 409 BAD_STATE:LANDED,手动起飞流断裂
     * (S8 走 fly('launch') 故 e2e 未暴露)。 */
    if (cmd === 'takeoff') {
      const st = this.cur()?.state ?? 'LANDED';
      return { terminal_id: tid, cmd: st === 'ARMED' ? 'takeoff' : 'launch' };
    }
    return { terminal_id: tid, cmd: cmd as DroneCmdRequest['cmd'] };
  }

  private showFlash(text: string): void {
    this.flash.textContent = text;
    this.flash.hidden = false;
    window.setTimeout(() => { this.flash.hidden = true; }, 3200);
  }

  private render(): void {
    const tid = store.snapshot.selectedTerminal;
    const d = this.cur();
    this.el.classList.toggle('dp-none', tid == null);
    if (tid != null) this.el.querySelector<HTMLElement>('.dp-tid')!.textContent = `tid ${tid}`;

    const st: DroneFlightState = d?.state ?? 'LANDED';
    const unlocked = d?.unlocked ?? false;
    const att = d?.att;

    this.chip.textContent = unlocked ? `${STATE_CN[st]}` : '🔒 未解锁';
    this.chip.className = 'dp-chip ' + (unlocked
      ? (st === 'LANDED' || st === 'ARMED' ? 'idle' : 'fly') : 'locked');

    /* 姿态仪:roll 旋转(地平线反向),pitch 平移(1.4px/deg) */
    const roll = att?.roll ?? 0, pitch = att?.pitch ?? 0;
    this.horizonG.setAttribute('transform', `rotate(${(-roll).toFixed(1)})`);
    this.pitchBar.setAttribute('transform', `translate(0 ${(pitch * 1.4).toFixed(2)})`);

    const spd = att ? Math.hypot(att.vx, att.vy, att.vz) : null;
    this.vAlt.textContent = att ? att.alt.toFixed(1) : '—';
    this.vSpd.textContent = spd == null ? '—' : spd.toFixed(1);
    this.vYaw.textContent = att ? att.yaw.toFixed(0).padStart(3, '0') : '—';
    this.vPos.textContent = d ? `(${d.pos[0].toFixed(1)}, ${d.pos[1].toFixed(1)})` : '—';

    /* 按态禁用矩阵(镜像 §3.2 转移表)+ 认证门控 */
    const en = ENABLE[st];
    const bridgeDown = performance.now() < this.bridgeDownUntil;
    for (const [k, b] of this.btns) {
      b.disabled = tid == null || !unlocked || !en[k as Btn] || bridgeDown;
      if (k === 'takeoff') b.textContent = st === 'ARMED' ? '起飞' : '解锁起飞';
    }
    this.hint.hidden = unlocked;
  }
}
