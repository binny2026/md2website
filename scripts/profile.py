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
LOCAL_YML = '.deploy-local.yml'

# 字段定义：(键, 说明, 是否必填)
FIELDS = [
    ('HOST', '服务器主机（域名或 IP）', True),
    ('PORT', 'SSH 端口', True),
    ('USER', '登录账号', True),
    ('REMOTE_DIR', '远程部署目录（绝对路径）', True),
    ('SSH_KEY', 'SSH 私钥路径', False),
    ('PASSWORD', '登录密码（留空则用 SSH 密钥）', False),
    ('SITE_BASE', '站点根路径（/ 或 /子目录/）', True),
    ('CLEAN_MODE', '清理方式 manifest|none|all', False),
    ('BUILD_BEFORE_DEPLOY', '部署前是否构建 true|false', False),
    ('REMOTE_TMP', '远程临时目录', False),
    ('DIST_NAME', '产物文件夹名（上传时）', False),
    ('UPLOAD_WITH_DIR', '是否带文件夹一起上传 true|false', False),
]

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


def strip_inline_comment(v):
    """去掉行尾注释：仅当 # 前有空白时生效，避免密码里的 # 被误截断"""
    if v[:1] in ('"', "'"):
        end = v.find(v[0], 1)
        if end != -1:
            return v[:end + 1]
    for i, ch in enumerate(v):
        if ch == '#' and i > 0 and v[i - 1].isspace():
            return v[:i].rstrip()
    return v


def read_profile(name):
    """解析 KEY=VALUE，# 独占一行为注释，行尾 # 注释会被剥离。不执行任何 shell 代码。"""
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
            v = strip_inline_comment(v.strip())
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
        '# 由 md2website skill 生成，权限 600，切勿提交到仓库',
        '# ============================================================',
        '',
    ]
    for key, desc, _ in FIELDS:
        if key not in values:
            continue
        lines.append(f'# {desc}')
        lines.append(f'{key}="{values[key]}"')
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
        print(f'  {k:<20} {data.get(k, "<未设置>")}')
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


FIELD_YML = {
    'HOST': 'host', 'PORT': 'port', 'USER': 'user', 'PASSWORD': 'password',
    'REMOTE_DIR': 'remote_dir', 'SSH_KEY': 'ssh_key', 'SITE_BASE': 'site_base',
    'CLEAN_MODE': 'clean_mode', 'BUILD_BEFORE_DEPLOY': 'build_before_deploy',
    'REMOTE_TMP': 'remote_tmp', 'DIST_NAME': 'dist_name', 'UPLOAD_WITH_DIR': 'upload_with_dir',
}


def _write_local_yml(project, data, source):
    """把配置写为站点本地 yml（.deploy-local.yml，权限 600，不上传服务器）"""
    lines = [
        f'# 站点本地部署配置（来源：{source}，权限 600，不上传服务器，勿提交 git）',
        '# 由 md2website skill 生成',
    ]
    for key, _desc, _req in FIELDS:
        val = data.get(key, '')
        if val == '':
            continue
        yml_key = FIELD_YML.get(key, key.lower())
        lines.append(f'{yml_key}: {val}')
    local = os.path.join(project, LOCAL_YML)
    with open(local, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines) + '\n')
    try:
        os.chmod(local, 0o600)
    except OSError:
        pass
    return local


def cmd_cache(args):
    """把配置档内容缓存到站点目录的 .deploy-local.yml（不上传服务器）"""
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
    local = _write_local_yml(project, data, f'配置档 {name}')
    print(f'已缓存到: {local}')
    return 0


def cmd_wizard(args):
    """交互式引导配置，写入站点本地 .deploy-local.yml（无预置默认值）"""
    project = os.path.abspath(args.project)
    if not os.path.isdir(project):
        print(f'目录不存在: {project}', file=sys.stderr)
        return 1

    print('开始配置站点部署信息（没有预置默认值，必填项不能留空）')

    host = input('服务器主机（域名或 IP，必填）: ').strip()
    if not host:
        print('未输入主机，已取消', file=sys.stderr)
        return 1

    user = input('登录账号（必填）: ').strip()
    if not user:
        print('未输入登录账号，已取消', file=sys.stderr)
        return 1

    password = input('登录密码（密码登录填写，留空则用 SSH 密钥）: ').strip()
    ssh_key = input('SSH 私钥路径（密钥登录填写，密码登录留空）: ').strip()
    if not password and not ssh_key:
        print('登录密码与 SSH 私钥至少填写一项，已取消', file=sys.stderr)
        return 1
    if ssh_key.startswith('~/'):
        ssh_key = '$HOME/' + ssh_key[2:]

    remote_dir = input('远程部署目录（绝对路径，必填）: ').strip()
    if not remote_dir:
        print('未输入远程目录，已取消', file=sys.stderr)
        return 1
    if not remote_dir.startswith('/'):
        print('远程目录必须是绝对路径，已取消', file=sys.stderr)
        return 1

    port = input('SSH 端口（必填，例如 22）: ').strip()
    if not port.isdigit() or not 1 <= int(port) <= 65535:
        print('SSH 端口必须是 1-65535 的数字，已取消', file=sys.stderr)
        return 1

    site_base = input('站点根路径（必填，例如 / 或 /docs/）: ').strip()
    if not site_base.startswith('/'):
        print('站点根路径必须以 / 开头，已取消', file=sys.stderr)
        return 1
    if not site_base.endswith('/'):
        site_base += '/'

    data = {
        'HOST': host, 'USER': user, 'PASSWORD': password, 'REMOTE_DIR': remote_dir,
        'SSH_KEY': ssh_key, 'PORT': port, 'SITE_BASE': site_base,
    }
    local = _write_local_yml(project, data, 'wizard 交互配置')
    print(f'已写入: {local}')
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
    p = sub.add_parser('wizard')
    p.add_argument('--project', required=True)

    args = ap.parse_args()
    return {
        'path': cmd_path, 'show': cmd_show, 'check': cmd_check,
        'set': cmd_set, 'list': cmd_list, 'bind': cmd_bind, 'cache': cmd_cache,
        'wizard': cmd_wizard,
    }[args.cmd](args)


if __name__ == '__main__':
    sys.exit(main())
