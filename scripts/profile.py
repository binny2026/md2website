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
import json
import os
import re
import sys
from urllib.parse import urlsplit

PROFILE_DIR = os.path.expanduser('~/.workbuddy/deploy-profiles')
PROFILE_MARK = '.deploy-profile'
LOCAL_YML = '.deploy-local.yml'
HOSTS_FILE = os.path.join(os.path.expanduser('~'), '.md2website', 'hosts.json')

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
    ('PORTAL_PROJECT', '门户项目本地绝对路径（子模块挂门户时填写）', False),
    ('PORTAL_URL', '门户访问地址（子模块返回门户用，完整 URL）', False),
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


def load_hosts():
    """读取全局主机/门户记录 ~/.md2website/hosts.json，返回 hosts 列表。"""
    if not os.path.isfile(HOSTS_FILE):
        return []
    try:
        with open(HOSTS_FILE, encoding='utf-8') as f:
            data = json.load(f)
    except (OSError, ValueError):
        return []
    hosts = data.get('hosts') if isinstance(data, dict) else None
    return hosts if isinstance(hosts, list) else []


def save_hosts(hosts):
    """写入全局主机/门户记录，权限 600。"""
    d = os.path.dirname(HOSTS_FILE)
    os.makedirs(d, mode=0o700, exist_ok=True)
    try:
        os.chmod(d, 0o700)
    except OSError:
        pass
    with open(HOSTS_FILE, 'w', encoding='utf-8') as f:
        json.dump({'version': 1, 'hosts': hosts}, f, ensure_ascii=False, indent=2)
    try:
        os.chmod(HOSTS_FILE, 0o600)
    except OSError:
        pass


def record_host(host_info):
    """把主机 + 门户信息 upsert 进全局记录。
    host_info: {
        'host', 'port', 'user', 'password', 'ssh_key', 'note',
        'portals': [{'name', 'url', 'root_dir'}, ...]
    }
    主机按 host+port+user 定位（合并登录信息）；门户按 root_dir 定位（更新或追加）。
    """
    hosts = load_hosts()
    target = None
    for h in hosts:
        if (h.get('host') == host_info['host']
                and h.get('port') == host_info.get('port')
                and h.get('user') == host_info['user']):
            target = h
            break
    if target is None:
        target = {'host': host_info['host'], 'port': host_info.get('port', '22'),
                  'user': host_info['user'], 'password': '', 'ssh_key': '',
                  'note': '', 'portals': []}
        hosts.append(target)
    for key in ('port', 'password', 'ssh_key', 'note'):
        val = host_info.get(key, '')
        if val:
            target[key] = val
    portals = target.setdefault('portals', [])
    if not isinstance(portals, list):
        portals = []
        target['portals'] = portals
    for p in host_info.get('portals', []):
        found = None
        for existing in portals:
            if existing.get('root_dir') == p.get('root_dir'):
                found = existing
                break
        if found is not None:
            for key in ('name', 'url', 'root_dir'):
                if p.get(key):
                    found[key] = p[key]
        else:
            portals.append(p)
    save_hosts(hosts)
    return target


def list_portals():
    """扁平化列出所有门户候选（含主机登录信息），供选择落地。"""
    out = []
    for h in load_hosts():
        for p in h.get('portals', []):
            if not isinstance(p, dict):
                continue
            out.append({
                'host': h.get('host', ''),
                'port': h.get('port', '22'),
                'user': h.get('user', ''),
                'password': h.get('password', ''),
                'ssh_key': h.get('ssh_key', ''),
                'note': h.get('note', ''),
                'name': p.get('name', ''),
                'url': p.get('url', ''),
                'root_dir': p.get('root_dir', ''),
            })
    return out


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
    'PORTAL_PROJECT': 'portal_project', 'PORTAL_URL': 'portal_url',
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

    portal_url = input('门户访问地址（可选，例如 https://docs.kfxh.work，留空则不写入全局备选）: ').strip()

    data = {
        'HOST': host, 'USER': user, 'PASSWORD': password, 'REMOTE_DIR': remote_dir,
        'SSH_KEY': ssh_key, 'PORT': port, 'SITE_BASE': site_base,
        'PORTAL_URL': portal_url,
    }
    local = _write_local_yml(project, data, 'wizard 交互配置')
    print(f'已写入: {local}')

    # 填了门户访问地址则自动写入全局备选（主机+门户，upsert 去重）
    if portal_url:
        portal_name = urlsplit(portal_url).netloc or os.path.basename(remote_dir.rstrip('/'))
        record_host({
            'host': host, 'port': port, 'user': user,
            'password': password, 'ssh_key': ssh_key, 'note': '',
            'portals': [{'name': portal_name, 'url': portal_url, 'root_dir': remote_dir}],
        })
        print(f'已记录到全局备选: {HOSTS_FILE}')
    return 0


def _parse_yml(path):
    """解析 .deploy-local.yml，返回大写 key 的 dict。"""
    data = {}
    if not os.path.isfile(path):
        return data
    rev = {v: k for k, v in FIELD_YML.items()}
    for line in open(path, encoding='utf-8'):
        line = line.strip()
        if not line or line.startswith('#') or ':' not in line:
            continue
        k, v = line.split(':', 1)
        k = k.strip()
        v = strip_inline_comment(v.strip())
        if len(v) >= 2 and v[0] == v[-1] and v[0] in '"\'':
            v = v[1:-1]
        key = rev.get(k)
        if key:
            data[key] = v
    return data


def read_deploy_config(project):
    """读取站点部署配置（优先 .deploy-local.yml，其次 .deploy-profile 配置档），返回大写 key dict。"""
    data = _parse_yml(os.path.join(project, LOCAL_YML))
    if data.get('HOST') and data.get('REMOTE_DIR') and data.get('SITE_BASE'):
        return data
    mark = os.path.join(project, PROFILE_MARK)
    if os.path.isfile(mark):
        try:
            name = sanitize(open(mark, encoding='utf-8').read().strip())
        except OSError:
            name = ''
        if name:
            prof = read_profile(name)
            if prof:
                return prof
    return data


def _site_name(project):
    """取站点标识名：优先 package.json 的 name，否则目录名。"""
    pkg = os.path.join(project, 'package.json')
    if os.path.isfile(pkg):
        try:
            name = json.load(open(pkg, encoding='utf-8')).get('name')
            if name:
                return name
        except (OSError, ValueError):
            pass
    return re.sub(r'[^A-Za-z0-9-]+', '-', os.path.basename(project).lower()).strip('-') or 'module'


def _url_path(url):
    """从门户完整 URL 解析其 path 部分（确保以 / 开头结尾）。"""
    path = urlsplit(url or '').path or '/'
    if not path.endswith('/'):
        path += '/'
    return path


def _land_as_submodule(project, portal):
    """把选中的门户落地为站点子模块配置，写入 .deploy-local.yml。"""
    site_name = _site_name(project)
    root_dir = (portal.get('root_dir') or '').rstrip('/')
    base_path = _url_path(portal.get('url'))
    remote_dir = root_dir + '/' + site_name
    site_base = base_path + site_name + '/'
    data = {
        'HOST': portal.get('host', ''),
        'PORT': portal.get('port', '22'),
        'USER': portal.get('user', ''),
        'PASSWORD': portal.get('password', ''),
        'SSH_KEY': portal.get('ssh_key', ''),
        'REMOTE_DIR': remote_dir,
        'SITE_BASE': site_base,
        'PORTAL_URL': portal.get('url', ''),
    }
    local = _write_local_yml(project, data, '全局记录选择')
    return local, data


def cmd_hosts_list(args):
    """列出全局记录里的主机与门户。"""
    hosts = load_hosts()
    if args.json:
        print(json.dumps({'hosts': hosts}, ensure_ascii=False, indent=2))
        return 0
    if not hosts:
        print('暂无全局主机/门户记录')
        return 0
    for h in hosts:
        print(f'主机 {h.get("user")}@{h.get("host")}:{h.get("port")}'
              + (f'  （{h.get("note")}）' if h.get('note') else ''))
        for p in h.get('portals', []):
            print(f'  - {p.get("name")}  {p.get("url")}  → {p.get("root_dir")}')
    return 0


def cmd_hosts_rm(args):
    """删除全局记录里的主机或门户。"""
    hosts = load_hosts()
    target_host = None
    for h in hosts:
        if (h.get('host') == args.host
                and str(h.get('port', '22')) == str(args.port or '22')
                and h.get('user') == args.user):
            target_host = h
            break
    if target_host is None:
        print(f'未找到主机 {args.user}@{args.host}:{args.port or "22"}', file=sys.stderr)
        return 1
    if args.root_dir:
        portals = target_host.get('portals', [])
        kept = [p for p in portals if p.get('root_dir') != args.root_dir]
        if len(kept) == len(portals):
            print(f'未找到门户 root_dir={args.root_dir}', file=sys.stderr)
            return 1
        target_host['portals'] = kept
        print(f'已删除门户: {args.root_dir}')
    else:
        hosts.remove(target_host)
        print(f'已删除主机: {args.user}@{args.host}:{args.port or "22"}')
    save_hosts(hosts)
    return 0


def cmd_choose(args):
    """从全局记录选择一个门户，落地为当前站点的子模块部署配置。"""
    project = os.path.abspath(args.project)
    if not os.path.isdir(project):
        print(f'目录不存在: {project}', file=sys.stderr)
        return 1

    portals = list_portals()
    if not portals:
        if not sys.stdin.isatty():
            print(json.dumps({'action': 'no_hosts'}, ensure_ascii=False))
        return 3

    # 非交互且未指定 --index：输出候选 JSON 供 Agent 决策
    if args.index is None and not sys.stdin.isatty():
        print(json.dumps({'action': 'choose_portal', 'portals': portals},
                         ensure_ascii=False, indent=2))
        return 2

    idx = args.index
    if idx is None:
        for i, p in enumerate(portals, 1):
            print(f'{i}) {p["name"]}  {p["url"]}')
            print(f'   {p["user"]}@{p["host"]}:{p["port"]}  → {p["root_dir"]}'
                  + (f'  （{p["note"]}）' if p.get('note') else ''))
        while True:
            try:
                raw = input(f'选择要挂载的门户 [1-{len(portals)}，q 取消]: ').strip()
            except (EOFError, KeyboardInterrupt):
                print()
                return 1
            if raw.lower() in ('q', 'quit', 'exit'):
                return 1
            if raw.isdigit() and 1 <= int(raw) <= len(portals):
                idx = int(raw)
                break
            print(f'  输入无效，请填 1-{len(portals)}')

    if not (isinstance(idx, int) and 1 <= idx <= len(portals)):
        print(f'无效的门户编号: {idx}', file=sys.stderr)
        return 1
    portal = portals[idx - 1]
    local, data = _land_as_submodule(project, portal)
    print(f'已选择门户: {portal["name"]}  {portal["url"]}')
    print(f'  已写入: {local}')
    print(f'  REMOTE_DIR = {data["REMOTE_DIR"]}')
    print(f'  SITE_BASE  = {data["SITE_BASE"]}')
    print(f'  PORTAL_URL = {data["PORTAL_URL"]}')
    return 0


def cmd_submodule(args):
    """交互式把当前站点挂载为门户子模块：选门户 + 子目录名，自动推导 REMOTE_DIR/SITE_BASE/PORTAL_PROJECT。"""
    project = os.path.abspath(args.project)
    if not os.path.isdir(project):
        print(f'目录不存在: {project}', file=sys.stderr)
        return 1

    print('把当前站点挂载为门户子模块（自动推导部署目录与 base）')

    portal = input('门户项目本地绝对路径（必填）: ').strip()
    if not portal:
        print('未输入门户项目路径，已取消', file=sys.stderr)
        return 1
    portal = os.path.abspath(os.path.expanduser(portal))
    if not os.path.isdir(portal):
        print(f'门户项目目录不存在: {portal}', file=sys.stderr)
        return 1

    pconf = read_deploy_config(portal)
    if not (pconf.get('HOST') and pconf.get('REMOTE_DIR') and pconf.get('SITE_BASE')):
        print(f'门户项目缺少部署配置（需先配置 HOST/REMOTE_DIR/SITE_BASE）: {portal}', file=sys.stderr)
        print('请先在门户项目执行: python3 profile.py wizard --project "<门户>"', file=sys.stderr)
        return 1

    default_name = None
    pkg = os.path.join(project, 'package.json')
    if os.path.isfile(pkg):
        try:
            default_name = json.load(open(pkg, encoding='utf-8')).get('name')
        except (OSError, ValueError):
            default_name = None
    if not default_name:
        default_name = re.sub(r'[^A-Za-z0-9-]+', '-',
                              os.path.basename(project).lower()).strip('-') or 'module'

    sub = input(f'子目录名（默认 {default_name}）: ').strip() or default_name
    sub = sub.strip('/')
    if not sub:
        print('子目录名不能为空，已取消', file=sys.stderr)
        return 1

    site_base = pconf['SITE_BASE']
    if not site_base.endswith('/'):
        site_base += '/'
    remote_dir = pconf['REMOTE_DIR'].rstrip('/') + '/' + sub
    site_base = site_base + sub + '/'

    data = {
        'HOST': pconf.get('HOST', ''),
        'PORT': pconf.get('PORT', '22'),
        'USER': pconf.get('USER', ''),
        'PASSWORD': pconf.get('PASSWORD', ''),
        'SSH_KEY': pconf.get('SSH_KEY', ''),
        'REMOTE_DIR': remote_dir,
        'SITE_BASE': site_base,
        'PORTAL_PROJECT': portal,
    }
    local = _write_local_yml(project, data, 'submodule 交互配置')
    print(f'已写入: {local}')
    print(f'  REMOTE_DIR     = {remote_dir}')
    print(f'  SITE_BASE      = {site_base}')
    print(f'  PORTAL_PROJECT = {portal}')
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
    p = sub.add_parser('submodule')
    p.add_argument('--project', required=True)
    p = sub.add_parser('hosts', help='列出全局主机/门户记录')
    p.add_argument('--json', action='store_true', help='输出 JSON')
    p.add_argument('--rm', action='store_true', help='删除（需 --host --user，可选 --port --root_dir）')
    p.add_argument('--host')
    p.add_argument('--port')
    p.add_argument('--user')
    p.add_argument('--root_dir')
    p = sub.add_parser('choose', help='从全局记录选择门户落地为子模块')
    p.add_argument('--project', required=True)
    p.add_argument('--index', type=int, default=None, help='直接指定门户编号（1 起）')

    args = ap.parse_args()
    return {
        'path': cmd_path, 'show': cmd_show, 'check': cmd_check,
        'set': cmd_set, 'list': cmd_list, 'bind': cmd_bind, 'cache': cmd_cache,
        'wizard': cmd_wizard, 'submodule': cmd_submodule,
        'hosts': (lambda a: cmd_hosts_rm(a) if a.rm else cmd_hosts_list(a)),
        'choose': cmd_choose,
    }[args.cmd](args)


if __name__ == '__main__':
    sys.exit(main())
