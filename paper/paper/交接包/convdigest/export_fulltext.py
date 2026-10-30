# -*- coding: utf-8 -*-
"""Export the frontend-author sessions as handover-pack full-text files (C-series style)."""
import os, json, glob, subprocess, datetime

CONV = r'C:\Users\<teammate>\Desktop\puf-drone-auth\paper\交接包\convdigest'
OUT  = r'C:\Users\<teammate>\Desktop\puf-drone-auth\paper\交接包\对话全文'
DSH  = os.path.expanduser('~/.dsh/sessions/--C-Users-<teammate>-Desktop-FPGA--')
CC   = os.path.expanduser('~/.claude/projects/c--Users-<teammate>-Desktop-FPGA')
BEIJING = datetime.timedelta(hours=8)
BANNER = ('> 本文件为**未截断全文**：用户=真人输入，助手=每轮最终回复，技能调用单独标注；系统注入类消息已剔除。时间=北京时间。\n'
          '> 本文件为**前端作者线（队友C）会话**，2026-10-24 由本机会话存档补录，与 C 系列（开发线对话）并列。')

def bj(ms):
    return datetime.datetime.utcfromtimestamp(ms/1000) + BEIJING

def bj_iso(iso):
    return datetime.datetime.fromisoformat(iso.replace('Z', '+00:00')) + BEIJING

def parse_dsh(session_dir):
    out = subprocess.run(['node', 'parse_sessions.mjs', session_dir], capture_output=True, text=True, cwd=CONV)
    events = []
    for line in out.stdout.splitlines():
        try:
            events.append(json.loads(line))
        except Exception:
            pass
    return events

def extract_dsh(session_dir):
    events = parse_dsh(session_dir)
    turns = []
    first = last = None
    for e in events:
        t = e.get('time') or e.get('timestamp')
        if not t:
            continue
        if first is None:
            first = t
        last = t
        if e.get('type') == 'user/message':
            d = e.get('data', {}) or {}
            src = d.get('source', {}) or {}
            content = d.get('content')
            if isinstance(content, list):
                txt = '\n'.join(p.get('text', '') for p in content if isinstance(p, dict) and p.get('type') == 'text')
            elif isinstance(content, str):
                txt = content
            else:
                txt = ''
            if src.get('kind') != 'user' or not src.get('rpcId'):
                continue
            if txt.startswith(('Current runtime context', '<system-reminder', '[model changed')):
                continue
            turns.append({'ts': t, 'user': txt, 'texts': [], 'ts_last': t, 'skills': []})
        elif e.get('type') == 'assistant/message':
            d = e.get('data', {}) or {}
            content = (d.get('message') or {}).get('content', [])
            txt = '\n'.join(p.get('text', '') for p in content if isinstance(p, dict) and p.get('type') == 'text')
            if not txt or not turns:
                continue
            turns[-1]['texts'].append(txt)
            turns[-1]['ts_last'] = t
    return first, last, turns

SKIP_PREFIX = ('<', 'Another Claude session', 'This session is being continued',
               '[Request interrupted', '[Image:', 'Base directory for this skill',
               'Current runtime context')

def extract_cc(jsonl):
    turns = []
    first = last = None
    with open(jsonl, encoding='utf-8', errors='replace') as fh:
        for line in fh:
            try:
                e = json.loads(line)
            except Exception:
                continue
            et = e.get('type')
            ts = e.get('timestamp')
            if not ts:
                continue
            if first is None:
                first = ts
            last = ts
            if et == 'user':
                if e.get('isSidechain'):
                    continue
                m = e.get('message', {}); c = m.get('content')
                if isinstance(c, str):
                    txt = c
                elif isinstance(c, list):
                    txt = '\n'.join(p.get('text', '') for p in c if isinstance(p, dict) and p.get('type') == 'text')
                else:
                    continue
                if e.get('toolUseResult') is not None or not txt:
                    continue
                if txt.startswith(SKIP_PREFIX) or e.get('isMeta'):
                    if txt.startswith('<command-name>'):
                        name = txt.split('</command-name>')[0].replace('<command-name>', '').strip()
                        if name and turns:
                            turns[-1]['skills'].append(name)
                    elif txt.startswith('Base directory for this skill'):
                        seg = txt.split(':', 1)[1].strip().split()[0].rstrip('\\/').replace('\\', '/')
                        name = seg.rstrip('/').split('/')[-1]
                        if name and turns:
                            turns[-1]['skills'].append(name)
                    continue
                turns.append({'ts': ts, 'user': txt, 'texts': [], 'ts_last': ts, 'skills': []})
            elif et == 'assistant':
                if e.get('isSidechain'):
                    continue
                m = e.get('message', {}); c = m.get('content')
                if not isinstance(c, list):
                    continue
                txt = '\n'.join(p.get('text', '') for p in c if isinstance(p, dict) and p.get('type') == 'text')
                if not txt or not turns:
                    continue
                turns[-1]['texts'].append(txt)
                turns[-1]['ts_last'] = ts
    return first, last, turns

def fmt_ts(x):
    if isinstance(x, str):
        return bj_iso(x)
    return bj(x)

def render(title, theme, session_id, first, last, turns, extra_note=None):
    lines = ['# ' + title, '']
    rng = '{0:%Y-%m-%d %H:%M:%S} ~ {1:%Y-%m-%d %H:%M:%S}'.format(fmt_ts(first), fmt_ts(last))
    lines.append('> ' + theme)
    lines.append('> 会话 {0} | {1} | {2} 轮'.format(session_id, rng, len(turns)))
    lines.append(BANNER)
    if extra_note:
        lines.append('> ' + extra_note)
    lines.append('')
    lines.append('---')
    lines.append('')
    for i, t in enumerate(turns, 1):
        lines.append('## [{0:%m-%d %H:%M}] 第{1}轮 · 用户'.format(fmt_ts(t['ts']), i))
        lines.append('')
        lines.append(t['user'].strip())
        if t.get('skills'):
            lines.append('')
            lines.append('> （技能调用：' + '、'.join(dict.fromkeys(t['skills'])) + '）')
        lines.append('')
        if t['texts']:
            lines.append('## [{0:%m-%d %H:%M}] 第{1}轮 · 助手'.format(fmt_ts(t['ts_last']), i))
            lines.append('')
            lines.append('\n\n'.join(x.strip() for x in t['texts']))
            lines.append('')
    return '\n'.join(lines) + '\n'

os.makedirs(OUT, exist_ok=True)

# F01: DSH main + appendix of the three short morning sessions
main_dir = glob.glob(os.path.join(DSH, 'session-0736428f*'))[0]
first, last, turns = extract_dsh(main_dir)
app = ['', '---', '', '## 附录：同日更早的三个短会话（DSH，各 1~2 轮）', '']
for sid in ['17a46d6a', '07f0ccfa', '296acb8c']:
    d = glob.glob(os.path.join(DSH, 'session-' + sid + '*'))
    if not d:
        continue
    f2, l2, t2 = extract_dsh(d[0])
    app.append('### session-{0}（{1:%m-%d %H:%M}~{2:%H:%M}）'.format(sid, bj(f2), bj(l2)))
    app.append('')
    for t in t2:
        app.append('**用户**：' + t['user'][:300])
        if t['texts']:
            app.append('**助手**：' + '\n\n'.join(t['texts'])[:800])
        app.append('')
app.append('（另有 session-650663c 为空会话，2026-10-15 08:59 创建后未使用，无内容。）')
txt = render('F1 · 前端作者线_Day1起步_DSH',
             'Three.js 控制界面起步：原型排障与工作区重构（工作区含 three.js 库 checkout 与地面站原型）',
             'session-0736428f-1727-4ab4-a892-d20cf3ec8a1b', first, last, turns)
with open(os.path.join(OUT, 'F01_1010_前端作者线_Day1起步_DSH_0736428f.md'), 'w', encoding='utf-8') as fh:
    fh.write(txt + '\n'.join(app))

# F02 / F03: Claude Code sessions
jobs = [
    ('944aa86b', 'F2 · 前端作者线_GCS大改设计',
     '全项目优化（brainstorming）→ GCS 大改设计稿 2026-10-11-gcs-overhaul-design.md',
     'F02_1011-1014_前端作者线_GCS大改设计_944aa86b.md', None),
    ('39206669', 'F3 · 前端作者线_前端主力会话',
     '按开发线《前端探索报告》改造前端→独立划分与交付打包→≥5 轮 UI 升级→截图+视觉模型评审→人工验收',
     'F03_1014-1016_前端作者线_前端主力会话_39206669.md',
     '（会话经历多次上下文压缩续接，原文均保留于本机 jsonl 存档。）'),
]
for sid, title, theme, fname, note in jobs:
    f = glob.glob(os.path.join(CC, sid + '*.jsonl'))[0]
    first, last, turns = extract_cc(f)
    txt = render(title, theme, sid + '（Claude Code 会话）', first, last, turns, extra_note=note)
    with open(os.path.join(OUT, fname), 'w', encoding='utf-8') as fh:
        fh.write(txt)

for p in sorted(glob.glob(os.path.join(OUT, 'F0*.md'))):
    n = sum(1 for _ in open(p, encoding='utf-8'))
    print(os.path.basename(p), n, 'lines')
