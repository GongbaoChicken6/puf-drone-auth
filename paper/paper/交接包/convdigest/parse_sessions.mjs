#!/usr/bin/env node
// DSH 会话存档解析器：把 session.v4.jsonl.zstd（多帧 zstd 拼接）解成纯 JSONL 输出到 stdout。
// 用法: node parse_sessions.mjs <会话目录或 .zstd 文件路径> [> 输出.jsonl]
// 依赖: Node >= 22（zlib 内置 zstd），无第三方包。
import fs from "node:fs";
import path from "node:path";
import zlib from "node:zlib";

const arg = process.argv[2];
if (!arg) { console.error("用法: node parse_sessions.mjs <会话目录或session.v4.jsonl.zstd>"); process.exit(1); }
const st = fs.statSync(arg);
const file = st.isDirectory() ? path.join(arg, "session.v4.jsonl.zstd") : arg;
const buf = fs.readFileSync(file);
const MAGIC = Buffer.from([0x28, 0xb5, 0x2f, 0xfd]);
let pos = 0, frames = 0, bytes = 0;
const write = (chunk) => { bytes += chunk.length; process.stdout.write(chunk); };
while (pos < buf.length - 4) {
  const idx = buf.indexOf(MAGIC, pos);
  if (idx < 0) break;
  try {
    const out = zlib.zstdDecompressSync(buf.subarray(idx));
    if (out.length) { write(out); frames++; }
    pos = idx + 4;
  } catch { pos = idx + 4; }
}
process.stderr.write(`[parse_sessions] ${path.basename(file)}: ${frames} 帧拼接, ${bytes} 字节 JSONl\n`);
