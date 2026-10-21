#!/usr/bin/env python3
"""
部署配置档管理：多项目各自一份配置，统一存放，不进 git。

用法:
    python3 profile.py path   --name <项目名>
    python3 profile.py show   --name <项目名>
    python3 profile.py check  --name <项目名>        # 检查缺项，退出码 2 表示缺配置
    python3 profile.py set    --name <项目名> KEY=VALUE [KEY=VALUE ...]
    python3 profile.py list

配置目录:
    ~/.workbuddy/deploy-profiles/<项目名>.conf

项目会生成 .deploy-profile 文件记录自己用哪个配置档（可安全提交）。
"""
import argparse
import os
import re
import sys

PROFILE_DIR = os.path.expanduser('~/.workbuddy/deploy-profiles')
PROFILE_MARK = '.deploy-profile'
LOCAL_CONF = '.deploy-local.conf'

# 字段定义：(键, 说明, 是否必填)
FIELDS = [
    ('HOST', '服务器主机（域名或 IP）', True),
    ('PORT', 'SSH 端口', False),
    ('USER', '登录账号', True),
    ('REMOTE_DIR', '远程部署目录（绝对路径）', True),
    ('SSH_KEY', 'SSH 私钥路径', False),
    ('SITE_BASE', '站点根路径（/ 或 /子目录/）', False),
    ('CLEAN_MODE', '清理方式 manifest|none|all', False),
    ('BUILD_BEFORE_DEPLOY', '部署前是否构建 true|false', False),
    ('REMOTE_TMP', '远程临时目录', False),
    ('DIST_NAME', '产物文件夹名（上传时）', False),
    ('UPLOAD_WITH_DIR', '是否带文件夹一起上传 true|false', False),
]

DEFAULTS = {
    'PORT': '22',
    'USER': 'root',
    'SSH_KEY': '$HOME/.ssh/id_rsa',
    'SITE_BASE': '/',
    'CLEAN_MODE': 'manifest',
    'BUILD_BEFORE_DEPLOY': 'true',
    'REMOTE_TMP': '/tmp',
    'DIST_NAME': 'dist',
    'UPLOAD_WITH_DIR': 'false',
}

REQUIRED = [k for k, _, req in FIELDS if req]
DESCRIBE = {k: d for k, d, _ in FIELDS}


def sanitize(name):
    s = re.sub(r'[^A-Za-z0-9._-]+', '-', name).strip('-')
    return s or 'default'


def profile_path(name):
    return os.path.join(PROFILE_DIR, sanitize(name) + '.conf')


def ensure_dir():
    os.makedirs(PROFILE_DIR, mode=0o700, exist_ok=True)
    try:
        os.chmod(PROFILE_DIR, 0o700)
    except OSError:
        pass


def read_profile(name):
    """解析 KEY=VALUE，# 开头为注释。不执行任何 shell 代码。"""
    path = profile_path(name)
    data = {}
    if not os.path.isfile(path):
        return data
    with open(path, encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            if '=' not in line:
                continue
            k, v = line.split('=', 1)
            k = k.strip()
            v = v.strip()
            if len(v) >= 2 and v[0] == v[-1] and v[0] in '"\'':
                v = v[1:-1]
            data[k] = v
    return data


def write_profile(name, values):
    ensure_dir()
    path = profile_path(name)
    lines = [
        '# ============================================================',
        f'# 部署配置档：{sanitize(name)}',
        '# 由 md-to-vitepress skill 生成，权限 600，切勿提交到仓库',
        '# ============================================================',
        '',
    ]
    for key, desc, _ in FIELDS:
        val = values.get(key, DEFAULTS.get(key, ''))
        if key in values or key in DEFAULTS:
            lines.append(f'# {desc}')
            lines.append(f'{key}="{val}"')
            lines.append('')
    with open(path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines))
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass
    return path


def write_marker(project_dir, name):
    mark = os.path.join(project_dir, PROFILE_MARK)
    with open(mark, 'w', encoding='utf-8') as f:
        f.write(sanitize(name) + '\n')
    return mark


def resolve_name(args, project_dir):
    if args.name:
        return sanitize(args.name)
    mark = os.path.join(project_dir, PROFILE_MARK)
    if os.path.isfile(mark):
        return sanitize(open(mark, encoding='utf-8').read().strip())
    return None


def missing_of(values):
    out = []
    for k in REQUIRED:
        v = values.get(k, '')
        if not v or v.strip() == '':
            out.append(k)
    return out


def cmd_path(args):
    ensure_dir()
    name = sanitize(args.name or 'default')
    print(profile_path(name))
    return 0


def cmd_show(args):
    name = resolve_name(args, os.getcwd())
    if not name:
        print('该项目未绑定配置档（缺少 .deploy-profile）', file=sys.stderr)
        return 1
    data = read_profile(name)
    print(f'配置档: {name}')
    print(f'路径:   {profile_path(name)}')
    if not data:
        print('（尚未创建）')
        return 1
    for k, desc, _ in FIELDS:
        print(f'  {k:<20} {data.get(k, DEFAULTS.get(k, "<未设置>"))}')
    return 0


def cmd_check(args):
    name = resolve_name(args, os.getcwd())
    if not name:
        print('UNBOUND')
        return 2
    data = read_profile(name)
    if not data:
        print('MISSING')
        for k in REQUIRED:
            print(f'  {k}: {DESCRIBE[k]}')
        return 2
    miss = missing_of(data)
    if miss:
        print('INCOMPLETE')
        for k in miss:
            print(f'  {k}: {DESCRIBE[k]}')
        return 2
    print('OK')
    return 0


def cmd_set(args):
    name = sanitize(args.name or 'default')
    data = read_profile(name)
    for pair in args.pairs:
        if '=' not in pair:
            print(f'格式错误（应为 KEY=VALUE）: {pair}', file=sys.stderr)
            return 1
        k, v = pair.split('=', 1)
        k = k.strip()
        if k not in DESCRIBE:
            print(f'未知字段: {k}\n可用字段: {", ".join(DESCRIBE)}', file=sys.stderr)
            return 1
        data[k] = v.strip()
    # 补默认值
    for k, v in DEFAULTS.items():
        data.setdefault(k, v)
    path = write_profile(name, data)
    print(f'已写入: {path}')
    miss = missing_of(data)
    if miss:
        print('仍缺必填项: ' + ', '.join(miss))
        return 2
    return 0


def cmd_list(args):
    ensure_dir()
    files = sorted(f for f in os.listdir(PROFILE_DIR) if f.endswith('.conf'))
    if not files:
        print('暂无配置档')
        return 0
    for f in files:
        name = f[:-5]
        data = read_profile(name)
        miss = missing_of(data)
        state = '完整' if not miss else '缺 ' + ','.join(miss)
        print(f'{name:<30} {data.get("USER","?")}@{data.get("HOST","?")} '
              f'{data.get("REMOTE_DIR","?")}  [{state}]')
    return 0


def cmd_bind(args):
    """把项目绑定到指定配置档"""
    project = os.path.abspath(args.project)
    if not os.path.isdir(project):
        print(f'目录不存在: {project}', file=sys.stderr)
        return 1
    name = sanitize(args.name)
    if not os.path.isfile(profile_path(name)):
        print(f'提示：配置档 {name} 尚不存在，请随后用 set 创建', file=sys.stderr)
    mark = write_marker(project, name)
    print(f'已绑定: {mark} → {name}')
    return 0


def cmd_cache(args):
    """把配置档内容缓存到站点目录的 .deploy-local.conf（不上传服务器）"""
    project = os.path.abspath(args.project)
    if not os.path.isdir(project):
        print(f'目录不存在: {project}', file=sys.stderr)
        return 1
    name = sanitize(args.name) if args.name else None
    if not name:
        mark = os.path.join(project, PROFILE_MARK)
        if os.path.isfile(mark):
            name = sanitize(open(mark, encoding='utf-8').read().strip())
    if not name:
        print('未指定 --name 且站点未绑定配置档，无法缓存', file=sys.stderr)
        return 1
    data = read_profile(name)
    if not data:
        print(f'配置档 {name} 不存在或为空，请先 profile.py set --name {name} ...', file=sys.stderr)
        return 1
    lines = [
        f'# 站点本地部署配置（缓存自配置档 {name}，权限 600，不上传服务器）',
        '# 由 md-to-vitepress skill 的 profile.py cache 生成',
    ]
    for key, desc, _ in FIELDS:
        val = data.get(key, DEFAULTS.get(key, ''))
        lines.append(f'{key}="{val}"')
    local = os.path.join(project, LOCAL_CONF)
    with open(local, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines) + '\n')
    try:
        os.chmod(local, 0o600)
    except OSError:
        pass
    print(f'已缓存到: {local}')
    return 0


def main():
    ap = argparse.ArgumentParser(description='部署配置档管理')
    sub = ap.add_subparsers(dest='cmd', required=True)

    p = sub.add_parser('path'); p.add_argument('--name')
    p = sub.add_parser('show'); p.add_argument('--name')
    p = sub.add_parser('check'); p.add_argument('--name')
    p = sub.add_parser('set'); p.add_argument('--name'); p.add_argument('pairs', nargs='+')
    sub.add_parser('list')
    p = sub.add_parser('bind')
    p.add_argument('--project', required=True)
    p.add_argument('--name', required=True)
    p = sub.add_parser('cache')
    p.add_argument('--project', required=True)
    p.add_argument('--name')

    args = ap.parse_args()
    return {
        'path': cmd_path, 'show': cmd_show, 'check': cmd_check,
        'set': cmd_set, 'list': cmd_list, 'bind': cmd_bind, 'cache': cmd_cache,
    }[args.cmd](args)


if __name__ == '__main__':
    sys.exit(main())
