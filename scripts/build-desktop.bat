@echo off
rem ============================================================
rem SciPlat 桌面端一键构建（pywebview 方案）
rem 产物1：backend\dist\SciPlat.exe（单文件，双击即独立运行）
rem 产物2：若本机装有 Inno Setup（ISCC.exe），额外生成安装包
rem   desktop\release\SciPlatSetup-0.4.0.exe
rem 依赖：Node/npm（仅前端构建）、.venv 已装 pyinstaller + pywebview
rem ============================================================
setlocal
cd /d %~dp0..

echo [1/3] 构建前端（npm run build）...
pushd frontend
call npm run build || goto :fail
popd

echo [2/3] 打包桌面端 SciPlat.exe（PyInstaller + pywebview）...
call .venv\Scripts\python.exe -m PyInstaller desktop\backend.spec --noconfirm --distpath backend\dist --workpath backend\build\pyinstaller --clean || goto :fail

echo [3/3] 生成安装包（Inno Setup，未安装则跳过）...
set "ISCC="
if exist "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" set "ISCC=C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
if exist "D:\Program Files (x86)\Inno Setup 6\ISCC.exe" set "ISCC=D:\Program Files (x86)\Inno Setup 6\ISCC.exe"
if exist "C:\Program Files\Inno Setup 6\ISCC.exe" set "ISCC=C:\Program Files\Inno Setup 6\ISCC.exe"
if defined ISCC (
  "%ISCC%" scripts\sciplat.iss || echo （Inno Setup 编译失败，单文件版仍可用）
) else (
  echo 未检测到 Inno Setup，仅提供单文件版 SciPlat.exe（可自行复制到任意目录运行）。
)

echo.
echo ============================================================
echo 构建完成：
echo   单文件版：backend\dist\SciPlat.exe
echo   安装包：  desktop\release\SciPlatSetup-0.4.0.exe（若已装 Inno Setup）
echo ============================================================
exit /b 0

:fail
echo.
echo 构建失败，请检查上方错误信息。
exit /b 1
