#!/usr/bin/env bash
# ============================================================
# md2website 安装脚本
#
# 用法：
#   ./install.sh                    交互式选择安装到哪些 Agent
#   ./install.sh --all              安装到所有已检测到的 Agent
#   ./install.sh --dir <路径>        安装到指定目录（可重复）
#   ./install.sh --list             只列出检测到的 Agent 目录
#   ./install.sh --yes              跳过安装前确认
#   ./install.sh --uninstall        卸载当前副本
#   ./install.sh --uninstall --all  卸载所有检测到的副本
#   ./install.sh --check            只检查环境，不安装
# HELP_END
# ============================================================
set -euo pipefail

NAME="md2website"
SRC_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MODE="install"
ASSUME_ALL="false"
ASSUME_YES="false"
TARGETS=""          # 换行分隔的安装目标列表

# 已支持的桌面 Agent（顺序即交互编号）
CAND_LABELS=("Trae CN" "Trae" "Codex" "Claude Code" "WorkBuddy")
CAND_DIRS=(
  "$HOME/.trae-cn/skills"
  "$HOME/.trae/skills"
  "$HOME/.codex/skills"
  "$HOME/.claude/skills"
  "$HOME/.workbuddy/skills"
)
FALLBACK_DIR="$HOME/.workbuddy/skills/$NAME"

C_RESET=$'\033[0m'; C_INFO=$'\033[36m'; C_OK=$'\033[32m'; C_WARN=$'\033[33m'; C_ERR=$'\033[31m'; C_B=$'\033[1m'
info() { printf '%s==>%s %s\n' "$C_INFO" "$C_RESET" "$*"; }
ok()   { printf '%s  ✓%s %s\n' "$C_OK" "$C_RESET" "$*"; }
warn() { printf '%s  !%s %s\n' "$C_WARN" "$C_RESET" "$*"; }
die()  { printf '%s  ✗%s %s\n' "$C_ERR" "$C_RESET" "$*" >&2; exit 1; }

# ---------- 通用小工具 ----------
short_path() {
  case "$1" in
    "$HOME"*) printf '~%s' "${1#"$HOME"}" ;;
    *) printf '%s' "$1" ;;
  esac
}

in_targets() {
  [ -n "$TARGETS" ] || return 1
  printf '%s\n' "$TARGETS" | grep -Fxq "$1"
}

add_target() {
  local t="$1"
  [ -n "$t" ] || return 1
  case "$t" in
    "~") t="$HOME" ;;
    "~/"*) t="$HOME/${t#'~/'}" ;;
  esac
  while [ "$t" != "/" ] && [ "${t%/}" != "$t" ]; do t="${t%/}"; done
  in_targets "$t" && return 0
  if [ -z "$TARGETS" ]; then
    TARGETS="$t"
  else
    TARGETS="$(printf '%s\n%s' "$TARGETS" "$t")"
  fi
  return 0
}

# ---------- 参数 ----------
while [ $# -gt 0 ]; do
  case "$1" in
    --dir)
      [ $# -ge 2 ] || die "--dir 需要跟路径"
      add_target "$2"; shift ;;
    --dir=*) add_target "${1#*=}" ;;
    --all) ASSUME_ALL="true" ;;
    --yes|-y) ASSUME_YES="true" ;;
    --uninstall) MODE="uninstall" ;;
    --check) MODE="check" ;;
    --list) MODE="list" ;;
    -h|--help)
      sed -n '2,/^# HELP_END/p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//' | sed '$d'
      exit 0 ;;
    *) die "未知参数: $1（--help 查看用法）" ;;
  esac
  shift
done

count_targets() { printf '%s\n' "$TARGETS" | grep -c . || true; }

first_target() { printf '%s\n' "$TARGETS" | sed -n '1p'; }

print_targets() {
  local t n=1 old_ifs="$IFS"
  IFS='
'
  for t in $TARGETS; do
    [ -n "$t" ] || continue
    printf '  %s) %s\n' "$n" "$(short_path "$t")"
    n=$((n + 1))
  done
  IFS="$old_ifs"
}

# 候选目录状态：installed / occupied / ready / source / agent-absent
cand_state() {
  local skills_dir="$1"
  local target="$skills_dir/$NAME"
  if [ ! -d "$skills_dir" ]; then printf 'agent-absent'; return 0; fi
  if [ "$SRC_DIR" = "$target" ]; then printf 'source'; return 0; fi
  if [ -f "$target/.installed-to" ] && [ -f "$target/SKILL.md" ]; then printf 'installed'; return 0; fi
  if [ -d "$target" ]; then printf 'occupied'; return 0; fi
  printf 'ready'
}

state_text() {
  case "$1" in
    installed) printf '已安装' ;;
    occupied) printf '目录已存在' ;;
    ready) printf '可安装' ;;
    source) printf '当前源目录' ;;
    agent-absent) printf '未安装该 Agent' ;;
    *) printf '%s' "$1" ;;
  esac
}

print_candidates() {
  local i sd state
  printf '\n  编号  %-13s %-30s %s\n' "Agent" "路径" "状态"
  for i in 1 2 3 4 5; do
    sd="${CAND_DIRS[$((i - 1))]}"
    state="$(cand_state "$sd")"
    printf '   %s    %-13s %-30s %s\n' "$i" "${CAND_LABELS[$((i - 1))]}" "$(short_path "$sd")" "$(state_text "$state")"
  done
  printf '   6    %-13s %s\n' "Custom Path" "（安装时输入绝对路径）"
  printf '\n'
}

# ---------- 环境检查 ----------
check_env() {
  info "检查运行环境"
  local fail=0 py=""

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

  if command -v node >/dev/null 2>&1; then
    local ver major
    ver="$(node --version | sed 's/^v//')"
    major="${ver%%.*}"
    if [ "${major:-0}" -ge 18 ] 2>/dev/null; then
      ok "Node $ver"
    else
      printf '%s  ✗%s Node 版本过低：${ver}（需 18+）\n' "$C_ERR" "$C_RESET"; fail=1
    fi
  else
    printf '%s  ✗%s 未找到 Node.js（构建必需）\n' "$C_ERR" "$C_RESET"
    echo "     安装方式：https://nodejs.org 或 brew install node / nvm"
    fail=1
  fi

  local tool
  for tool in tar scp ssh; do
    command -v "$tool" >/dev/null 2>&1 && ok "$tool 可用" || warn "缺少 ${tool}（部署功能不可用）"
  done

  return $fail
}

# ---------- 目标选择 ----------
add_choice() {
  local n="$1"
  case "$n" in
    ''|*[!0-9]*) return 1 ;;
  esac
  if [ "$n" -lt 1 ] || [ "$n" -gt 6 ]; then return 1; fi

  if [ "$n" = "6" ]; then
    local custom=""
    printf '自定义安装目录（绝对路径）: '
    read -r custom || custom=""
    if [ -z "$custom" ]; then
      warn "已跳过自定义路径"
      return 0
    fi
    add_target "$custom"
    return 0
  fi

  local sd="${CAND_DIRS[$((n - 1))]}" label="${CAND_LABELS[$((n - 1))]}" state
  state="$(cand_state "$sd")"
  case "$state" in
    agent-absent)
      warn "跳过 ${label}：未检测到 $(short_path "$sd")"
      return 0 ;;
    source)
      warn "跳过 ${label}：这就是当前源目录"
      return 0 ;;
  esac
  add_target "$sd/$NAME"
}

collect_all_targets() {
  local i sd state
  for i in 1 2 3 4 5; do
    sd="${CAND_DIRS[$((i - 1))]}"
    state="$(cand_state "$sd")"
    case "$state" in
      installed|occupied|ready) add_target "$sd/$NAME" ;;
    esac
  done
}

interactive_select() {
  local i sd state default_list="" input="" tok lo hi

  info "探测 Agent skills 目录"
  print_candidates

  # 默认值：优先已安装过的目录；没有则默认全部可安装目录
  for i in 1 2 3 4 5; do
    sd="${CAND_DIRS[$((i - 1))]}"
    state="$(cand_state "$sd")"
    if [ "$state" = "installed" ]; then default_list="$default_list $i"; fi
  done
  if [ -z "$default_list" ]; then
    for i in 1 2 3 4 5; do
      sd="${CAND_DIRS[$((i - 1))]}"
      state="$(cand_state "$sd")"
      if [ "$state" = "ready" ] || [ "$state" = "occupied" ]; then default_list="$default_list $i"; fi
    done
  fi

  printf '选择安装目标 [1-6，空格或逗号分隔，a=全选，q=取消]'
  if [ -n "$default_list" ]; then printf '（回车默认:%s）' "$default_list"; fi
  printf ': '
  read -r input || input=""

  case "$input" in
    q|Q) info "已取消"; exit 0 ;;
    "")  input="$default_list" ;;
    a|A) input="1 2 3 4 5" ;;
  esac

  input="$(printf '%s' "$input" | tr ',' ' ')"

  for tok in $input; do
    case "$tok" in
      *-*)
        lo="${tok%%-*}"; hi="${tok##*-}"
        case "$lo$hi" in
          ''|*[!0-9]*) warn "忽略无效范围：$tok"; continue ;;
        esac
        if [ "$lo" -gt "$hi" ]; then warn "忽略无效范围：$tok"; continue; fi
        while [ "$lo" -le "$hi" ]; do
          add_choice "$lo" || warn "忽略无效选项：$lo"
          lo=$((lo + 1))
        done
        ;;
      *)
        add_choice "$tok" || warn "忽略无效选项：$tok"
        ;;
    esac
  done

  [ -n "$TARGETS" ] || die "没有选择任何安装目标（可重新运行，或使用 --dir <路径>）"
}

confirm_targets() {
  if [ "$ASSUME_YES" = "true" ] || [ ! -t 0 ]; then return 0; fi
  printf '\n将安装 %s 到 %s 个目录：\n' "$NAME" "$(count_targets)"
  print_targets
  printf '\n确认继续？[Y/n]: '
  local ans=""
  read -r ans || ans=""
  case "$ans" in
    n|N|no|NO) info "已取消"; exit 0 ;;
  esac
}

# ---------- 安装 / 卸载 ----------
install_one() {
  local target="$1" item f
  if [ "$SRC_DIR" = "$target" ]; then
    warn "跳过源目录：$target"
    return 1
  fi
  case "$target" in
    "$HOME"|"/"|"/usr"|"/tmp"|"/etc"|"/var"|"")
      warn "跳过危险路径：$target"; return 1 ;;
  esac

  mkdir -p "$(dirname "$target")" 2>/dev/null || { warn "无法创建父目录：$target"; return 1; }
  rm -rf "$target" 2>/dev/null || { warn "无法清理旧目录：$target"; return 1; }
  mkdir -p "$target" 2>/dev/null || { warn "无法创建目录：$target"; return 1; }

  for item in SKILL.md README.md README.en.md SETUP.md LICENSE install.sh scripts assets; do
    if [ -e "$SRC_DIR/$item" ]; then
      cp -R "$SRC_DIR/$item" "$target/" 2>/dev/null || { warn "复制失败：$item"; return 1; }
    fi
  done
  chmod +x "$target/assets/deploy.sh" "$target/assets/build.sh" "$target/install.sh" 2>/dev/null || true
  chmod +x "$target"/scripts/*.py 2>/dev/null || true

  for f in SKILL.md scripts/init.py scripts/scan.py scripts/fix.py scripts/profile.py assets/deploy.sh assets/build.sh; do
    if [ ! -f "$target/$f" ]; then
      warn "安装不完整，缺少 ${f}：${target}"
      return 1
    fi
  done

  printf '%s\n' "$target" > "$target/.installed-to"
  return 0
}

install_all() {
  local t ok_n=0 fail_n=0 old_ifs="$IFS"
  IFS='
'
  for t in $TARGETS; do
    [ -n "$t" ] || continue
    if install_one "$t"; then
      ok_n=$((ok_n + 1))
      ok "$(short_path "$t")"
    else
      fail_n=$((fail_n + 1))
      printf '%s  ✗%s %s\n' "$C_ERR" "$C_RESET" "$(short_path "$t")"
    fi
  done
  IFS="$old_ifs"

  printf '\n安装完成：%s 成功' "$ok_n"
  if [ "$fail_n" -gt 0 ]; then printf '，%s 失败' "$fail_n"; fi
  printf '\n'

  local first
  first="$(first_target)"
  printf '\n  位置    %s\n' "$(short_path "$first")"
  printf '  自检    python3 "%s/scripts/_env.py"\n' "$first"
  printf '  更新    在仓库重新执行 ./install.sh，默认只更新已安装的目录\n'

  [ "$fail_n" -eq 0 ]
}

collect_uninstall_targets() {
  local i sd state
  if [ "$ASSUME_ALL" = "true" ]; then
    for i in 1 2 3 4 5; do
      sd="${CAND_DIRS[$((i - 1))]}"
      state="$(cand_state "$sd")"
      if [ "$state" = "installed" ]; then add_target "$sd/$NAME"; fi
    done
    return 0
  fi

  if [ -n "$TARGETS" ]; then return 0; fi

  # 未显式指定时，以当前副本的安装记录为准
  if [ -f "$SRC_DIR/.installed-to" ]; then
    add_target "$(tr -d '\r\n' < "$SRC_DIR/.installed-to")"
  else
    die "当前目录不是已安装的 skill（缺少 .installed-to 记录）
   请显式指定目标：./install.sh --uninstall --dir <已安装目录>
   或卸载全部：  ./install.sh --uninstall --all"
  fi
}

uninstall_one() {
  local target="$1"
  [ -f "$target/SKILL.md" ] && grep -q 'name: md2website' "$target/SKILL.md" 2>/dev/null \
    || { warn "拒绝卸载：$target 不像 md2website 安装目录"; return 1; }
  case "$target" in
    "$HOME"|"/"|"/usr"|"/tmp"|"/etc"|"/var"|"")
      warn "拒绝卸载：危险路径 $target"; return 1 ;;
  esac
  [ "$target" = "${target%/}" ] || { warn "目标路径异常：$target"; return 1; }

  rm -rf "$target"
  ok "已删除 $(short_path "$target")"
  return 0
}

do_uninstall() {
  local t ok_n=0 fail_n=0 answer="" old_ifs

  collect_uninstall_targets
  [ -n "$TARGETS" ] || die "没有找到可卸载的副本"

  printf '即将删除 %s 个目录：\n' "$(count_targets)"
  print_targets
  printf '确认请输入 yes: '
  read -r answer || answer=""
  [ "$answer" = "yes" ] || { echo "已取消"; exit 0; }

  old_ifs="$IFS"; IFS='
'
  for t in $TARGETS; do
    [ -n "$t" ] || continue
    if uninstall_one "$t"; then ok_n=$((ok_n + 1)); else fail_n=$((fail_n + 1)); fi
  done
  IFS="$old_ifs"

  printf '\n卸载完成：%s 成功' "$ok_n"
  if [ "$fail_n" -gt 0 ]; then printf '，%s 失败' "$fail_n"; fi
  printf '\n'
  echo "注意：部署配置档（~/.workbuddy/deploy-profiles）未删除，如需清理请手动操作。"
  [ "$fail_n" -eq 0 ]
}

# ---------- 主流程 ----------
case "$MODE" in
  check)
    check_env && { echo; ok "环境满足要求"; exit 0; } || { echo; die "环境不满足，请先补齐依赖"; }
    ;;

  list)
    info "检测到的 Agent skills 目录"
    print_candidates
    exit 0
    ;;

  uninstall)
    do_uninstall
    ;;

  install)
    check_env || echo
    echo

    [ -d "$SRC_DIR/scripts" ] || die "当前目录不像 skill 包（缺少 scripts/）"

    if [ -z "$TARGETS" ]; then
      if [ "$ASSUME_ALL" = "true" ]; then
        collect_all_targets
      elif [ -t 0 ]; then
        interactive_select
      else
        # 非交互环境（Agent 执行 / CI / 管道）：装到所有已检测到的 Agent 目录，
        # 确保发起安装的那个 Agent 也能加载；一个都没检测到时退回默认目录
        collect_all_targets
        [ -n "$TARGETS" ] || add_target "$FALLBACK_DIR"
      fi
    fi

    [ -n "$TARGETS" ] || die "没有可安装的目标目录（可用 --dir <路径> 指定）"

    confirm_targets
    install_all
    ;;
esac
