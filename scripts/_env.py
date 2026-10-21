#!/usr/bin/env python3
"""
环境探测与依赖管理，供 md-to-vitepress 各脚本共用。

不写死任何解释器路径，全部运行时探测，因此可在任意机器上运行。
"""
import os
import shutil
import subprocess
import sys

MIN_NODE_MAJOR = 18          # VitePress 1.x 要求
PKG_NAME = 'vitepress'
PKG_VERSION = '^1.6.4'


# ---------------------------------------------------------------- Python

def python_exe():
    """当前脚本所用的解释器即为可用 Python"""
    return sys.executable


def python_cmd():
    """给用户复制用的简写入法"""
    return 'python3' if sys.platform != 'win32' else 'python'


# ---------------------------------------------------------------- Node

def find_node():
    """依次尝试：PATH → nvm → homebrew → 系统常见位置"""
    exe = shutil.which('node')
    if exe:
        return exe

    candidates = [
        os.path.expanduser('~/.nvm/versions/node/*/bin/node'),
        '/opt/homebrew/bin/node',
        '/usr/local/bin/node',
        '/usr/bin/node',
    ]
    import glob
    for pattern in candidates:
        for path in sorted(glob.glob(pattern), reverse=True):
            if os.path.isfile(path) and os.access(path, os.X_OK):
                return path
    return None


def node_version(node):
    try:
        out = subprocess.run([node, '--version'], capture_output=True,
                             text=True, timeout=10).stdout.strip()
        return out.lstrip('v')
    except Exception:
        return None


def check_node():
    """返回 (ok, node路径, 版本, 错误信息)"""
    node = find_node()
    if not node:
        return False, None, None, 'not_found'

    ver = node_version(node)
    if not ver:
        return False, node, None, 'broken'

    try:
        major = int(ver.split('.')[0])
    except ValueError:
        return False, node, ver, 'broken'

    if major < MIN_NODE_MAJOR:
        return False, node, ver, f'too_old ({ver} < {MIN_NODE_MAJOR})'

    return True, node, ver, None


def node_install_hint():
    """按平台给出安装建议"""
    system = sys.platform
    if system == 'darwin':
        return ('macOS 安装 Node.js：\n'
                '  brew install node            # 已有 Homebrew\n'
                '  或到 https://nodejs.org 下载 LTS 安装包\n'
                '  或用 nvm: https://github.com/nvm-sh/nvm')
    if system.startswith('linux'):
        return ('Linux 安装 Node.js：\n'
                '  curl -fsSL https://deb.nodesource.com/setup_lts.x | sudo -E bash -\n'
                '  sudo apt install -y nodejs\n'
                '  或使用 nvm: https://github.com/nvm-sh/nvm')
    if system == 'win32':
        return ('Windows 安装 Node.js：\n'
                '  到 https://nodejs.org 下载 LTS 安装包\n'
                '  推荐配合 Git Bash 或 WSL 运行本工具')
    return '请到 https://nodejs.org 安装 Node.js 18+'


def npx_path():
    return shutil.which('npx') or shutil.which('npx.cmd')


# ---------------------------------------------------------------- 依赖

def has_vitepress(project_dir):
    """检查项目内是否已装 vitepress"""
    local = os.path.join(project_dir, 'node_modules', PKG_NAME, 'package.json')
    return os.path.isfile(local)


def install_deps(project_dir, quiet=False):
    """在项目内执行 npm install，返回 (ok, message)"""
    npm = shutil.which('npm') or shutil.which('npm.cmd')
    if not npm:
        return False, '未找到 npm'

    pkg = os.path.join(project_dir, 'package.json')
    if not os.path.isfile(pkg):
        return False, f'缺少 package.json: {pkg}'

    if not quiet:
        print('  安装依赖（首次约 1-3 分钟）...')

    proc = subprocess.run([npm, 'install', '--no-audit', '--no-fund'],
                          cwd=project_dir, capture_output=True, text=True)
    if proc.returncode != 0:
        tail = (proc.stderr or proc.stdout or '').strip().splitlines()[-8:]
        return False, '\n'.join(tail)
    return True, 'ok'


def ensure_deps(project_dir, auto_install=True):
    """确保依赖就绪，返回 (ok, message)"""
    if has_vitepress(project_dir):
        return True, 'ready'
    if not auto_install:
        return False, 'missing'
    return install_deps(project_dir)


# ---------------------------------------------------------------- 输出

def describe():
    """一行环境摘要，便于排查"""
    ok_n, node, ver, err = check_node()
    parts = [f'python {sys.version.split()[0]} ({sys.executable})']
    if ok_n:
        parts.append(f'node {ver} ({node})')
    else:
        parts.append(f'node 不可用 [{err}]')
    return ' | '.join(parts)


if __name__ == '__main__':
    print('平台:', sys.platform)
    print('Python:', sys.version.split()[0], '→', python_exe())
    ok, node, ver, err = check_node()
    if ok:
        print('Node:', ver, '→', node)
        print('npx:', npx_path())
    else:
        print('Node 不可用:', err)
        print(node_install_hint())
    sys.exit(0 if ok else 1)
