/* ============================================================
 * index.html 导航壳(报告 §5:P1,品牌头 + 两页入口 + 链路状态)
 * 合并入组员仓库后,四看板互链(../docs/*.html)自然生效
 * ============================================================ */
import './styles/tokens.css';
import './styles/base.css';
import { api } from './core/api';

const app = document.querySelector<HTMLElement>('#app')!;

function linkBadge(ok: boolean, mode: string): string {
  return ok
    ? `<span class="chip cyan"><span class="dot"></span>桥接在线 · ${mode.toUpperCase()}</span>`
    : `<span class="chip red"><span class="dot"></span>桥接离线</span>`;
}

function render(online: boolean, mode = '—'): void {
  app.innerHTML = `
  <div style="max-width:960px;margin:0 auto;padding:48px 24px;">
    <header style="margin-bottom:40px;">
      <div class="chip purple" style="margin-bottom:14px;">FPGA 赛道 · 竞赛演示</div>
      <h1 style="font-size:34px;font-weight:800;letter-spacing:.5px;">PUF 无人机身份认证</h1>
      <p style="color:var(--muted);margin:10px 0 0;font-size:15px;">
        硬件指纹挑战-应答 · HF-IDA 协议 · 前端演示与可视化模块
      </p>
      <div style="margin-top:18px;" id="link-badge">${linkBadge(online, mode)}</div>
    </header>

    <div style="display:grid;grid-template-columns:1fr 1fr;gap:20px;">
      <a class="card active hoverlift" href="./console.html" style="padding:26px;display:block;text-decoration:none;color:inherit;">
        <h2 style="font-size:19px;color:var(--cyan);">🛰 演示控制台</h2>
        <p style="color:var(--muted);margin:10px 0 0;">认证五帧实时动画 · 双向判定 · 场景演示 S1–S7 · 3D 认证舞台</p>
        <p class="mono" style="color:var(--muted);margin:14px 0 0;font-size:11px;">P1 · 互斥演示主舞台</p>
      </a>
      <a class="card wait hoverlift" href="./viz.html" style="padding:26px;display:block;text-decoration:none;color:inherit;">
        <h2 style="font-size:19px;color:var(--green);">📊 数据可视化</h2>
        <p style="color:var(--muted);margin:10px 0 0;">HD 分布 · ROC/EER · 模板位矩阵 · 报告插图导出</p>
        <p class="mono" style="color:var(--muted);margin:14px 0 0;font-size:11px;">P2 · 实验数据可视化</p>
      </a>
    </div>

    <div class="card" id="dash-card" style="margin-top:20px;padding:18px 22px;">
      <h3 style="font-size:13px;color:var(--muted);font-weight:600;letter-spacing:.5px;">项目看板(组员仓库 docs/dashboards/)</h3>
      <div style="display:flex;gap:10px;flex-wrap:wrap;margin-top:10px;">
        <a class="chip" href="../docs/dashboards/project_status.html">project_status</a>
        <a class="chip" href="../docs/dashboards/project_flow.html">project_flow</a>
        <a class="chip" href="../docs/dashboards/architecture.html">architecture</a>
        <a class="chip" href="../docs/dashboards/mindmap.html">mindmap</a>
      </div>
    </div>

    <p style="color:var(--muted);font-size:11px;margin-top:28px;">
      演示链路:浏览器 ←SSE/HTTP→ Python 桥接(127.0.0.1:8642)← server 公共 API · 完全离线
    </p>
  </div>`;

  /* 修复(按钮审计 P1-1):原绑定挂在 #link-badge 下,而看板 chip 在兄弟卡片里,
   * 选择器命中空集,preventDefault 永不生效;且桥接交付形态下 /docs 需映射。
   * 现按 href 前缀全量绑定:先拦截,探测可达(合并布局 + 桥接 --docs-dir)则放行
   * 导航,不可达才给出提示——不再无脑挡跳转,也不再静默 404。 */
  app.querySelectorAll('a.chip[href^="../docs"]').forEach(a => {
    (a as HTMLAnchorElement).addEventListener('click', e => {
      const href = (a as HTMLAnchorElement).getAttribute('href')!;
      e.preventDefault();
      void fetch(href).then(r => {
        if (r.ok) { window.location.href = href; return; }
        dashHint('看板位于组员仓库 docs/dashboards/,当前工作区不可达——模块合并(桥接映射 /docs/)后互链生效');
      }).catch(() => {
        dashHint('看板链接探测失败(桥接未映射 /docs/)——模块合并后互链生效');
      });
    });
  });
}

function dashHint(text: string): void {
  let el = document.getElementById('dash-hint');
  if (!el) {
    el = document.createElement('p');
    el.id = 'dash-hint';
    el.style.cssText = 'color:var(--amber);font-size:11px;margin:8px 0 0;';
    document.getElementById('dash-card')?.after(el);
  }
  el.textContent = text;
}

/* P3(按钮审计 N4):轮询结果未变时不重写 DOM —— 每 5s 全量重建会周期性打掉
 * 键盘焦点、悬停态与 dash-hint 提示。 */
let lastPollKey: string | null = null;
function applyPoll(online: boolean, mode: string): void {
  const key = online + '|' + mode;
  if (key === lastPollKey) return;
  lastPollKey = key;
  render(online, mode);
}

async function poll(): Promise<void> {
  try {
    const st = await api.getStatus();
    applyPoll(true, st.link.mode);
  } catch {
    applyPoll(false, '—');
  }
}

void poll();
window.setInterval(() => void poll(), 5000);
