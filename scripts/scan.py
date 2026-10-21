#!/usr/bin/env python3
"""
扫描 Markdown 项目，检测会阻断文档站构建的语法冲突。

用法:
    python3 scan.py <md项目目录> [--json]

退出码: 0 无阻断问题；1 发现阻断问题或路径错误
"""
import argparse
import json
import os
import re
import sys

# 正文（代码块外）里被 Vue 编译器误判的模式
PATTERNS = [
    {
        'id': 'autolink',
        'level': 'blocker',
        'regex': re.compile(r'<(?:https?|ftp|mailto):[^>\s]+>'),
        'desc': '自动链接 <https://...> 会被 Vue 当成标签',
        'fix': '由 config.mjs 的 escape_vue_syntax 规则自动转义（已内置，无需手工改）',
    },
    {
        'id': 'raw_img',
        'level': 'blocker',
        'regex': re.compile(r'<img\b[^>]*>', re.I),
        'desc': '原始 <img> 标签会被 Vite 当作模块 import',
        'fix': '转换为 Markdown 语法 ![说明](相对路径)',
    },
    {
        'id': 'mustache',
        'level': 'blocker',
        'regex': re.compile(r'\{\{|\}\}'),
        'desc': '{{ }} 会被 Vue 当作插值表达式',
        'fix': '由 escape_vue_syntax 自动转义（已内置）',
    },
    {
        'id': 'placeholder_angle',
        'level': 'warn',
        'regex': re.compile(r'<[A-Za-z][\w.\-]*[:：][\w.\-]+>'),
        'desc': '形如 <email_hash:a1b2> 的占位符会被当作未知标签',
        'fix': '由 escape_vue_syntax 转为纯文本（已内置）',
    },
    {
        'id': 'raw_table_html',
        'level': 'warn',
        'regex': re.compile(r'<(table|div|span|style|script)\b', re.I),
        'desc': '正文中的块级 HTML 标签，Vue 模板中可能破坏结构',
        'fix': '建议改为 Markdown 或放入自定义组件',
    },
]

IMG_REF = re.compile(r'!\[[^\]]*\]\(\s*<?([^)\s>]+)>?[^)]*\)')
HTML_IMG_SRC = re.compile(r'<img\b[^>]*\bsrc\s*=\s*["\']([^"\']+)["\']', re.I)
FENCE = re.compile(r'^\s*(```|~~~)')


def iter_md(root):
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in {
            'node_modules', '.git', '.vitepress', 'dist', 'build', '.cache'}]
        for fn in sorted(filenames):
            if fn.lower().endswith(('.md', '.markdown')):
                yield os.path.join(dirpath, fn)


def rel(root, path):
    return os.path.relpath(path, root)


def scan(root):
    findings = []
    stats = {'files': 0, 'lines': 0, 'images_referenced': 0, 'images_missing': 0}

    for path in iter_md(root):
        stats['files'] += 1
        in_fence = False
        fence_lang = ''
        try:
            lines = open(path, encoding='utf-8', errors='replace').read().splitlines()
        except OSError as e:
            findings.append({'file': rel(root, path), 'line': 0, 'id': 'io',
                             'level': 'error', 'desc': f'读取失败: {e}', 'snippet': '', 'fix': ''})
            continue

        stats['lines'] += len(lines)
        base = os.path.dirname(path)

        for no, line in enumerate(lines, 1):
            if FENCE.match(line):
                if not in_fence:
                    in_fence = True
                    fence_lang = line.strip().lstrip('`~').strip().lower()
                else:
                    in_fence = False
                    fence_lang = ''
                continue
            if in_fence:
                continue

            for p in PATTERNS:
                m = p['regex'].search(line)
                if m:
                    findings.append({
                        'file': rel(root, path),
                        'line': no,
                        'id': p['id'],
                        'level': p['level'],
                        'desc': p['desc'],
                        'snippet': line.strip()[:160],
                        'fix': p['fix'],
                    })

            # 图片引用检查（跳过外链）
            refs = IMG_REF.findall(line) + HTML_IMG_SRC.findall(line)
            for ref in refs:
                if re.match(r'^(https?:)?//|^data:|^/assets/', ref):
                    continue
                stats['images_referenced'] += 1
                target = os.path.normpath(os.path.join(base, ref.split('?')[0].split('#')[0]))
                if not os.path.exists(target):
                    stats['images_missing'] += 1
                    findings.append({
                        'file': rel(root, path),
                        'line': no,
                        'id': 'missing_image',
                        'level': 'blocker',
                        'desc': f'图片不存在: {ref}',
                        'snippet': line.strip()[:160],
                        'fix': '确认文件名大小写与扩展名（.png/.jpeg/.jpg 易混），从源目录补齐',
                    })

    return findings, stats


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('root')
    ap.add_argument('--json', action='store_true')
    ap.add_argument('--only-blockers', action='store_true')
    args = ap.parse_args()

    root = os.path.abspath(args.root)
    if not os.path.isdir(root):
        print(f'目录不存在: {root}', file=sys.stderr)
        return 1

    findings, stats = scan(root)
    if args.only_blockers:
        findings = [f for f in findings if f['level'] in ('blocker', 'error')]

    if args.json:
        print(json.dumps({'stats': stats, 'findings': findings}, ensure_ascii=False, indent=2))
    else:
        by_id = {}
        for f in findings:
            by_id.setdefault(f['id'], []).append(f)

        print(f"扫描目录: {root}")
        print(f"文件 {stats['files']} 个 / {stats['lines']} 行；"
              f"图片引用 {stats['images_referenced']} 处，缺失 {stats['images_missing']} 处\n")

        if not findings:
            print('未发现阻断性问题，可直接初始化文档站。')
            return 0

        for fid, items in sorted(by_id.items(), key=lambda kv: -len(kv[1])):
            level = items[0]['level'].upper()
            print(f"[{level}] {fid}: {len(items)} 处 — {items[0]['desc']}")
            for it in items[:5]:
                print(f"    {it['file']}:{it['line']}  {it['snippet']}")
            if len(items) > 5:
                print(f"    ... 其余 {len(items) - 5} 处")
            if items[0].get('fix'):
                print(f"    处理: {items[0]['fix']}")
            print()

    blockers = [f for f in findings if f['level'] in ('blocker', 'error')]
    return 1 if blockers else 0


if __name__ == '__main__':
    sys.exit(main())
