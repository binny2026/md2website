#!/usr/bin/env python3
"""
查找本机已生成的文档站（供「更新站点」使用）。

用法:
    python3 sites.py list                 # 列出所有已发现站点
    python3 sites.py list --json          # 输出 JSON（Agent 消费）
    python3 sites.py list --path <目录>   # 只扫描指定目录
    python3 sites.py list --match <关键词> # 按标题/路径过滤
    python3 sites.py select               # 交互选择，输出站点路径

识别依据: 目录下存在 docs/.vitepress/config.mjs。
扫描范围: 当前目录 → 当前目录的上级 → ~/Documents → 全局注册表。
"""
import argparse
import datetime
import json
import os
import re
import sys

SKIP_DIRS = {'node_modules', '.git', '.backup', 'dist', 'build', '.cache',
             '__pycache__', 'Library', 'Applications'}
META_FILE = '.md2website.json'
REGISTRY_FILE = os.path.join(os.path.expanduser('~'), '.md2website', 'sites.json')


def is_site(path):
    return os.path.isfile(os.path.join(path, 'docs', '.vitepress', 'config.mjs'))


def scan(root, maxdepth):
    """在 root 下扫描站点目录，命中站点后不再深入其内部"""
    found = []
    root = os.path.abspath(root)
    if not os.path.isdir(root):
        return found
    root_depth = root.rstrip(os.sep).count(os.sep)
    for dirpath, dirnames, _ in os.walk(root):
        depth = dirpath.rstrip(os.sep).count(os.sep) - root_depth
        if depth > maxdepth:
            dirnames[:] = []
            continue
        if is_site(dirpath):
            found.append(dirpath)
            dirnames[:] = []
            continue
        dirnames[:] = [d for d in dirnames
                       if d not in SKIP_DIRS and not d.startswith('.')]
    return found


def _read_json(path):
    try:
        with open(path, encoding='utf-8') as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def _config_title(path):
    cfg = os.path.join(path, 'docs', '.vitepress', 'config.mjs')
    try:
        with open(cfg, encoding='utf-8', errors='replace') as f:
            text = f.read(4000)
    except OSError:
        return ''
    m = re.search(r"title:\s*['\"]([^'\"]+)['\"]", text)
    return m.group(1) if m else ''


def _mtime(path):
    try:
        return datetime.datetime.fromtimestamp(
            os.path.getmtime(path)).strftime('%Y-%m-%d %H:%M')
    except OSError:
        return ''


def site_info(path):
    meta = _read_json(os.path.join(path, META_FILE))
    pkg = _read_json(os.path.join(path, 'package.json'))
    return {
        'path': path,
        'title': meta.get('title') or _config_title(path) or os.path.basename(path),
        'name': meta.get('name') or pkg.get('name') or '',
        'source': meta.get('source') or '',
        'base': meta.get('base') or '',
        'updated_at': meta.get('updated_at') or _mtime(
            os.path.join(path, 'docs', '.vitepress', 'config.mjs')),
        'has_meta': bool(meta),
        'has_deploy': os.path.isfile(os.path.join(path, '.deploy-local.yml')),
    }


def registry_paths():
    data = _read_json(REGISTRY_FILE)
    sites = data.get('sites') if isinstance(data, dict) else None
    if not isinstance(sites, list):
        return []
    return [s.get('path') for s in sites
            if isinstance(s, dict) and s.get('path') and os.path.isdir(s['path'])]


def collect(path=None, keyword=None):
    candidates = []
    if path:
        candidates.extend(scan(path, 8))
    else:
        cwd = os.path.abspath(os.getcwd())
        candidates.extend(scan(cwd, 3))
        parent = os.path.dirname(cwd)
        if parent and parent != cwd:
            candidates.extend(scan(parent, 2))
        docs = os.path.join(os.path.expanduser('~'), 'Documents')
        candidates.extend(scan(docs, 4))
    candidates.extend(registry_paths())

    seen = set()
    sites = []
    for p in candidates:
        real = os.path.realpath(p)
        if real in seen or not is_site(real):
            continue
        seen.add(real)
        sites.append(site_info(real))

    if keyword:
        kw = keyword.lower()
        sites = [s for s in sites
                 if kw in s['title'].lower() or kw in s['path'].lower()
                 or kw in (s['source'] or '').lower()]
    sites.sort(key=lambda s: s['updated_at'] or '', reverse=True)
    return sites


def print_table(sites):
    if not sites:
        print('没有找到已生成的文档站。')
        print('新建站点：python3 init.py <md目录> --out <站点目录>')
        return
    for i, s in enumerate(sites, 1):
        print(f'{i}) {s["title"]}')
        print(f'   站点   {s["path"]}')
        print(f'   源目录 {s["source"] or "（未记录，更新时需用 --source 指定）"}')
        flags = []
        flags.append('已配置部署' if s['has_deploy'] else '未配置部署')
        flags.append('元数据完整' if s['has_meta'] else '无元数据')
        if s['updated_at']:
            flags.append(s['updated_at'])
        print(f'   状态   {" · ".join(flags)}')
        print()


def pick(sites):
    """交互选择；非交互终端直接输出 JSON 供 Agent 决策"""
    if not sites:
        print('没有找到已生成的文档站。', file=sys.stderr)
        return 1
    if len(sites) == 1:
        print(sites[0]['path'])
        return 0
    if not sys.stdin.isatty():
        print(json.dumps({'action': 'choose', 'sites': sites},
                         ensure_ascii=False, indent=2))
        return 0
    print_table(sites)
    while True:
        try:
            raw = input(f'选择要更新的站点 [1-{len(sites)}，q 取消]: ').strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return 1
        if raw.lower() in ('q', 'quit', 'exit'):
            return 1
        if raw.isdigit() and 1 <= int(raw) <= len(sites):
            print(sites[int(raw) - 1]['path'])
            return 0
        print(f'  输入无效，请填 1-{len(sites)}')


def main():
    ap = argparse.ArgumentParser(description='查找已生成的文档站')
    sub = ap.add_subparsers(dest='cmd')

    p_list = sub.add_parser('list', help='列出站点')
    p_list.add_argument('--json', action='store_true', help='输出 JSON')
    p_list.add_argument('--path', default=None, help='只扫描指定目录')
    p_list.add_argument('--match', default=None, help='按标题/路径/源目录过滤')

    p_sel = sub.add_parser('select', help='交互选择站点')
    p_sel.add_argument('--path', default=None)
    p_sel.add_argument('--match', default=None)

    args = ap.parse_args()
    cmd = args.cmd or 'list'
    sites = collect(getattr(args, 'path', None), getattr(args, 'match', None))

    if cmd == 'select':
        return pick(sites)

    if getattr(args, 'json', False):
        print(json.dumps({'total': len(sites), 'sites': sites},
                         ensure_ascii=False, indent=2))
    else:
        print_table(sites)
    return 0


if __name__ == '__main__':
    sys.exit(main())
