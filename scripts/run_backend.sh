#!/usr/bin/env bash
# 文件说明：后端启动脚本，优先使用项目虚拟环境并以 8001 端口运行 FastAPI。
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

if [[ -x "$REPO_ROOT/backend/.venv/bin/uvicorn" ]]; then
  UVICORN_BIN="$REPO_ROOT/backend/.venv/bin/uvicorn"
elif [[ -x "$REPO_ROOT/.venv/bin/uvicorn" ]]; then
  UVICORN_BIN="$REPO_ROOT/.venv/bin/uvicorn"
else
  UVICORN_BIN="uvicorn"
fi

exec "$UVICORN_BIN" app.main:app --app-dir "$REPO_ROOT/backend" --reload --host 127.0.0.1 --port "${PORT:-8001}"
