@echo off
rem NOTE: This file is GBK/ANSI encoded for zh-CN Windows cmd. Do NOT edit with UTF-8 tools directly; convert with: iconv -f UTF-8 -t GBK
setlocal
cd /d "%~dp0\.."

echo ==========================================
echo   SciPlat 科研管理平台 - 一键启动
echo ==========================================

where python >nul 2>nul
if errorlevel 1 (
  echo [错误] 未找到 Python，请先安装 Python 3.10+ 并勾选 "Add to PATH"。
  pause
  exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
  echo [1/4] 创建 Python 虚拟环境...
  python -m venv .venv
  if errorlevel 1 goto :fail
) else (
  echo [1/4] 虚拟环境已存在
)

call ".venv\Scripts\activate.bat"

echo [2/4] 安装后端依赖...
pip install -q -r "backend\requirements.txt"
if errorlevel 1 goto :fail

if not exist "frontend\dist\index.html" (
  echo [3/4] 首次构建前端（需要几分钟）...
  cd frontend
  call npm install --no-fund --no-audit
  if errorlevel 1 goto :fail
  call npm run build
  if errorlevel 1 goto :fail
  cd ..
) else (
  echo [3/4] 前端已构建，跳过（如需重新构建请删除 frontend\dist 目录）
)

echo [4/4] 启动服务：http://127.0.0.1:8000
echo       浏览器将自动打开。关闭本窗口即停止服务。
echo       若提示端口被占用，请先关闭旧的服务窗口再重试。
cd backend
python run.py

echo.
echo 服务已停止。
pause
exit /b 0

:fail
echo.
echo [错误] 启动过程出错，请检查上方日志。
echo 若为端口占用（10048），请关闭已运行的服务窗口后重试。
pause
exit /b 1
