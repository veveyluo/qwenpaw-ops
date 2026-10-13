#!/bin/bash
# run.sh — 统一入口
# 用法:
#   bash run.sh check              # 检查所有补丁（只报告不补）
#   bash run.sh apply              # 检查并自动补回缺失补丁
#   bash run.sh check <name>       # 检查指定补丁
#   bash run.sh apply <name>       # 补回指定补丁
#   bash run.sh help               # 显示帮助
#
# 可用补丁名: gmi, cron, ast, compact, thinking
set -uo pipefail
cd "$(dirname "$0")"

# 自动加载 .env
if [ -f .env ]; then set -a; source .env; set +a; fi

PYTHON="${PYTHON:-python3}"

PATCHES=(gmi cron ast compact thinking)
declare -A SCRIPTS=(
  [gmi]="gmi_fallback_patch.py"
  [cron]="cron_dedup_check.py"
  [ast]="ast_search_dedup_check.py"
  [compact]="compact_cn_check.py"
  [thinking]="thinking_config_check.py"
)

run_patch() {
  local name="$1" mode="${2:-check}"
  local script="${SCRIPTS[$name]:-}"
  [ -n "$script" ] || { echo "❌ 未知补丁: $name"; return 2; }

  echo "--- $name ($script) ---"
  if [ "$mode" = "check" ]; then
    "$PYTHON" "$script" --check 2>&1
  else
    "$PYTHON" "$script" 2>&1
  fi
  return $?
}

run_all() {
  local mode="${1:-check}"
  local fail=0
  echo "========== QwenPaw 补丁检查 ($mode) =========="
  echo ""
  for p in "${PATCHES[@]}"; do
    run_patch "$p" "$mode" || fail=1
    echo ""
  done
  echo "========== 完成 (退出码: $fail) =========="
  return $fail
}

case "${1:-help}" in
  check)
    shift
    if [ -n "${1:-}" ]; then run_patch "$1" check; else run_all check; fi
    ;;
  apply)
    shift
    if [ -n "${1:-}" ]; then run_patch "$1" apply; else run_all apply; fi
    ;;
  help|*)
    echo "QwenPaw Ops — 补丁存活检查工具"
    echo ""
    echo "用法: bash run.sh <command> [patch-name]"
    echo ""
    echo "命令:"
    echo "  check [name]   检查补丁是否在位（不修改文件）"
    echo "  apply [name]   检查并自动补回缺失补丁"
    echo "  help           显示此帮助"
    echo ""
    echo "可用补丁:"
    echo "  gmi       内容审核误杀自动 fallback"
    echo "  cron      cron 跨进程去重"
    echo "  ast       ast_search 工具去重"
    echo "  compact   compact 汉化插件存活"
    echo "  thinking  思考档配置漂移检测"
    ;;
esac
