#!/usr/bin/env bash
# ============================================================
# md2website 安装脚本
#
# 用法：
#   ./install.sh                 安装到 ~/.workbuddy/skills/md2website
#   ./install.sh --dir <路径>     安装到指定目录
#   ./install.sh --uninstall     卸载
#   ./install.sh --check         只检查环境，不安装
# ============================================================
set -euo pipefail

NAME="md2website"
SRC_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEFAULT_DIR="$HOME/.workbuddy/skills/$NAME"
TARGET_DIR="$DEFAULT_DIR"
MODE="install"
UNINSTALL_DIR_GIVEN=""

C_RESET=$'\033[0m'; C_INFO=$'\033[36m'; C_OK=$'\033[32m'; C_WARN=$'\033[33m'; C_ERR=$'\033[31m'; C_B=$'\033[1m'
info() { printf '%s==>%s %s\n' "$C_INFO" "$C_RESET" "$*"; }
ok()   { printf '%s  ✓%s %s\n' "$C_OK" "$C_RESET" "$*"; }
warn() { printf '%s  !%s %s\n' "$C_WARN" "$C_RESET" "$*"; }
die()  { printf '%s  ✗%s %s\n' "$C_ERR" "$C_RESET" "$*" >&2; exit 1; }

while [ $# -gt 0 ]; do
  case "$1" in
    --dir) [ $# -ge 2 ] || die "--dir 需要跟路径"; TARGET_DIR="$2"; UNINSTALL_DIR_GIVEN="true"; shift ;;
    --dir=*) TARGET_DIR="${1#*=}"; UNINSTALL_DIR_GIVEN="true" ;;
    --uninstall) MODE="uninstall" ;;
    --check) MODE="check" ;;
    -h|--help)
      sed -n '2,12p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
      exit 0 ;;
    *) die "未知参数: $1（--help 查看用法）" ;;
  esac
  shift
done

# ---------- 环境检查 ----------
check_env() {
  info "检查运行环境"
  local fail=0

  # Python 3.8+
  local py=""
  for cand in python3 python; do
    if command -v "$cand" >/dev/null 2>&1; then
      if "$cand" -c 'import sys; sys.exit(0 if sys.version_info >= (3,8) else 1)' 2>/dev/null; then
        py="$cand"; break
      fi
    fi
  done
  if [ -n "$py" ]; then
    ok "Python $("$py" -c 'import sys;print(".".join(map(str,sys.version_info[:3])))') ($py)"
  else
    printf '%s  ✗%s 需要 Python 3.8+\n' "$C_ERR" "$C_RESET"; fail=1
  fi

  # Node 18+
  if command -v node >/dev/null 2>&1; then
    local ver major
    ver="$(node --version | sed 's/^v//')"
    major="${ver%%.*}"
    if [ "${major:-0}" -ge 18 ] 2>/dev/null; then
      ok "Node $ver"
    else
      printf '%s  ✗%s Node 版本过低：$ver（需 18+）\n' "$C_ERR" "$C_RESET"; fail=1
    fi
  else
    printf '%s  ✗%s 未找到 Node.js（构建必需）\n' "$C_ERR" "$C_RESET"
    echo "     安装方式：https://nodejs.org 或 brew install node / nvm"
    fail=1
  fi

  # 打包工具
  for tool in tar scp ssh; do
    command -v "$tool" >/dev/null 2>&1 && ok "$tool 可用" || { warn "缺少 $tool（部署功能不可用）"; }
  done

  return $fail
}

case "$MODE" in
  check)
    check_env && { echo; ok "环境满足要求"; exit 0; } || { echo; die "环境不满足，请先补齐依赖"; }
    ;;

    uninstall)
    # 卸载目标以安装记录为准：<安装目录>/.installed-to
    # 若脚本所在目录带有该记录，说明当前目录就是安装副本，删它是对的。
    RECORD="$SRC_DIR/.installed-to"
    if [ -z "${UNINSTALL_DIR_GIVEN:-}" ]; then
      if [ -f "$RECORD" ]; then
        TARGET_DIR="$(tr -d '\r\n' < "$RECORD")"
      else
        die "当前目录不是已安装的 skill（缺少 .installed-to 记录）
   请显式指定目标：./install.sh --uninstall --dir <已安装目录>"
      fi
    fi

    # 安全校验：只允许删除看起来是本 skill 的目录
    [ -f "$TARGET_DIR/SKILL.md" ] && grep -q 'name: md2website' "$TARGET_DIR/SKILL.md" 2>/dev/null \
      || die "拒绝卸载：$TARGET_DIR 不像 md2website 安装目录（缺 SKILL.md 或标识不符）"
    case "$TARGET_DIR" in
      "$HOME"|"/"|"/usr"|"/tmp"|"") die "拒绝卸载：目标路径过于危险: $TARGET_DIR" ;;
    esac
    [ "$TARGET_DIR" = "${TARGET_DIR%/}" ] || die "目标路径异常: $TARGET_DIR"

    echo "即将删除: $TARGET_DIR"
    printf '确认请输入 yes: '
    read -r answer
    [ "$answer" = "yes" ] || { echo "已取消"; exit 0; }

    info "卸载 $TARGET_DIR"
    rm -rf "$TARGET_DIR"
    ok "已卸载"
    echo "注意：部署配置档（~/.workbuddy/deploy-profiles）未删除，如需清理请手动操作。"
    exit 0
    ;;

  install)
    check_env || echo
    echo

    [ -d "$SRC_DIR/scripts" ] || die "当前目录不像 skill 包（缺少 scripts/）"
    if [ "$SRC_DIR" = "$TARGET_DIR" ]; then
      die "源目录与目标目录相同，无需安装"
    fi

    info "安装到 $TARGET_DIR"
    mkdir -p "$(dirname "$TARGET_DIR")"
    rm -rf "$TARGET_DIR"
    mkdir -p "$TARGET_DIR"
    # 只复制必要文件，排除测试与临时产物
    for item in SKILL.md README.md README.en.md SETUP.md LICENSE install.sh scripts assets; do
      [ -e "$SRC_DIR/$item" ] && cp -R "$SRC_DIR/$item" "$TARGET_DIR/"
    done
    chmod +x "$TARGET_DIR/assets/deploy.sh" "$TARGET_DIR/assets/build.sh" "$TARGET_DIR/install.sh" 2>/dev/null || true
    chmod +x "$TARGET_DIR"/scripts/*.py 2>/dev/null || true
    ok "文件已复制"

    # 校验关键文件
    for f in SKILL.md scripts/init.py scripts/scan.py scripts/fix.py scripts/profile.py assets/deploy.sh assets/build.sh; do
      [ -f "$TARGET_DIR/$f" ] || die "安装不完整，缺少 $f"
    done
    ok "完整性校验通过"

    # 记录安装位置，供今后 --uninstall 使用（避免误删）
    printf '%s\n' "$TARGET_DIR" > "$TARGET_DIR/.installed-to"

    cat <<EOF

$(printf '%s安装完成%s' "$C_OK" "$C_RESET")

  位置    $TARGET_DIR
  自检    python3 "$TARGET_DIR/scripts/_env.py"

$(printf '%s最简用法（推荐）%s' "$C_B" "$C_RESET")

  把一键入口复制到你的 Markdown 目录，双击/执行即可：

    cp "$TARGET_DIR/assets/build.sh" ~/你的md目录/
    cd ~/你的md目录 && ./build.sh

  自动完成：扫描 → 生成站点 → 装依赖 → 构建 → 打开浏览器
  要交互选择：./build.sh --wizard

$(printf '%s命令行用法%s' "$C_B" "$C_RESET")

  # 扫描问题（只读）
  python3 "$TARGET_DIR/scripts/scan.py" <你的md目录>

  # 生成站点
  python3 "$TARGET_DIR/scripts/init.py" <你的md目录> --out ./my-doc-site --title "文档标题"

  # 构建预览
  cd ./my-doc-site && npm install && npm run dev

详细说明见 $TARGET_DIR/SETUP.md
EOF
    ;;
esac
