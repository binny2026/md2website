#!/usr/bin/env python3
"""Remote transaction helper; stdin carries a tar stream, argv carries JSON."""
import fcntl
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import sys
import tarfile
import tempfile
import uuid

PORTAL_ENTRIES = frozenset(('index.html', '404.html', 'assets', 'favicon.svg',
                            'modules.json.php', 'hashmap.json', 'site.json'))


def identifier(value):
    if not re.fullmatch(r'[a-zA-Z0-9][a-zA-Z0-9_-]{0,79}', value):
        raise ValueError('slug/release-id 仅允许字母数字、下划线、短横线，最长 80 字符')
    return value


def absolute(value):
    p = PurePosixPath(value)
    if not p.is_absolute() or '..' in p.parts or str(p) != value or len(p.parts) < 3:
        raise ValueError('目录必须为规范绝对路径，且至少两级，禁止 .. 和尾斜线')
    if any(ord(c) < 32 for c in value):
        raise ValueError('目录包含控制字符')
    return Path(value)


def validate(options):
    root = absolute(options['releases_root'])
    web = absolute(options['webroot'])
    if root == web or root in web.parents or web in root.parents:
        raise ValueError('releases-root 与 webroot 必须相互隔离')
    slug = identifier(options['slug'])
    identifier(options['release_id'])
    if options['portal']:
        if slug != 'portal':
            raise ValueError('门户 slug 必须为 portal')
    elif slug == 'portal' or slug in PORTAL_ENTRIES:
        raise ValueError('slug 与门户保留入口冲突')
    return root, web


def real_directory(path):
    if not path.is_dir() or path.resolve() != path:
        raise ValueError('目录必须已存在且路径不得经过软链')


def check_tree(path, portal):
    if not (path / 'index.html').is_file():
        raise ValueError('版本缺少 index.html')
    for item in path.rglob('*'):
        if item.is_symlink() or not (item.is_file() or item.is_dir()):
            raise ValueError('产物不允许软链或特殊文件')
    if portal:
        if not (path / 'modules.json.php').is_file():
            raise ValueError('门户版本缺少 modules.json.php')
        if any(p.name not in PORTAL_ENTRIES for p in path.iterdir()):
            raise ValueError('门户含不受控顶层产物')


def unpack(stream, stage):
    with tarfile.open(fileobj=stream, mode='r|gz') as archive:
        seen = set()
        for member in archive:
            rel = PurePosixPath(member.name)
            if (rel.is_absolute() or '..' in rel.parts or not rel.parts
                    or str(rel) != member.name or member.name in seen):
                raise ValueError('上传包路径非法或重复')
            seen.add(member.name)
            dest = stage.joinpath(*rel.parts)
            if member.isdir():
                dest.mkdir(parents=True, exist_ok=True)
            elif member.isfile():
                dest.parent.mkdir(parents=True, exist_ok=True)
                with archive.extractfile(member) as source, dest.open('xb') as target:
                    shutil.copyfileobj(source, target)
                dest.chmod(0o644)
            else:
                raise ValueError('上传包包含链接或特殊文件')


def check_current(link, versions):
    if os.path.lexists(link):
        if not link.is_symlink():
            raise ValueError('入口存在普通文件/目录，需独立迁移授权')
        current = link.resolve(strict=True)
        if current.parent != versions or not current.is_dir():
            raise ValueError('现有入口指向非受控版本')
        identifier(current.name)


def activate(web, versions, target, portal, slug):
    link = web / ('.portal-current' if portal else slug)
    check_current(link, versions)
    entries = sorted(p.name for p in target.iterdir()) if portal else []
    # Validate every reserved entry, including entries omitted by this version.
    for name in PORTAL_ENTRIES if portal else ():
        entry = web / name
        if os.path.lexists(entry) and (not entry.is_symlink()
                or os.readlink(entry) != '.portal-current/' + name):
            raise ValueError('门户入口冲突，拒绝覆盖：' + name)
    created = []
    temporary = web / ('.ci-switch-' + uuid.uuid4().hex)
    try:
        for name in entries:
            entry = web / name
            if not os.path.lexists(entry):
                entry.symlink_to('.portal-current/' + name)
                created.append(entry)
        temporary.symlink_to(target)
        os.replace(temporary, link)
    except BaseException:
        for entry in created:
            entry.unlink()
        raise
    finally:
        if temporary.is_symlink():
            temporary.unlink()


def execute(options, stream=None):
    root, web = validate(options)
    real_directory(root)
    real_directory(web)
    # One lock per webroot protects module/portal entry collisions too.
    fd = os.open(str(web / '.md2website-ci.lock'),
                 os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'w') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        versions = root / options['slug']
        versions.mkdir(exist_ok=True)
        real_directory(versions)
        target = versions / options['release_id']
        marker = versions / ('.' + options['release_id'] + '.ready')
        if options['action'] == 'publish':
            if os.path.lexists(target) or os.path.lexists(marker):
                raise ValueError('版本已存在；release-id 必须全新')
            stage = Path(tempfile.mkdtemp(prefix='.upload-', dir=str(versions)))
            try:
                unpack(stream, stage)
                check_tree(stage, options['portal'])
                stage.chmod(0o755)
                os.rename(stage, target)
                with marker.open('x') as ready:
                    ready.write('complete\n')
            finally:
                if stage.exists():
                    shutil.rmtree(stage)
        elif options['action'] != 'rollback':
            raise ValueError('未知远端操作')
        real_directory(target)
        if not marker.is_file() or marker.is_symlink() or marker.read_text() != 'complete\n':
            raise ValueError('目标不是完整上传的受控版本')
        check_tree(target, options['portal'])
        activate(web, versions, target, options['portal'], options['slug'])


def main():
    try:
        execute(json.loads(sys.argv[1]), sys.stdin.buffer)
    except (OSError, ValueError, tarfile.TarError):
        print('发布/回滚失败：请检查路径、版本、入口冲突或发布锁；原入口未主动覆盖。', file=sys.stderr)
        return 1
    print('版本入口切换完成')
    return 0


if __name__ == '__main__':
    sys.exit(main())
