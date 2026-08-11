#!/usr/bin/env bash
# SciPlat 一键启动（Git Bash 环境）
set -e
cd "$(dirname "$0")/.."

echo "=========================================="
echo "  SciPlat 科研管理平台 - 一键启动"
echo "=========================================="

if [ ! -d .venv ]; then
  echo "[1/4] 创建 Python 虚拟环境..."
  python -m venv .venv
fi
source .venv/Scripts/activate

echo "[2/4] 安装后端依赖..."
pip install -q -r backend/requirements.txt

if [ ! -f frontend/dist/index.html ]; then
  echo "[3/4] 首次构建前端（需要几分钟）..."
  cd frontend
  npm install --no-fund --no-audit
  npm run build
  cd ..
else
  echo "[3/4] 前端已构建，跳过（如需重新构建请删除 frontend/dist 目录）"
fi

echo "[4/4] 启动服务：http://127.0.0.1:8000 （浏览器将自动打开）"
cd backend
python run.py
