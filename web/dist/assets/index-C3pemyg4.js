import{a as d}from"./api-DfqN_a4j.js";const o=document.querySelector("#app");function h(e,t){return e?`<span class="chip cyan"><span class="dot"></span>桥接在线 · ${t.toUpperCase()}</span>`:'<span class="chip red"><span class="dot"></span>桥接离线</span>'}function m(e,t="—"){o.innerHTML=`
  <div style="max-width:960px;margin:0 auto;padding:48px 24px;">
    <header style="margin-bottom:40px;">
      <div class="chip purple" style="margin-bottom:14px;">FPGA 赛道 · 竞赛演示</div>
      <h1 style="font-size:34px;font-weight:800;letter-spacing:.5px;">PUF 无人机身份认证</h1>
      <p style="color:var(--muted);margin:10px 0 0;font-size:15px;">
        硬件指纹挑战-应答 · HF-IDA 协议 · 前端演示与可视化模块
      </p>
      <div style="margin-top:18px;" id="link-badge">${h(e,t)}</div>
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
  </div>`,o.querySelectorAll('a.chip[href^="../docs"]').forEach(a=>{a.addEventListener("click",l=>{const s=a.getAttribute("href");l.preventDefault(),fetch(s).then(c=>{if(c.ok){window.location.href=s;return}r("看板位于组员仓库 docs/dashboards/,当前工作区不可达——模块合并(桥接映射 /docs/)后互链生效")}).catch(()=>{r("看板链接探测失败(桥接未映射 /docs/)——模块合并后互链生效")})})})}function r(e){var a;let t=document.getElementById("dash-hint");t||(t=document.createElement("p"),t.id="dash-hint",t.style.cssText="color:var(--amber);font-size:11px;margin:8px 0 0;",(a=document.getElementById("dash-card"))==null||a.after(t)),t.textContent=e}let i=null;function p(e,t){const a=e+"|"+t;a!==i&&(i=a,m(e,t))}async function n(){try{const e=await d.getStatus();p(!0,e.link.mode)}catch{p(!1,"—")}}n();window.setInterval(()=>void n(),5e3);
