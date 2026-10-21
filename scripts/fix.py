#!/usr/bin/env python3
"""
自动修复 scan.py 能发现的图片类阻断问题。

默认只做"安全修复"：
  1. 原始 <img src="...">  → Markdown ![](相对路径)
  2. jpeg/jpg/png 扩展名写错但目标存在 → 修正为真实文件名
  3. 文件名大小写不一致 → 修正为真实文件名

用法:
    python3 fix.py <md项目目录> [--dry-run]
"""
import argparse
import os
import re
import sys

HTML_IMG = re.compile(r'<img\b([^>]*?)/?>', re.I)
ATTR_SRC = re.compile(r'\bsrc\s*=\s*["\']([^"\']+)["\']', re.I)
ATTR_ALT = re.compile(r'\balt\s*=\s*["\']([^"\']*)["\']', re.I)
FENCE = re.compile(r'^\s*(```|~~~)')
IMG_REF = re.compile(r'!\[([^\]]*)\]\(\s*<?([^)\s>]+)>?([^)]*)\)')


def build_index(base):
    """目录下文件名(小写) → 真实文件名，用于纠正大小写/扩展名"""
    idx = {}
    for d in (base, os.path.join(base, 'assets')):
        if os.path.isdir(d):
            for fn in os.listdir(d):
                if os.path.isfile(os.path.join(d, fn)):
                    idx.setdefault(fn.lower(), fn)
                    stem, ext = os.path.splitext(fn)
                    if ext.lower() in ('.jpeg', '.jpg'):
                        idx.setdefault((stem + '.jpeg').lower(), fn)
                        idx.setdefault((stem + '.jpg').lower(), fn)
                    if ext.lower() == '.png':
                        idx.setdefault((stem + '.png').lower(), fn)
    return idx


def resolve(ref, base, idx):
    """返回 (是否需改写, 新ref)"""
    if re.match(r'^(https?:)?//|^data:|^/|^#', ref):
        return False, ref
    clean = ref.split('?')[0].split('#')[0]
    target = os.path.normpath(os.path.join(base, clean))
    if os.path.exists(target):
        return False, ref
    # 尝试按文件名索引纠正
    dirpart, fn = os.path.split(clean)
    real = idx.get(fn.lower())
    if real and (not dirpart or dirpart.rstrip('/').endswith('assets')):
        new = (dirpart.rstrip('/') + '/' + real) if dirpart else real
        return True, new
    return False, ref


def fix_file(path, dry):
    base = os.path.dirname(path)
    idx = build_index(base)
    lines = open(path, encoding='utf-8').read().splitlines(keepends=True)
    out, in_fence, changed = [], False, []

    for no, line in enumerate(lines, 1):
        if FENCE.match(line):
            in_fence = not in_fence
            out.append(line)
            continue
        if in_fence:
            out.append(line)
            continue

        new_line = line

        # 1) <img> → Markdown
        def repl_img(m):
            attrs = m.group(1)
            src = ATTR_SRC.search(attrs)
            if not src:
                return m.group(0)
            ref = src.group(1)
            alt = ATTR_ALT.search(attrs)
            alt_text = alt.group(1) if alt else ''
            need, newref = resolve(ref, base, idx)
            changed.append((no, 'raw_img', f'<img src="{ref}"> → ![{alt_text}]({newref})'))
            return f'![{alt_text}]({newref})'

        new_line = HTML_IMG.sub(repl_img, new_line)

        # 2) Markdown 图片路径纠正
        def repl_md(m):
            alt, ref, tail = m.group(1), m.group(2), m.group(3)
            need, newref = resolve(ref, base, idx)
            if need:
                changed.append((no, 'bad_path', f'{ref} → {newref}'))
                return f'![{alt}]({newref}{tail})'
            return m.group(0)

        new_line = IMG_REF.sub(repl_md, new_line)
        out.append(new_line)

    if changed and not dry:
        with open(path, 'w', encoding='utf-8') as f:
            f.writelines(out)
    return changed


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('root')
    ap.add_argument('--dry-run', action='store_true')
    args = ap.parse_args()

    root = os.path.abspath(args.root)
    if not os.path.isdir(root):
        print(f'目录不存在: {root}', file=sys.stderr)
        return 1

    total = 0
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in {
            'node_modules', '.git', '.vitepress', 'dist', 'build'}]
        for fn in sorted(filenames):
            if not fn.lower().endswith(('.md', '.markdown')):
                continue
            path = os.path.join(dirpath, fn)
            changes = fix_file(path, args.dry_run)
            if changes:
                total += len(changes)
                tag = '[预览]' if args.dry_run else '[已修改]'
                print(f'{tag} {os.path.relpath(path, root)}')
                for no, kind, desc in changes:
                    print(f'    L{no} ({kind}) {desc}')

    if total == 0:
        print('没有需要修复的图片问题。')
    else:
        verb = '待修复' if args.dry_run else '已修复'
        print(f'\n共 {verb} {total} 处。')
        if args.dry_run:
            print('去掉 --dry-run 实际写入。')
    return 0


if __name__ == '__main__':
    sys.exit(main())
