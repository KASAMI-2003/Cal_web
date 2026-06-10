#!/usr/bin/env bash
# 论文 MySQL 种子数据一键导入（在仓库根目录或 deploy 目录执行均可）
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MYSQL_USER="${MYSQL_USER:-py_server}"
MYSQL_PASS="${MYSQL_PASS:-123456}"

mysql -u "$MYSQL_USER" -p"$MYSQL_PASS" < "$SCRIPT_DIR/thesis-element_inf.sql"
mysql -u "$MYSQL_USER" -p"$MYSQL_PASS" < "$SCRIPT_DIR/thesis-materials.sql"

echo "Done. element_inf + materials thesis seed imported."
