#!/usr/bin/env bash
# 一键启动：后端 pyserver（含可选 cargo）+ 前端 Vite 开发服务器
# 用法：在项目根目录执行  bash scripts/start-all.sh
# 环境变量：PYTHON（默认 python3）、TERMINAL_WS_PORT（默认 8765）、TSX_SKIP_RUST_SERVER=1 跳过 Rust

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON_BIN="${PYTHON:-python3}"

cd "$ROOT"

if [[ ! -d "$ROOT/web/node_modules" ]]; then
  echo "[start-all] web/node_modules 不存在，请先执行: cd web && npm install"
  exit 1
fi

cleanup() {
  if [[ -n "${BACK_PID:-}" ]] && kill -0 "$BACK_PID" 2>/dev/null; then
    kill "$BACK_PID" 2>/dev/null || true
    wait "$BACK_PID" 2>/dev/null || true
  fi
}
trap cleanup EXIT INT TERM

echo "[start-all] 启动后端: $ROOT/server ($PYTHON_BIN pyserver.py)"
(
  cd "$ROOT/server"
  if [[ -f .venv/bin/activate ]]; then
    # shellcheck source=/dev/null
    source .venv/bin/activate
    PYTHON_BIN="$(command -v python || command -v python3 || echo "$PYTHON_BIN")"
  fi
  export TERMINAL_WS_PORT="${TERMINAL_WS_PORT:-8765}"
  exec "$PYTHON_BIN" pyserver.py
) &
BACK_PID=$!

sleep 1
if ! kill -0 "$BACK_PID" 2>/dev/null; then
  echo "[start-all] 后端进程已退出，请检查 server 目录下依赖与日志。"
  exit 1
fi

echo "[start-all] 启动前端: npm run dev（Ctrl+C 将结束前端并停止后端）"
cd "$ROOT/web"
npm run dev
