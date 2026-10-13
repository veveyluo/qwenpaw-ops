#!/bin/bash
# pre_push_check.sh — 推送前敏感信息扫描
set -euo pipefail
FAIL=0
CHECKED=0

get_files() {
  local files
  files=$(git diff --cached --name-only --diff-filter=ACM 2>/dev/null)
  if [ -z "$files" ]; then files=$(git ls-files 2>/dev/null); fi
  echo "$files"
}

echo "=== pre-push 敏感信息检查 ==="

while IFS= read -r f; do
  [ -f "$f" ] || continue
  case "$f" in .gitignore|LICENSE|*.md|.github/*|pre_push_check.sh) continue ;; esac
  CHECKED=$((CHECKED + 1))

  # 1. 公网 IP（排除本地/内网/示例）
  IP_MATCHES=$(grep -nP '\b((25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)\.){3}(25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)\b' "$f" 2>/dev/null \
    | grep -vP '127\.0\.0\.1|0\.0\.0\.0|255\.255\.255\.255|1\.2\.3\.4|192\.168\.|10\.\d+\.|172\.(1[6-9]|2\d|3[01])\.' || true)
  if [ -n "$IP_MATCHES" ]; then echo "⚠️  $f: 疑似公网 IP"; echo "$IP_MATCHES"|head -3|sed 's/^/    /'; FAIL=1; fi

  # 2. 硬编码凭据
  for pat in 'SOCKS_PASS\s*=\s*[^"$]' 'API_KEY\s*=\s*["'"'"'][A-Za-z0-9]' 'ghp_[A-Za-z0-9]{36}' 'gho_[A-Za-z0-9]{36}' 'as_sk_[A-Za-z0-9]{20,}' 'sk-[A-Za-z0-9]{32,}' 'AKIA[0-9A-Z]{16}' 'xox[baprs]-[A-Za-z0-9-]{10,}'; do
    M=$(grep -nP "$pat" "$f" 2>/dev/null || true)
    if [ -n "$M" ]; then echo "⚠️  $f: 疑似硬编码凭据"; echo "$M"|head -3|sed 's/^/    /'; FAIL=1; fi
  done

  # 3. NAS / workspace 完整路径
  PATH_MATCHES=$(grep -nP '/run/csi|/[a-f0-9]{32}|workspaces/QwenPaw' "$f" 2>/dev/null | grep -v 'PATH_PATTERNS=' || true)
  if [ -n "$PATH_MATCHES" ]; then echo "⚠️  $f: 疑似 NAS 路径"; echo "$PATH_MATCHES"|head -3|sed 's/^/    /'; FAIL=1; fi

  # 4. 个人标识
  PERSONAL=$(grep -rniP 'YOUR_GITHUB_USER|YOUR_SSH_USER|YOUR_VPS_HOSTNAME|YOUR_DOMAIN' "$f" 2>/dev/null \
    | grep -vP 'Copyright.*YOUR_GITHUB_USER|YOUR_GITHUB_USER@users\.noreply' || true)
  if [ -n "$PERSONAL" ]; then echo "⚠️  $f: 疑似个人标识"; echo "$PERSONAL"|head -3|sed 's/^/    /'; FAIL=1; fi

done < <(get_files)

echo "扫描 $CHECKED 个文件"
[ "$FAIL" -eq 1 ] && { echo "❌ 发现敏感信息，推送已阻止"; exit 1; } || { echo "✅ 检查通过"; exit 0; }
