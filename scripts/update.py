#!/usr/bin/env python3
"""
更新已有文档站：按站点记录的源目录重新生成内容并构建。

用法:
    python3 update.py                      # 自动查找站点；多个则让你选
    python3 update.py <站点目录>            # 更新指定站点
    python3 update.py <站点目录> --deploy   # 更新并部署
    python3 update.py <站点目录> --dry-run  # 只显示计划，不动文件
    python3 update.py <站点目录> --source <md目录>  # 手动指定源目录

行为:
  - 重新扫描源目录，覆盖 docs/ 内容与侧边栏配置（新增章节自动进导航）
  - 覆盖前把 docs/.vitepress 备份到 .backup/vitepress-<时间戳>
  - 保留 .deploy-local.yml 与 node_modules
  - 默认只构建不部署；加 --deploy 才会发布
"""
import argparse
import datetime
import json
import os
import re
import shutil
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sites as site_index  # noqa: E402

META_FILE = '.md2website.json'


def _read_json(path):
    try:
        with open(path, encoding='utf-8') as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def _config_base(path):
    cfg = os.path.join(path, 'docs', '.vitepress', 'config.mjs')
    try:
        with open(cfg, encoding='utf-8', errors='replace') as f:
            text = f.read(4000)
    except OSError:
        return '/'
    m = re.search(r"base:\s*['\"]([^'\"]+)['\"]", text)
    return m.group(1) if m else '/'


def choose(site_arg):
    """定位站点：路径 → 匹配；未给 → 自动查找，多个则交互选择"""
    if site_arg:
        path = os.path.abspath(site_arg)
        if site_index.is_site(path):
            return path
        matched = site_index.collect(None, site_arg)
        if len(matched) == 1:
            return matched[0]['path']
        if not matched:
            print(f'没有找到匹配「{site_arg}」的站点', file=sys.stderr)
            return None
        print(f'「{site_arg}」匹配到 {len(matched)} 个站点，请指定完整路径：',
              file=sys.stderr)
        site_index.print_table(matched)
        return None

    found = site_index.collect()
    if not found:
        print('没有找到已生成的文档站。新建站点：\n'
              '  python3 init.py <md目录> --out <站点目录>', file=sys.stderr)
        return None
    if len(found) == 1:
        print(f'找到站点：{found[0]["path"]}')
        return found[0]['path']

    if not sys.stdin.isatty():
        print(json.dumps({'action': 'choose', 'sites': found},
                         ensure_ascii=False, indent=2))
        return None

    site_index.print_table(found)
    while True:
        try:
            raw = input(f'选择要更新的站点 [1-{len(found)}，q 取消]: ').strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return None
        if raw.lower() in ('q', 'quit', 'exit'):
            return None
        if raw.isdigit() and 1 <= int(raw) <= len(found):
            return found[int(raw) - 1]['path']
        print(f'  输入无效，请填 1-{len(found)}')


def run(cmd, cwd):
    print(f'  $ {" ".join(cmd)}')
    proc = subprocess.run(cmd, cwd=cwd)
    return proc.returncode


def main():
    ap = argparse.ArgumentParser(description='更新已有文档站')
    ap.add_argument('site', nargs='?', default=None, help='站点目录或标题关键词')
    ap.add_argument('--source', default=None, help='手动指定 Markdown 源目录')
    ap.add_argument('--deploy', action='store_true', help='更新后立即部署')
    ap.add_argument('--dry-run', action='store_true', help='只显示计划')
    ap.add_argument('--no-backup', action='store_true', help='不备份 .vitepress 配置')
    ap.add_argument('--no-build', action='store_true', help='只重新生成，不构建')
    args = ap.parse_args()

    site = choose(args.site)
    if not site:
        return 2

    meta = _read_json(os.path.join(site, META_FILE))
    raw_source = args.source or meta.get('source')
    source = os.path.abspath(raw_source) if raw_source else ''
    title = meta.get('title') or site_index.site_info(site)['title']
    site_name = meta.get('name') or _read_json(
        os.path.join(site, 'package.json')).get('name')
    base = meta.get('base') or _config_base(site)

    if not source or not os.path.isdir(source):
        print(f'源目录不可用：{source or "（未记录）"}\n'
              f'请用 --source <md目录> 指定后重试', file=sys.stderr)
        print(json.dumps({'action': 'need_source', 'site': site,
                          'title': title}, ensure_ascii=False, indent=2))
        return 3

    print(f'站点    {site}')
    print(f'源目录  {source}')
    print(f'标题    {title}')

    if args.dry_run:
        print('计划：备份配置 → 重新生成 → '
              + ('构建 → ' if not args.no_build else '')
              + ('部署' if args.deploy else '（不部署）'))
        return 0

    # 1. 备份 .vitepress（config 与主题一旦被重新生成就无法手工恢复）
    if not args.no_backup:
        src_vp = os.path.join(site, 'docs', '.vitepress')
        if os.path.isdir(src_vp):
            stamp = datetime.datetime.now().strftime('%Y%m%d-%H%M%S')
            dst_vp = os.path.join(site, '.backup', f'vitepress-{stamp}')
            os.makedirs(os.path.dirname(dst_vp), exist_ok=True)
            shutil.copytree(src_vp, dst_vp)
            print(f'  已备份配置 → {dst_vp}')

    # 2. 原地重新生成（保留部署配置与依赖）
    script = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'init.py')
    cmd = [sys.executable, script, source, '--out', site, '--force',
           '--title', title, '--base', base]
    if site_name:
        cmd += ['--name', site_name]
    if run(cmd, os.path.dirname(site)) != 0:
        print('重新生成失败', file=sys.stderr)
        return 1

    if args.no_build:
        return 0

    # 3. 构建
    npm = shutil.which('npm')
    if not npm:
        print('未找到 npm，请先安装 Node.js 18+ 再构建', file=sys.stderr)
        return 1
    if not os.path.isdir(os.path.join(site, 'node_modules')):
        if run([npm, 'install'], site) != 0:
            print('依赖安装失败', file=sys.stderr)
            return 1
    if run([npm, 'run', 'build'], site) != 0:
        print('构建失败', file=sys.stderr)
        return 1

    # 4. 可选部署
    if args.deploy:
        deploy = os.path.join(site, 'deploy.sh')
        if not os.path.isfile(deploy):
            print('站点内没有 deploy.sh，无法部署', file=sys.stderr)
            return 1
        if run(['./deploy.sh'], site) != 0:
            print('部署失败', file=sys.stderr)
            return 1

    print(f'\n更新完成：{site}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
