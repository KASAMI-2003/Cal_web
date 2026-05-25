#!/usr/bin/env bash
# 安装数字孪生所需的 HTEM 最小运行时（source + Si 示例 dat）
# 用法：在 tsx-web-app 根目录执行 ./scripts/setup_htem.sh [HTEM-main路径]

set -euo pipefail
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DEST="$REPO_ROOT/server/digital_twin/HTEM-main"
SOURCE="${1:-}"

if [[ -z "$SOURCE" ]]; then
  for c in \
    "$REPO_ROOT/../digital_twin/HTEM-main" \
    "$REPO_ROOT/../../digital_twin/HTEM-main" \
    "$DEST"
  do
    if [[ -f "$c/source/elasticity.py" ]]; then
      SOURCE="$c"
      break
    fi
  done
fi

if [[ -z "$SOURCE" || ! -f "$SOURCE/source/elasticity.py" ]]; then
  echo "未找到 HTEM-main。用法: $0 /path/to/HTEM-main" >&2
  exit 1
fi

echo "HTEM 源: $SOURCE"
echo "安装到: $DEST"

mkdir -p "$DEST/example/5_Si_model"
rm -rf "$DEST/source"
cp -R "$SOURCE/source" "$DEST/source"
cp -f "$SOURCE/example/5_Si_model/Elasticity_cold+NVT_s4.dat" "$DEST/example/5_Si_model/"
[[ -f "$SOURCE/LICENSE" ]] && cp -f "$SOURCE/LICENSE" "$DEST/"
[[ -f "$SOURCE/README.md" ]] && cp -f "$SOURCE/README.md" "$DEST/"

echo "HTEM 最小运行时已就绪。重启 pyserver 后数字孪生曲面可用。"
