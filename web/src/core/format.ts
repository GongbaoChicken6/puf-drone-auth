/* ============================================================
 * 格式化工具 —— hex 分段展示/时间戳/字节解码
 * 分段口径与 protocol.py 逐字节对齐:
 *   帧头 10B = STX|len|incompat|compat|seq|sysid|compid|msgid×3
 *   载荷     = 按 msg_id 的字段表(ACCESS_REQUEST "<II8s" 等)
 *   尾部 2B  = CRC-16/MCRF4XX 小端
 * ============================================================ */
import { MSG } from './types';

export interface HexSegment {
  label: string;
  bytes: string[];     // 每字节两位大写 hex
  tone: 'header' | 'payload' | 'crc' | 'field';
}

const H = (b: number) => b.toString(16).toUpperCase().padStart(2, '0');

export function hexBytes(hex: string): string[] {
  return (hex.replace(/[^0-9a-fA-F]/g, '').match(/../g) ?? []).map(s => s.toUpperCase());
}

export function hexSpaced(hex: string): string {
  return hexBytes(hex).join(' ');
}

/* 载荷字段表:字段名 + 字节数(小端多字节整数聚合展示) */
function payloadFields(msgId: number, n: number): { label: string; size: number }[] {
  switch (msgId) {
    case MSG.ACCESS_REQUEST: return [{ label: 'tid u32', size: 4 }, { label: 'nonce u32', size: 4 }, { label: 'C2 8B', size: 8 }];
    case MSG.CHALLENGE: return Array.from({ length: n / 8 }, (_, i) => ({ label: `seed${i + 1}`, size: 8 }));
    case MSG.EXTRA_CHALLENGE: return Array.from({ length: n / 8 }, (_, i) => ({ label: `xseed${i + 1}`, size: 8 }));
    case MSG.RESPONSE_R1: return Array.from({ length: n / 8 }, (_, i) => ({ label: `r1_${i + 1}`, size: 8 }));
    case MSG.RESULT: return [{ label: 'result u8', size: 1 }, { label: 'hd u8', size: 1 }, { label: 'R2 8B', size: 8 }];
    case MSG.CONFIRM: return [{ label: 'tid u32', size: 4 }, { label: 'status u8', size: 1 }];
    default: return n > 0 ? [{ label: 'payload', size: n }] : [];
  }
}

/* 帧按字段结构对齐分段(报告 §6.2:不做黄金帧逐字节 diff) */
export function segmentFrame(hex: string, msgId: number): HexSegment[] {
  const b = hexBytes(hex);
  const segs: HexSegment[] = [];
  if (b.length < 12) return [{ label: 'raw', bytes: b, tone: 'payload' }];
  const plen = parseInt(b[1], 16);
  const header = b.slice(0, 10);
  segs.push(
    { label: 'STX', bytes: header.slice(0, 1), tone: 'header' },
    { label: 'len', bytes: header.slice(1, 2), tone: 'header' },
    { label: 'flags', bytes: header.slice(2, 4), tone: 'header' },
    { label: 'seq', bytes: header.slice(4, 5), tone: 'header' },
    { label: 'sys/comp', bytes: header.slice(5, 7), tone: 'header' },
    { label: 'msgid', bytes: header.slice(7, 10), tone: 'header' },
  );
  const payload = b.slice(10, 10 + plen);
  let off = 0;
  for (const f of payloadFields(msgId, payload.length)) {
    if (off >= payload.length) break;
    const size = Math.min(f.size, payload.length - off);
    segs.push({ label: f.label, bytes: payload.slice(off, off + size), tone: 'field' });
    off += size;
  }
  if (off < payload.length) segs.push({ label: '…', bytes: payload.slice(off), tone: 'field' });
  segs.push({ label: 'CRC16', bytes: b.slice(10 + plen, 10 + plen + 2), tone: 'crc' });
  return segs;
}

/* 小端字节串 → 无符号整数(展示用) */
export function leToUint(bytes: string[]): number {
  return bytes.reduce((acc, s, i) => acc + parseInt(s, 16) * 2 ** (8 * i), 0);
}

export function hhmmss(ts: string | number | Date): string {
  const d = ts instanceof Date ? ts : new Date(ts);
  const p = (n: number, w = 2) => String(n).padStart(w, '0');
  return `${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}.${p(d.getMilliseconds(), 3)}`;
}

export function pct(n: number): string { return `${Math.round(n)}%`; }

/* 64bit 响应 hex → '1'/'0' 位串(MSB first,与 templates.stability.json 掩码同口径) */
export function hexToBits(hex: string): string {
  return hexBytes(hex).map(b => parseInt(b, 16).toString(2).padStart(8, '0')).join('');
}

/* hex → 位串后逐位异或距离(用于 S2 差异高亮的前端复算展示) */
export function hammingBits(a: string, b: string): number {
  const x = hexToBits(a), y = hexToBits(b);
  const n = Math.min(x.length, y.length);
  let d = 0;
  for (let i = 0; i < n; i++) if (x[i] !== y[i]) d++;
  return d;
}

/* ---------- 帧载荷提取(布局已用 docs/protocol_contract.md §4 黄金帧逐字节核对) ----------
 * 帧头 10B: STX|len|incompat|compat|seq|sysid|compid|msgid×3,msgid 为 3 字节**小端**。
 * len 即真实载荷长度(CHALLENGE/RESPONSE_R1 恒 32B = 4×8B)。CRC 尾 2B 小端。 */
export interface FrameParts {
  msgId: number;
  payload: string[];   // 大写两字符 hex 的字节序列
  crc: string[];
  len: number;
  seq: number;
}

export function frameParts(hex: string): FrameParts | null {
  const b = hexBytes(hex);
  if (b.length < 12) return null;
  const len = parseInt(b[1], 16);
  return {
    msgId: parseInt(b[7], 16) | (parseInt(b[8], 16) << 8) | (parseInt(b[9], 16) << 16),
    len,
    seq: parseInt(b[4], 16),
    payload: b.slice(10, 10 + len),
    crc: b.slice(10 + len, 12 + len),
  };
}

/* 载荷按 8 字节分组 —— CHALLENGE 的 seeds、RESPONSE_R1 的 r1s 都是 8B×n */
export function groupsOf8(payload: string[]): string[] {
  const out: string[] = [];
  for (let i = 0; i + 8 <= payload.length; i += 8) out.push(payload.slice(i, i + 8).join(''));
  return out;
}

/* ACCESS_REQUEST 载荷 = tid u32 LE | nonce u32 LE | C2 8B,取 C2 */
export function c2OfAccessRequest(hex: string): string | null {
  const p = frameParts(hex);
  if (!p || p.msgId !== MSG.ACCESS_REQUEST || p.payload.length < 16) return null;
  return p.payload.slice(8, 16).join('').toLowerCase();
}

/* RESULT 载荷 = result u8 | hd u8 | R2 8B(PASS 才有 R2) */
export function resultOfFrame(hex: string): { result: number; hd: number; r2: string | null } | null {
  const p = frameParts(hex);
  if (!p || p.msgId !== MSG.RESULT || p.payload.length < 2) return null;
  return {
    result: parseInt(p.payload[0], 16),
    hd: parseInt(p.payload[1], 16),
    r2: p.payload.length >= 10 ? p.payload.slice(2, 10).join('').toLowerCase() : null,
  };
}

/* 逐位差异统计,并给出差异位序号(MSB first,与稳定掩码同口径) */
export function bitDiff(aHex: string, bHex: string): { count: number; bits: number[] } {
  const x = hexToBits(aHex), y = hexToBits(bHex);
  const n = Math.min(x.length, y.length);
  const bits: number[] = [];
  for (let i = 0; i < n; i++) if (x[i] !== y[i]) bits.push(i);
  return { count: bits.length, bits };
}

/* ---------- /api/status 口径归一(§8.2) ----------
 * templates[].terminal_id 是字符串(TemplateDB.terminals() 返回 str),而
 * pools[].terminal_id 与全部 SSE 事件的 terminal_id 都是数字。跨两张表关联
 * (如 UI 卡片同时显示模板对数与池水位)必须先经此处归一,否则 === 恒假。 */
export function tidNum(tid: string | number): number { return Number(tid); }

/* 稳定位占比。模板行的 stable_bits 可为 null(掩码未算出);
 * 分母恒为 64(报告 §7 V3 / types.ts 展示层标注),取整口径与
 * TemplateDB.enroll() 的 round(100.0*n/64, 1) 一致,保证与 enroll.done 事件同数。 */
export const STABLE_BITS_TOTAL = 64;
export function stableBitsPct(stableBits: number | null | undefined): number | null {
  if (stableBits == null) return null;
  return Math.round((1000 * stableBits) / STABLE_BITS_TOTAL) / 10;
}

export { H as byteHex };

/* 水位条的填充比 → **transform 字面量**(报告 §4.3「动效仅 transform/opacity」)。
 *
 * 为什么不是 width:池水位是全程在变的(每个帧事件都可能更新),而 width 是
 * 布局属性 —— 每变一次都要让顶栏/终端卡重排一次,直接把这条动画推离合成器。
 * scaleX 走合成层,与 60fps 目标(§6.3)对齐。
 *
 * 夹到 0..100 再除以 100:后端给的 pool_pct 理论上在范围内,但水位条是用来
 * 读数的,一旦因为越界把条子拉出容器,读出来的比例就是错的 —— 宁可夹住。
 * 返回 4 位小数,避免浮点长尾把 HTML 属性撑成科学计数法。 */
export function barScale(pct: number | null | undefined): string {
  const v = Math.max(0, Math.min(100, Number(pct) || 0)) / 100;
  return `transform:scaleX(${v.toFixed(4)})`;
}
