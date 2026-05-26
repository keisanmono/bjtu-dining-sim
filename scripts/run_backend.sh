#!/usr/bin/env bash
# 文件说明：后端启动脚本，进入仓库根目录并以 8001 端口运行 FastAPI。
set -euo pipefail

cd "$(dirname "$0")/../backend"
uvicorn app.main:app --reload --host 127.0.0.1 --port "${PORT:-8001}"
