#!/usr/bin/env bash
# 文件说明：前端启动脚本，进入 frontend 目录并启动 Vite 开发服务。
set -euo pipefail

cd "$(dirname "$0")/../frontend"
npm run dev
