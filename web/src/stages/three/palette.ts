/* ============================================================
 * 3D 舞台配色与图元小工具
 *
 * **配色不另造**:一律从 tokens.css 的 CSS 变量现读(报告 §4.1「禁止另造」)。
 * 这样 2D 时序图、右栏判定大字、3D 光束三者共用同一份色源 —— 改 token 一处,
 * 三处同时变,不存在「3D 里那个青色和面板上的青色不是一个青」的漂移。
 *
 * 读取时机有讲究:必须等样式表生效后(模块加载完、首帧渲染前)。故用惰性
 * 初始化 —— 首次取色发生在 startStage3d() 里,而不是模块顶层。若样式表尚未
 * 就绪就取,getPropertyValue 会返回空串,颜色会静默退化成黑色。
 * ============================================================ */
import {
  Color, CanvasTexture, SRGBColorSpace, Sprite, SpriteMaterial,
} from 'three';

/* tokens.css 中的语义色名(与 :root 逐字对应) */
const TOKEN_NAMES = {
  bg: '--bg', bg2: '--bg2', bg3: '--bg3', bg4: '--bg4',
  border: '--border', border2: '--border2',
  text: '--text', muted: '--muted', dim: '--dim',
  green: '--green', cyan: '--cyan', amber: '--amber', red: '--red',
  blue: '--blue', purple: '--purple', pink: '--pink',
  puf: '--puf', comm: '--comm', auth: '--auth', board: '--board',
  server: '--server', radio: '--radio',
} as const;

export type TokenName = keyof typeof TOKEN_NAMES;

/* 兜底值 = tokens.css 的现行取值。只有在样式表缺失/变量被改名时才用得上,
 * 且这种情况会在控制台留下一次 warn —— 不静默改颜色。 */
const FALLBACK: Record<TokenName, string> = {
  bg: '#070b14', bg2: '#0b111e', bg3: '#101827', bg4: '#172136',
  border: 'rgba(148,178,255,.10)', border2: 'rgba(148,178,255,.22)',
  text: '#dfe7f3', muted: '#7b8ba8', dim: '#5e7290',
  green: '#00d68f', cyan: '#22d3ee', amber: '#f59e0b', red: '#ef4444',
  blue: '#3b82f6', purple: '#a78bfa', pink: '#f472b6',
  puf: '#00d68f', comm: '#22d3ee', auth: '#f59e0b', board: '#ef4444',
  server: '#a78bfa', radio: '#f472b6',
};

let cache: Record<TokenName, Color> | null = null;
let rawCache: Record<TokenName, string> | null = null;
let warned = false;

function readAll(): Record<TokenName, string> {
  const cs = getComputedStyle(document.documentElement);
  const out = {} as Record<TokenName, string>;
  let missing = 0;
  for (const key of Object.keys(TOKEN_NAMES) as TokenName[]) {
    const v = cs.getPropertyValue(TOKEN_NAMES[key]).trim();
    if (!v) { out[key] = FALLBACK[key]; missing++; } else { out[key] = v; }
  }
  if (missing > 0 && !warned) {
    warned = true;
    console.warn(`[stage3d] ${missing} 个 token 变量未取到,已用兜底色。检查 tokens.css 是否加载。`);
  }
  return out;
}

/** 语义色(THREE.Color,已由 three 从 sRGB 转到工作色彩空间) */
export function pal(): Record<TokenName, Color> {
  if (!cache) {
    rawCache = readAll();
    const c = {} as Record<TokenName, Color>;
    for (const k of Object.keys(rawCache) as TokenName[]) c[k] = new Color(rawCache[k]);
    cache = c;
  }
  return cache;
}

/** 原始 CSS 字符串(画 canvas 标签时要 sRGB 原文) */
export function raw(name: TokenName): string {
  if (!rawCache) rawCache = readAll();
  return rawCache[name];
}

/* ---------- 文字标签精灵 ----------
 * 3D 场景里的「基站 / 无人机 / tid 7」若用 DOM 覆盖层做,会和 canvas 的缩放、
 * 相机运动脱节;用纹理精灵则天然随相机变换,且能被 Bloom 拾取到一点辉光。
 *
 * 做成有状态的小类而非一次性工厂:标签文本随状态变化(池水位、稳定位数、
 * 选中的 tid),而**重建纹理必须保留各自的字号** —— 早先用工厂函数重建时,
 * 每次都套同一个 size,结果无人机标签一刷新就跳回默认大小(实测踩过)。
 * 故 size 由实例持有,重绘只换纹理、不动尺寸。 */
export interface LabelOpts {
  size?: number;        // 世界单位下的字高
  color?: TokenName;
  glow?: boolean;
  weight?: number;
}

export class Label {
  readonly sprite: Sprite;
  private text: string;
  private color: TokenName;
  private size: number;
  private weight: number;
  private glow: boolean;

  constructor(text: string, o: LabelOpts = {}) {
    this.text = text;
    this.color = o.color ?? 'text';
    this.size = o.size ?? 0.5;
    this.weight = o.weight ?? 600;
    this.glow = o.glow !== false;
    this.sprite = new Sprite(new SpriteMaterial({
      transparent: true, depthWrite: false,
      // 标签不该被 Bloom 二次放大成光斑,故不透明度压在 1 以下
      opacity: 0.92,
    }));
    this.paint();
  }

  get object(): Sprite { return this.sprite; }

  /** 改文本/改色。内容与颜色都没变则直接返回 —— 重绘要新建 canvas 并上传
   *  纹理,每帧调用的代价是毫秒级,不能不做短路。 */
  set(text: string, color?: TokenName): void {
    const c = color ?? this.color;
    if (this.text === text && this.color === c) return;
    this.text = text;
    this.color = c;
    this.paint();
  }

  dispose(): void {
    this.sprite.material.map?.dispose();
    this.sprite.material.dispose();
  }

  private paint(): void {
    const px = 64;                       // 画布内字高(px),再按 size 缩到世界单位
    const color = raw(this.color);
    const font = `${this.weight} ${px}px 'Segoe UI',system-ui,sans-serif`;
    const pad = 18;

    const probe = document.createElement('canvas').getContext('2d')!;
    probe.font = font;
    const w = Math.ceil(probe.measureText(this.text).width) + pad * 2;
    const h = px + pad * 2;

    const cv = document.createElement('canvas');
    cv.width = w; cv.height = h;
    const g = cv.getContext('2d')!;
    g.font = font;
    g.textAlign = 'center';
    g.textBaseline = 'middle';
    if (this.glow) { g.shadowColor = color; g.shadowBlur = 14; }
    g.fillStyle = color;
    g.fillText(this.text, w / 2, h / 2);

    const tex = new CanvasTexture(cv);
    tex.colorSpace = SRGBColorSpace;
    const old = this.sprite.material.map;
    this.sprite.material.map = tex;
    this.sprite.material.needsUpdate = true;
    old?.dispose();

    this.sprite.scale.set((w / h) * this.size, this.size, 1);
  }
}
