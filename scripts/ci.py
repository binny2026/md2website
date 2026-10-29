#!/usr/bin/env python3
"""Isolated Linux/native CI build and versioned SSH publishing (Python 3.8+)."""
import argparse
import json
import os
from pathlib import Path
import re
import shlex
import subprocess
import sys
import tarfile
import tempfile

from ci_remote import absolute, check_tree, identifier, validate


SCRIPTS = Path(__file__).resolve().parent


def build(args):
    out = Path(args.out).absolute()
    if os.path.lexists(out):
        raise ValueError('--out 必须不存在')
    out = out.resolve()
    source = Path(args.source).resolve(strict=True) if args.source else None
    if args.portal == bool(source):
        raise ValueError('必须且只能指定 --source 或 --portal')
    if source and (not source.is_dir() or source == out or source in out.parents
                   or out in source.parents):
        raise ValueError('输出与源目录必须隔离，源必须为目录')
    identifier(args.name)
    if not re.fullmatch(r'/(?:[A-Za-z0-9_-]+/)*', args.base):
        raise ValueError('--base 必须为 / 或 /slug/ 形式')
    if args.portal:
        if not args.portal_scan_root:
            raise ValueError('门户需要 --portal-scan-root（服务器固定 webroot）')
        absolute(args.portal_scan_root)
    elif args.portal_scan_root:
        raise ValueError('--portal-scan-root 仅用于门户')
    # init.py uses raw template substitution; reject syntax-breaking values.
    for value in (args.title, args.subtitle):
        if any(c in value for c in ('\n', '\r', '\x00', "'", '"', '`', '\\')) or '${' in value:
            raise ValueError('标题/副标题不允许引号、反斜线、换行或模板插值')
    if args.portal_url and not re.fullmatch(r'https?://[^\s]+', args.portal_url):
        raise ValueError('--portal-url 必须为 HTTP(S) URL')
    out.mkdir(parents=True)
    home = out / '.ci-home'
    home.mkdir()
    project = out / 'project'
    env = dict(os.environ, HOME=str(home), VP_BASE=args.base,
               PORTAL_URL=args.portal_url or '', npm_config_cache=str(out / '.npm-cache'))
    command = [sys.executable, str(SCRIPTS / 'init.py')]
    command += ['--portal'] if args.portal else [str(source)]
    command += ['--out', str(project), '--name', args.name, '--title', args.title,
                '--subtitle', args.subtitle, '--base', args.base]
    subprocess.run(command, check=True, env=env)
    config = project / 'docs/.vitepress/config.mjs'
    text = config.read_text(encoding='utf-8')
    # Enforce dead-link checking only in this generated CI project.
    text = re.sub(r'ignoreDeadLinks\s*:\s*true', 'ignoreDeadLinks: false', text)
    config.write_text(text, encoding='utf-8')
    if args.portal:
        php = project / 'docs/public/modules.json.php'
        text = php.read_text(encoding='utf-8')
        old = "$base = rtrim(__DIR__, '/');"
        if text.count(old) != 1:
            raise ValueError('门户 PHP 模板发生变化，无法安全替换扫描根')
        quoted = "'" + args.portal_scan_root.replace('\\', '\\\\').replace("'", "\\'") + "'"
        php.write_text(text.replace(old, '$base = ' + quoted + ';'), encoding='utf-8')
    subprocess.run(['npm', 'install', '--no-audit', '--no-fund'], cwd=project, env=env, check=True)
    subprocess.run(['npm', 'run', 'build'], cwd=project, env=env, check=True)
    dist = project / 'docs/.vitepress/dist'
    check_tree(dist, args.portal)
    (dist / 'site.json').write_text(json.dumps({
        'title': args.title, 'description': args.subtitle,
        'name': args.name, 'base': args.base,
        'role': 'portal' if args.portal else 'site',
    }, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'project': str(project), 'dist': str(dist)}, ensure_ascii=False))


def remote(args):
    options = {key: getattr(args, key) for key in
               ('releases_root', 'webroot', 'slug', 'release_id', 'portal')}
    options['action'] = args.command
    validate(options)
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9.-]*', args.host):
        raise ValueError('--host 只支持 DNS 名称或 IPv4')
    if not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_-]*', args.user):
        raise ValueError('--user 非法')
    if not 1 <= args.port <= 65535:
        raise ValueError('--port 超出范围')
    key = Path(args.ssh_key).resolve(strict=True)
    known_hosts = Path(args.known_hosts).resolve(strict=True)
    if not key.is_file() or not known_hosts.is_file():
        raise ValueError('SSH key 与 known_hosts 必须是调用方提供的文件')
    command = ['ssh', '-F', '/dev/null', '-p', str(args.port), '-i', str(key),
               '-o', 'StrictHostKeyChecking=yes', '-o', 'BatchMode=yes',
               '-o', 'IdentitiesOnly=yes', '-o', 'ConnectTimeout=15',
               '-o', 'UserKnownHostsFile=' + '"' + str(known_hosts).replace('"', '\\"') + '"',
               args.user + '@' + args.host]
    # OpenSSH passes a command string to a remote shell: quote *each* argument.
    helper = (SCRIPTS / 'ci_remote.py').read_text(encoding='utf-8')
    command.append(' '.join(shlex.quote(part) for part in
                            ['python3', '-c', helper, json.dumps(options)]))
    if args.command == 'rollback':
        subprocess.run(command, stdin=subprocess.DEVNULL, check=True)
        return
    dist = Path(args.dist).resolve(strict=True)
    check_tree(dist, args.portal)
    with tempfile.TemporaryFile() as package:
        with tarfile.open(fileobj=package, mode='w:gz') as archive:
            for item in sorted(dist.rglob('*')):
                archive.add(str(item), arcname=item.relative_to(dist).as_posix(), recursive=False)
        package.seek(0)
        subprocess.run(command, stdin=package, check=True)


def parser():
    ap = argparse.ArgumentParser(description=__doc__)
    commands = ap.add_subparsers(dest='command', required=True)
    b = commands.add_parser('build', help='创建全新隔离工作区（产物位于 out/project/docs/.vitepress/dist）')
    b.add_argument('--source')
    b.add_argument('--portal', action='store_true')
    for name in ('out', 'name', 'title', 'base'):
        b.add_argument('--' + name, required=True)
    b.add_argument('--subtitle', default='')
    b.add_argument('--portal-url', default='')
    b.add_argument('--portal-scan-root')
    for action in ('publish', 'rollback'):
        p = commands.add_parser(action)
        for name in ('host', 'user', 'ssh-key', 'known-hosts', 'releases-root',
                     'webroot', 'slug', 'release-id'):
            p.add_argument('--' + name, required=True)
        p.add_argument('--port', type=int, default=22)
        p.add_argument('--portal', action='store_true')
        if action == 'publish':
            p.add_argument('--dist', required=True)
    return ap


def main():
    args = parser().parse_args()
    try:
        build(args) if args.command == 'build' else remote(args)
    except subprocess.CalledProcessError:
        # Never format CalledProcessError: its command may contain caller data.
        print('CI 子进程失败，未继续执行后续步骤。', file=sys.stderr)
        return 1
    except (OSError, ValueError, tarfile.TarError) as exc:
        print('CI 失败：' + str(exc), file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
