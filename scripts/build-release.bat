@echo off
rem ============================================================
rem SciPlat 发布构建：前端 → exe → 安装包 → latest.json
rem 产物：desktop\release\（SciPlatSetup-x.y.z.exe + latest.json）
rem 上传：GitHub Release 附件 = 安装包 + latest.json
rem ============================================================
setlocal
cd /d %~dp0..

echo [1/4] 构建前端...
pushd frontend
call npm run build || goto :fail
popd

echo [2/4] 打包 SciPlat.exe（PyInstaller + pywebview）...
call .venv\Scripts\python.exe -m PyInstaller desktop\backend.spec --noconfirm --distpath backend\dist --workpath backend\build\pyinstaller --clean || goto :fail

echo [3/4] 编译安装包（Inno Setup）...
set "ISCC="
if exist "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" set "ISCC=C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
if exist "D:\Program Files (x86)\Inno Setup 6\ISCC.exe" set "ISCC=D:\Program Files (x86)\Inno Setup 6\ISCC.exe"
if exist "C:\Program Files\Inno Setup 6\ISCC.exe" set "ISCC=C:\Program Files\Inno Setup 6\ISCC.exe"
if not defined ISCC (
  echo 未检测到 Inno Setup，无法生成安装包。 & goto :fail
)
"%ISCC%" scripts\sciplat.iss || goto :fail

echo [4/4] 生成 latest.json（版本单点：config.APP_VERSION）...
call .venv\Scripts\python.exe scripts\gen_latest.py || goto :fail

echo.
echo ============================================================
echo 发布就绪：desktop\release\
echo   安装包：SciPlatSetup-*.exe
echo   latest.json（上传为 Release 资产）
echo 发布说明请编辑 latest.json 的 notes 字段后上传。
echo ============================================================
exit /b 0

:fail
echo.
echo 构建失败，请检查上方错误信息。
exit /b 1
