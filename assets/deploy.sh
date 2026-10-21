#!/usr/bin/env bash
# ============================================================
# 文档站部署脚本
#   用法：./deploy.sh               使用项目绑定的配置档，构建 + 上传
#         ./deploy.sh --profile X   临时使用指定配置档
#         ./deploy.sh --no-build    跳过构建
#         ./deploy.sh --dry-run     只检查配置和连通性，不上传
#
#   配置来源（按优先级）：
#     1. --profile 指定的配置档
#     2. 项目内 .deploy-profile 记录的配置档名
#     3. 项目内 deploy.conf（旧版兼容）
#   配置档位置：~/.workbuddy/deploy-profiles/<名字>.conf
# ============================================================
set -euo pipefail

# ---------- 平台检查 ----------
case "$(uname -s 2>/dev/null || echo unknown)" in
  MINGW*|MSYS*|CYGWIN*)
    # Git Bash 可用，但路径与权限易出问题；仅提醒不阻断
    ;;
  Linux|Darwin) ;;
  *)
    if [ -n "${WINDIR:-}" ] || [ -n "${COMSPEC:-}" ]; then
      echo "本脚本需要 bash 环境。Windows 用户请在 WSL 或 Git Bash 中运行。" >&2
      exit 1
    fi
    ;;
esac

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# 配置档目录：可用 MD2VP_PROFILE_DIR 覆盖（便于多用户/测试）
PROFILE_DIR="${MD2VP_PROFILE_DIR:-$HOME/.workbuddy/deploy-profiles}"
PROFILE_MARK="$SCRIPT_DIR/.deploy-profile"
DIST_DIR="$SCRIPT_DIR/docs/.vitepress/dist"

C_RESET=$'\033[0m'; C_INFO=$'\033[36m'; C_OK=$'\033[32m'; C_WARN=$'\033[33m'; C_ERR=$'\033[31m'
info() { printf '%s==>%s %s\n' "$C_INFO" "$C_RESET" "$*"; }
ok()   { printf '%s  ✓%s %s\n' "$C_OK" "$C_RESET" "$*"; }
warn() { printf '%s  !%s %s\n' "$C_WARN" "$C_RESET" "$*"; }
die()  { printf '%s  ✗%s %s\n' "$C_ERR" "$C_RESET" "$*" >&2; exit 1; }

# ---------- 参数 ----------
DO_BUILD=""
DRY_RUN="false"
PROFILE_NAME=""
while [ $# -gt 0 ]; do
  case "$1" in
    --no-build) DO_BUILD="false" ;;
    --build)    DO_BUILD="true" ;;
    --dry-run)  DRY_RUN="true" ;;
    --profile)
      [ $# -ge 2 ] || die "--profile 需要跟配置档名"
      PROFILE_NAME="$2"; shift ;;
    --profile=*) PROFILE_NAME="${1#*=}" ;;
    -h|--help)
      echo "用法: $0 [--profile 名字] [--no-build] [--dry-run]"
      echo "  --profile X  使用指定配置档（默认取项目 .deploy-profile）"
      echo "  --no-build   跳过构建，直接上传现有 dist 产物"
      echo "  --dry-run    仅检查配置与服务器连通性，不上传"
      exit 0 ;;
    *) die "未知参数: $1（用 --help 查看用法）" ;;
  esac
  shift
done

# ---------- 解析配置来源 ----------
CONF=""
CONF_SOURCE=""
if [ -n "$PROFILE_NAME" ]; then
  CONF="$PROFILE_DIR/$PROFILE_NAME.conf"
  CONF_SOURCE="配置档 ${PROFILE_NAME}（--profile）"
  [ -f "$CONF" ] || die "配置档不存在: $CONF
   先创建：python3 <skill>/scripts/profile.py set --name $PROFILE_NAME HOST=... USER=... REMOTE_DIR=..."
elif [ -f "$SCRIPT_DIR/.deploy-local.conf" ]; then
  CONF="$SCRIPT_DIR/.deploy-local.conf"
  CONF_SOURCE="站点本地配置 .deploy-local.conf"
elif [ -f "$PROFILE_MARK" ]; then
  PROFILE_NAME="$(tr -d '\r\n ' < "$PROFILE_MARK")"
  CONF="$PROFILE_DIR/$PROFILE_NAME.conf"
  CONF_SOURCE="配置档 $PROFILE_NAME"
  if [ ! -f "$CONF" ]; then
    die "项目绑定了配置档 ${PROFILE_NAME}，但文件不存在: $CONF
   用 profile.py set --name $PROFILE_NAME HOST=... 创建，或重新 bind 到其他配置档"
  fi
elif [ -f "$SCRIPT_DIR/deploy.conf" ]; then
  CONF="$SCRIPT_DIR/deploy.conf"
  CONF_SOURCE="项目内 deploy.conf（旧版）"
else
  die "未找到部署配置。任选其一：
   1) 绑定配置档：python3 <skill>/scripts/profile.py bind --project \"$SCRIPT_DIR\" --name <名字>
   2) 缓存配置到本地：python3 <skill>/scripts/profile.py cache --project \"$SCRIPT_DIR\"
   3) 项目内放 deploy.conf（旧版方式）"
fi

# 只接受 KEY=VALUE 形式的简单配置，不执行任意 shell 代码
load_conf() {
  local file="$1" line key val
  while IFS= read -r line || [ -n "$line" ]; do
    line="${line#"${line%%[![:space:]]*}"}"
    case "$line" in ''|'#'*) continue ;; esac
    case "$line" in *=*) ;; *) continue ;; esac
    key="${line%%=*}"
    val="${line#*=}"
    key="$(printf '%s' "$key" | tr -d '[:space:]')"
    case "$key" in
      HOST|PORT|USER|REMOTE_DIR|SSH_KEY|SSH_KEY_PASSPHRASE|SITE_BASE|CLEAN_MODE|BUILD_BEFORE_DEPLOY|REMOTE_TMP|DIST_NAME|UPLOAD_WITH_DIR) ;;
      *) continue ;;
    esac
    # 去掉两端引号
    case "$val" in
      \"*\") val="${val#\"}"; val="${val%\"}" ;;
      \'*\') val="${val#\'}"; val="${val%\'}" ;;
    esac
    val="${val//\$HOME/$HOME}"
    eval "$key=\"\$val\""
  done < "$file"
}
load_conf "$CONF"

: "${HOST:?配置缺少 HOST（用 profile.py set 补上）}"
: "${USER:?配置缺少 USER（用 profile.py set 补上）}"
: "${REMOTE_DIR:?配置缺少 REMOTE_DIR（用 profile.py set 补上）}"
PORT="${PORT:-22}"
REMOTE_DIR="${REMOTE_DIR%/}"
REMOTE_TMP="${REMOTE_TMP:-/tmp}"
CLEAN_MODE="${CLEAN_MODE:-manifest}"
[ -z "$DO_BUILD" ] && DO_BUILD="${BUILD_BEFORE_DEPLOY:-true}"
DIST_NAME="${DIST_NAME:-dist}"
UPLOAD_WITH_DIR="${UPLOAD_WITH_DIR:-false}"

printf '\n%s╭─ 部署目标 ───────────────────────────────────╮%s\n' "$C_INFO" "$C_RESET"
printf '  %-10s %s@%s:%s\n' "服务器" "$USER" "$HOST" "$PORT"
printf '  %-10s %s\n' "目录" "$REMOTE_DIR"
printf '  %-10s %s\n' "站点根路径" "${SITE_BASE:-/}"
printf '  %-10s %s\n' "清理方式" "$CLEAN_MODE"
printf '  %-10s %s\n' "配置来源" "$CONF_SOURCE"
printf '%s╰──────────────────────────────────────────────╯%s\n\n' "$C_INFO" "$C_RESET"

# ---------- 打包前的构建 ----------
if [ "$DO_BUILD" != "false" ]; then
  info "构建站点"
  command -v npm >/dev/null 2>&1 || die "未找到 npm。
   Node.js 18+ 是构建必需依赖，安装方式见 https://nodejs.org
   或用本 skill 自带检测：python3 scripts/_env.py"

  cd "$SCRIPT_DIR"

  # 依赖未安装则自动安装（标准 npm install）
  if [ ! -f "node_modules/vitepress/package.json" ]; then
    info "首次构建，安装依赖（约 1-3 分钟）"
    npm install --no-audit --no-fund || die "npm install 失败，请检查网络或 npm 源配置"
    ok "依赖安装完成"
  fi

  npm run build || die "构建失败，已中止部署"
  ok "构建完成"
else
  info "跳过构建（--no-build）"
fi

[ -d "$DIST_DIR" ] || die "找不到构建产物: $DIST_DIR"
PAGE_COUNT=$(find "$DIST_DIR" -name 'index.html' | wc -l | tr -d ' ')
IMG_COUNT=$(find "$DIST_DIR" -type f \( -name '*.png' -o -name '*.jpg' -o -name '*.jpeg' -o -name '*.gif' -o -name '*.svg' -o -name '*.webp' \) | wc -l | tr -d ' ')
[ "$PAGE_COUNT" -gt 0 ] || die "产物中没有页面，请先构建"
ok "产物检查：${PAGE_COUNT} 个页面 / ${IMG_COUNT} 张图片"

# ---------- SSH 参数 ----------
# BatchMode=yes：不允许交互输入密码，避免密钥未配置时脚本卡死等输入
SSH_OPTS=(-p "$PORT" -o StrictHostKeyChecking=accept-new -o ConnectTimeout=15 -o BatchMode=yes)
SCP_OPTS=(-P "$PORT" -o StrictHostKeyChecking=accept-new -o ConnectTimeout=15 -o BatchMode=yes)
if [ -n "${SSH_KEY:-}" ]; then
  [ -f "$SSH_KEY" ] || die "找不到私钥: $SSH_KEY"
  SSH_OPTS+=(-i "$SSH_KEY")
  SCP_OPTS+=(-i "$SSH_KEY")
fi

USE_SSHPASS="false"
if [ -n "${SSH_KEY_PASSPHRASE:-}" ]; then
  if command -v sshpass >/dev/null 2>&1; then
    USE_SSHPASS="true"
  else
    die "私钥有口令但本机未安装 sshpass。建议执行 ssh-add \"$SSH_KEY\" 后把 SSH_KEY_PASSPHRASE 置空"
  fi
fi

ssh_run() {
  local cmd="$1"
  if [ "$USE_SSHPASS" = "true" ]; then
    sshpass -p "$SSH_KEY_PASSPHRASE" ssh "${SSH_OPTS[@]}" "$USER@$HOST" "$cmd"
  else
    ssh "${SSH_OPTS[@]}" "$USER@$HOST" "$cmd"
  fi
}
scp_run() {
  if [ "$USE_SSHPASS" = "true" ]; then
    sshpass -p "$SSH_KEY_PASSPHRASE" scp "${SCP_OPTS[@]}" "$@"
  else
    scp "${SCP_OPTS[@]}" "$@"
  fi
}

# ---------- 连通性检查 ----------
info "检查服务器连通性"
if ! ssh_run "echo connect-ok" >/dev/null 2>&1; then
  die "SSH 连接失败（已禁止交互输入密码）。
     最常见原因：公钥还没装到服务器。执行一次：
       ssh-copy-id -i ${SSH_KEY:-$HOME/.ssh/id_rsa}.pub $USER@$HOST
     其他排查：网络、端口 ${PORT}、账号 ${USER} 是否正确。
     手动验证：ssh -o BatchMode=yes -p $PORT ${SSH_KEY:+-i $SSH_KEY} $USER@$HOST true"
fi
ok "SSH 连接正常"

if ! ssh_run "test -d '$REMOTE_DIR' && echo dir-ok" >/dev/null 2>&1; then
  die "远程目录不存在: $REMOTE_DIR
     如确需自动创建，请先手动执行：ssh $USER@$HOST 'mkdir -p $REMOTE_DIR'"
fi
ok "远程目录存在"

if [ "$DRY_RUN" = "true" ]; then
  printf '\n%s模拟运行结束，未上传任何文件。%s\n\n' "$C_WARN" "$C_RESET"
  exit 0
fi

# ---------- 本地打包 ----------
STAMP="$(date +%Y%m%d-%H%M%S)"
SITE_NAME="$(grep -o '"name": *"[^"]*"' "$SCRIPT_DIR/package.json" 2>/dev/null | head -1 | sed 's/.*"\([^"]*\)"$/\1/')"
SITE_NAME="${SITE_NAME:-$(basename "$SCRIPT_DIR")}"
PKG_NAME="$SITE_NAME-$STAMP.tar.gz"
PKG_PATH="$SCRIPT_DIR/$PKG_NAME"
cleanup_local() { rm -f "$PKG_PATH"; }
trap cleanup_local EXIT

info "打包产物"
# --no-xattrs 避免 macOS 扩展属性在 Linux 上产生警告
if [ "$UPLOAD_WITH_DIR" = "true" ]; then
  # 带文件夹一起上传：远程出现 <REMOTE_DIR>/<DIST_NAME>/
  if [ "$DIST_NAME" = "dist" ]; then
    tar --no-xattrs -czf "$PKG_PATH" -C "$DIST_DIR/.." dist 2>/dev/null || \
      tar -czf "$PKG_PATH" -C "$DIST_DIR/.." dist
  else
    STAGE="$SCRIPT_DIR/.deploy-stage"
    rm -rf "$STAGE"; mkdir -p "$STAGE"
    cp -R "$DIST_DIR" "$STAGE/$DIST_NAME"
    tar --no-xattrs -czf "$PKG_PATH" -C "$STAGE" "$DIST_NAME" 2>/dev/null || \
      tar -czf "$PKG_PATH" -C "$STAGE" "$DIST_NAME"
    rm -rf "$STAGE"
  fi
else
  # 平铺（默认）：远程是 <REMOTE_DIR>/index.html
  tar --no-xattrs -czf "$PKG_PATH" -C "$DIST_DIR" . 2>/dev/null || \
    tar -czf "$PKG_PATH" -C "$DIST_DIR" .
fi
PKG_SIZE=$(du -h "$PKG_PATH" | awk '{print $1}')
ok "打包完成：${PKG_NAME}（${PKG_SIZE}）"

# ---------- 上传 ----------
REMOTE_PKG="$REMOTE_TMP/$PKG_NAME"
info "上传到服务器（约 ${PKG_SIZE}，请稍候）"
scp_run "$PKG_PATH" "$USER@$HOST:$REMOTE_PKG" || die "上传失败"
ok "上传完成"

# ---------- 远程解压与清理 ----------
info "远程解压部署"
REMOTE_SCRIPT=$(cat <<EOF
set -e
cd "$REMOTE_DIR"

# 1) 按清单清理上次部署的文件（只删清单内、且当前存在的文件）
MANIFEST=".deploy-manifest"
if [ "$CLEAN_MODE" = "manifest" ] && [ -f "\$MANIFEST" ]; then
  while IFS= read -r rel; do
    if [ -n "\$rel" ] && [ -e "\$rel" ]; then rm -f -- "\$rel"; fi
  done < "\$MANIFEST"
elif [ "$CLEAN_MODE" = "all" ]; then
  find . -mindepth 1 -maxdepth 1 ! -name ".deploy-manifest" -exec rm -rf {} +
fi

# 2) 解压覆盖
tar -xzf "$REMOTE_PKG" -C "$REMOTE_DIR"

# 3) 记录本次部署清单，供下次清理
if [ "$CLEAN_MODE" = "manifest" ]; then
  find . -type f ! -name "\$MANIFEST" ! -name ".user.ini" | sed 's|^\./||' | sort > "\$MANIFEST"
fi

rm -f "$REMOTE_PKG"
echo "remote-deploy-done"
EOF
)

ssh_run "$REMOTE_SCRIPT" | grep -q "remote-deploy-done" || die "远程解压失败"
ok "远程部署完成"

# ---------- 结果校验 ----------
info "校验线上文件"
REMOTE_INDEX_OK=$(ssh_run "test -f '$REMOTE_DIR/index.html' && echo yes" 2>/dev/null || true)
[ "$REMOTE_INDEX_OK" = "yes" ] || die "线上缺少 index.html，部署可能异常"
REMOTE_FILE_COUNT=$(ssh_run "find '$REMOTE_DIR' -type f | wc -l" | tr -d ' ')
ok "线上文件数：$REMOTE_FILE_COUNT"

DOMAIN="${HOST}"
printf '\n%s部署成功%s\n' "$C_OK" "$C_RESET"
printf '  时间    %s\n' "$STAMP"
printf '  地址    https://%s/\n' "$DOMAIN"
printf '  目录    %s\n\n' "$REMOTE_DIR"
