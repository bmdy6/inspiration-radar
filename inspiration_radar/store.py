"""SQLite is authoritative. JSON and Markdown are recoverable local exports."""
from contextlib import contextmanager
from datetime import date, datetime, timezone
import json
import os
from pathlib import Path
import sqlite3
import tempfile

from .core import select_items


@contextmanager
def database(state):
    state = Path(state)
    state.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(state / 'radar.sqlite3', timeout=10)
    try:
        conn.execute('CREATE TABLE IF NOT EXISTS seen (key TEXT PRIMARY KEY, day TEXT NOT NULL)')
        conn.execute('CREATE TABLE IF NOT EXISTS reports (day TEXT PRIMARY KEY, data TEXT NOT NULL)')
        conn.commit()
        yield conn
    finally:
        conn.close()


def load_seen(state):
    path = Path(state) / 'radar.sqlite3'
    if not path.exists():
        return set()
    # Discovery never creates a state database.
    conn = sqlite3.connect(path.resolve().as_uri() + '?mode=ro', uri=True, timeout=10)
    try:
        return {r[0] for r in conn.execute('SELECT key FROM seen')}
    finally:
        conn.close()


def atomic_text(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(dir=path.parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def md(value):
    # Source titles and model text are untrusted; render them as plain Markdown text.
    text = ' '.join(str(value).split())
    for char in '\\`*_{}[]<>#!|':
        text = text.replace(char, '\\' + char)
    return text


def export_report(report, state):
    base = Path(state) / 'daily' / report['date']
    lines = [f"# {md(report['name'])} · {report['date']}", '']
    if report['demo']:
        lines += ['离线演示：使用合成素材与预置评分，未调用模型。', '']
    for item in report['items']:
        lines += [f"## {md(item['title'])}", '', f"它是什么：{md(item['what'])}", '',
                  f"最有意思的点：{md(item['highlight'])}", '', f"启发：{md(item['inspire'])}", '',
                  f"原始链接：<{item['url']}>", '', f"评分：{item['total_score']}/10", '']
    if not report['items']:
        lines += ['本批次没有符合规则的新条目。', '']
    atomic_text(base.with_suffix('.json'), json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    atomic_text(base.with_suffix('.md'), '\n'.join(lines))
    return str(base.with_suffix('.md'))


def publish(items, cfg, state, day, *, demo=False):
    if date.fromisoformat(day).isoformat() != day:
        raise ValueError('Date must be YYYY-MM-DD')
    with database(state) as conn:
        try:
            conn.execute('BEGIN IMMEDIATE')
            old = conn.execute('SELECT data FROM reports WHERE day=?', (day,)).fetchone()
            if old:
                report = json.loads(old[0])
                if report['demo'] != demo:
                    raise ValueError('Use separate state directories for demo and real data')
                status = 'already_published'
            else:
                seen = {r[0] for r in conn.execute('SELECT key FROM seen')}
                picked = select_items(items, cfg, seen, demo=demo)
                report = {'date': day, 'name': cfg['name'], 'demo': demo,
                          'generated_at': datetime.now(timezone.utc).isoformat(), 'items': picked}
                status = 'complete'
            path = export_report(report, state)
            if not old:
                conn.execute('INSERT INTO reports VALUES (?,?)', (day, json.dumps(report, ensure_ascii=False)))
                conn.executemany('INSERT INTO seen VALUES (?,?)',
                                 [(item['candidate_key'], day) for item in report['items']])
            conn.commit()
        except BaseException:
            conn.rollback()
            raise
    return {'status': status, 'count': len(report['items']), 'report': path}
