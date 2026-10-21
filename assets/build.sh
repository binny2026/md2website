#!/usr/bin/env bash
# ============================================================
# 一键建站 · 双击即用
#
# 默认（零参数）：
#   放到 Markdown 目录里双击/执行，自动扫描 → 生成站点 → 装依赖 → 构建 → 打开浏览器
#
# 交互模式：
#   ./build.sh --wizard     逐项询问输出位置、站点标题、是否部署
#
# 其他：
#   ./build.sh --dir <md目录>   指定源目录
#   ./build.sh --no-open        构建完不自动打开浏览器
#   ./build.sh --skill <路径>   手动指定 skill 本体位置
# ============================================================
# HELP_END
set -euo pipefail

NAME="md-to-vitepress"
SCRIPT_PATH="${BASH_SOURCE[0]}"
while [ -L "$SCRIPT_PATH" ]; do
  LINK_DIR="$(cd -P "$(dirname "$SCRIPT_PATH")" && pwd)"
  SCRIPT_PATH="$(readlink "$SCRIPT_PATH")"
  case "$SCRIPT_PATH" in /*) ;; *) SCRIPT_PATH="$LINK_DIR/$SCRIPT_PATH" ;; esac
done
SCRIPT_DIR="$(cd -P "$(dirname "$SCRIPT_PATH")" && pwd)"

C_RESET=$'\033[0m'; C_INFO=$'\033[36m'; C_OK=$'\033[32m'; C_WARN=$'\033[33m'; C_ERR=$'\033[31m'; C_B=$'\033[1m'
info() { printf '%s==>%s %s\n' "$C_INFO" "$C_RESET" "$*"; }
ok()   { printf '%s  ✓%s %s\n' "$C_OK" "$C_RESET" "$*"; }
warn() { printf '%s  !%s %s\n' "$C_WARN" "$C_RESET" "$*"; }
die()  { printf '%s  ✗%s %s\n' "$C_ERR" "$C_RESET" "$*" >&2; exit 1; }

# ---------- 定位 skill ----------
# 脚本可能被复制到任意目录双击，需要找到真正含 scripts/ 的 skill 根
find_skill() {
  local d="$1"
  for _ in 1 2 3 4 5; do
    if [ -f "$d/scripts/init.py" ] && [ -f "$d/SKILL.md" ]; then
      echo "$d"; return 0
    fi
    d="$(cd "$d/.." 2>/dev/null && pwd)" || return 1
  done
  return 1
}
SKILL_DIR="$(find_skill "$SCRIPT_DIR" || true)"
if [ -z "$SKILL_DIR" ]; then
  for cand in "$HOME/.workbuddy/skills/$NAME" "$SCRIPT_DIR/../$NAME"; do
    [ -d "$cand" ] && [ -f "$cand/scripts/init.py" ] && { SKILL_DIR="$(cd "$cand" && pwd)"; break; }
  done
fi
[ -n "${SKILL_DIR:-}" ] || die "找不到 md-to-vitepress skill 本体（缺 scripts/init.py）
   请先运行 skill 目录下的 ./install.sh 安装，或用 --skill <路径> 指定"

PY=""
for cand in python3 python; do
  command -v "$cand" >/dev/null 2>&1 && { PY="$cand"; break; }
done
[ -n "$PY" ] || die "需要 Python 3.8+，请先安装：https://www.python.org/downloads/"

# ---------- 参数 ----------
SRC_DIR=""
OUT_DIR=""
TITLE=""
SUBTITLE=""
NAME=""
WIZARD="false"
DO_OPEN="true"
NO_BUILD="false"
while [ $# -gt 0 ]; do
  case "$1" in
    --wizard) WIZARD="true" ;;
    --dir) [ $# -ge 2 ] || die "--dir 需要跟路径"; SRC_DIR="$2"; shift ;;
    --dir=*) SRC_DIR="${1#*=}" ;;
    --out) [ $# -ge 2 ] || die "--out 需要跟路径"; OUT_DIR="$2"; shift ;;
    --out=*) OUT_DIR="${1#*=}" ;;
    --title) [ $# -ge 2 ] || die "--title 需要跟文字"; TITLE="$2"; shift ;;
    --title=*) TITLE="${1#*=}" ;;
    --subtitle) [ $# -ge 2 ] || die "--subtitle 需要跟文字"; SUBTITLE="$2"; shift ;;
    --name) [ $# -ge 2 ] || die "--name 需要跟文字"; NAME="$2"; shift ;;
    --name=*) NAME="${1#*=}" ;;
    --skill) [ $# -ge 2 ] || die "--skill 需要跟路径"; SKILL_DIR="$2"; shift ;;
    --no-open) DO_OPEN="false" ;;
    --no-build) NO_BUILD="true" ;;
    -h|--help)
      sed -n '/^# 一键建站/,/^# HELP_END/p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//' | sed '$d'
      exit 0 ;;
    *) die "未知参数: $1（--help 查看用法）" ;;
  esac
  shift
done

# ---------- 定位 Markdown 源目录 ----------
# 双击运行时当前目录不可靠，优先用脚本所在目录向上查找
locate_src() {
  local start="$1"
  [ -n "$start" ] || start="$SCRIPT_DIR"

  # 若本身就是 md 目录
  if [ -n "$(find "$start" -maxdepth 2 -name '*.md' -not -path '*/node_modules/*' -print -quit 2>/dev/null)" ]; then
    echo "$start"; return 0
  fi

  # 向上找
  local d="$start"
  for _ in 1 2 3; do
    d="$(cd "$d/.." 2>/dev/null && pwd)" || break
    if [ -n "$(find "$d" -maxdepth 2 -name '*.md' -not -path '*/node_modules/*' -not -path '*/.vitepress/*' -print -quit 2>/dev/null)" ]; then
      echo "$d"; return 0
    fi
  done
  return 1
}

if [ -n "$SRC_DIR" ]; then
  [ -d "$SRC_DIR" ] || die "源目录不存在: $SRC_DIR"
  SRC_DIR="$(cd "$SRC_DIR" && pwd)"
else
  SRC_DIR="$(locate_src "$PWD" || true)"
  [ -n "$SRC_DIR" ] || die "当前目录没有找到 Markdown 文件。
   请把本脚本放到包含 .md 的目录里，或用 --dir 指定源目录"
fi

# ---------- 环境自检 ----------
info "检查环境"
if ! "$PY" "$SKILL_DIR/scripts/_env.py" >/dev/null 2>&1; then
  printf '%s  ✗%s 环境不满足\n\n' "$C_ERR" "$C_RESET"
  "$PY" "$SKILL_DIR/scripts/_env.py" 2>&1 | tail -8
  exit 1
fi
ok "Python / Node 可用"

# ---------- 交互向导 ----------
guess_name="$(basename "$SRC_DIR")"
[ -n "$OUT_DIR" ] || OUT_DIR="$(cd "$SRC_DIR/.." && pwd)/${guess_name}-site"
[ -n "$TITLE" ] || TITLE="$guess_name"

ask_yn() {
  local prompt="$1" default="$2" answer
  printf '%s [%s]: ' "$prompt" "$default" >&2
  read -r answer
  answer="${answer:-$default}"
  case "$answer" in [yY]*) return 0 ;; *) return 1 ;; esac
}

if [ "$WIZARD" = "true" ]; then
  echo
  printf '%s交互模式%s（直接回车使用方括号内的默认值）\n\n' "$C_B" "$C_RESET"

  printf '站点标题 [%s]: ' "$TITLE"; read -r input; TITLE="${input:-$TITLE}"
  printf '副标题 [留空]: '; read -r input; SUBTITLE="${input:-$SUBTITLE}"
  printf '输出目录 [%s]: ' "$OUT_DIR"; read -r input; OUT_DIR="${input:-$OUT_DIR}"
  echo
fi

# ---------- 生成站点 ----------
if [ -d "$OUT_DIR" ]; then
  warn "输出目录已存在：$OUT_DIR"
  if [ "$WIZARD" = "true" ]; then
    ask_yn "删除重建？会丢失该目录内的改动" "n" || { echo "已取消"; exit 0; }
    rm -rf "$OUT_DIR"
  else
    die "输出目录已存在。换一个 --out，或在 --wizard 模式下选择重建
   当前目录: $OUT_DIR"
  fi
fi

info "扫描并生成站点"
"$PY" "$SKILL_DIR/scripts/init.py" "$SRC_DIR" \
  --out "$OUT_DIR" --title "$TITLE" ${SUBTITLE:+--subtitle "$SUBTITLE"} ${NAME:+--name "$NAME"} \
  | sed 's/^/  /'

[ -f "$OUT_DIR/DEPLOY.md" ] || die "生成失败，请检查上面的输出"

# ---------- 安装依赖 ----------
cd "$OUT_DIR"
if [ "$NO_BUILD" = "false" ]; then
  if [ ! -f "node_modules/vitepress/package.json" ]; then
    info "安装依赖（首次约 1-3 分钟，请耐心等待）"
    npm install --no-audit --no-fund >/tmp/md2vp-npm.log 2>&1 \
      || { echo; tail -15 /tmp/md2vp-npm.log; die "npm install 失败，详见 /tmp/md2vp-npm.log"; }
    ok "依赖安装完成"
  else
    ok "依赖已就绪"
  fi

  # ---------- 构建 ----------
  info "构建站点"
  npm run build >/tmp/md2vp-build.log 2>&1 \
    || { echo; tail -20 /tmp/md2vp-build.log; die "构建失败，详见 /tmp/md2vp-build.log"; }

  PAGES=$(find docs/.vitepress/dist -name 'index.html' | wc -l | tr -d ' ')
  IMGS=$(find docs/.vitepress/dist/assets -type f \( -name '*.png' -o -name '*.jpeg' -o -name '*.jpg' \) 2>/dev/null | wc -l | tr -d ' ')
  ok "构建完成：${PAGES} 个页面 / ${IMGS} 张图片"
fi

# ---------- 打开预览 ----------
DIST="$OUT_DIR/docs/.vitepress/dist"
if [ ! -d "$DIST" ]; then
  warn "没有构建产物，跳过预览"
  printf '\n站点目录：%s\n' "$OUT_DIR"
  exit 0
fi

PORT=4173
info "启动本地预览"
# 后台起服务，记录 PID 方便关闭
nohup npm run preview >/tmp/md2vp-preview.log 2>&1 &
PREVIEW_PID=$!
trap 'kill $PREVIEW_PID 2>/dev/null || true' EXIT INT TERM

# 等端口就绪
for i in $(seq 1 30); do
  if curl -s -o /dev/null "http://127.0.0.1:$PORT/" 2>/dev/null; then break; fi
  sleep 0.5
done

URL="http://127.0.0.1:$PORT/"
if curl -s -o /dev/null "$URL" 2>/dev/null; then
  ok "预览地址：$URL"
  if [ "$DO_OPEN" = "true" ]; then
    if command -v open >/dev/null 2>&1; then open "$URL"
    elif command -v xdg-open >/dev/null 2>&1; then xdg-open "$URL"
    fi
  fi
else
  warn "预览服务未就绪，可手动执行：cd \"$OUT_DIR\" && npm run preview"
fi

cat <<EOF

$(printf '%s完成%s' "$C_B$C_OK" "$C_RESET")

  源目录    $SRC_DIR
  站点目录  $OUT_DIR
  产物      $DIST
  预览      $URL

  需要部署到服务器：见 $OUT_DIR/DEPLOY.md
  关闭预览：Ctrl+C（本窗口保持打开即服务在线）

EOF

# 前台等待，保持服务运行（双击窗口不闪退）
if [ "$DO_OPEN" = "true" ]; then
  printf '按 Ctrl+C 退出并停止预览服务...\n'
  wait $PREVIEW_PID 2>/dev/null || true
fi
