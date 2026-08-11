@echo off
rem ============================================================
rem 公网对象存储发布示例（阿里云 OSS / 腾讯云 COS）
rem 前置条件：
rem   阿里云：安装并配置 ossutil（https://help.aliyun.com/document_detail/120075.html）
rem   腾讯云：安装并配置 coscli（https://cloud.tencent.com/document/product/436/63143）
rem 使用前请修改下面 BUCKET / ENDPOINT / PREFIX 三项为你的实际值。
rem
rem 流程：生成匹配该存储桶的 latest.json → 上传安装包 + latest.json
rem 更新源 URL（客户端填写）：https://%BUCKET%.%ENDPOINT%/%PREFIX%/latest.json
rem ============================================================
setlocal
cd /d %~dp0..

rem ---- 请按你的账号修改 ----
set "BUCKET=sciplat-update"
set "ENDPOINT=oss-cn-hangzhou.aliyuncs.com"
set "PREFIX=sciplat"
set "TOOL=ossutil"
rem ---------------------------

rem 1) 生成 latest.json（下载 URL 指向本桶；发布说明与强制更新可加参数）
call .venv\Scripts\python.exe scripts\gen_latest.py --url-prefix https://%BUCKET%.%ENDPOINT%/%PREFIX% || goto :fail

rem 2) 上传安装包与版本信息（工具不存在时提示手动上传）
if not exist "backend\dist\SciPlat.exe" (
  echo 未找到 backend\dist\SciPlat.exe，请先运行 build-release.bat & goto :fail
)
for /f "delims=" %%v in ('type desktop\release\latest.json ^| findstr /c:"version"') do set "VER_LINE=%%v"
for /f "tokens=2 delims=:" %%v in ('echo %VER_LINE%') do set "VERSION=%%~v" & goto :ver_ok
:ver_ok
set "VERSION=%VERSION: =%"
set "VERSION=%VERSION:"=%"
set "VERSION=%VERSION:,=%"

where %TOOL% >nul 2>nul
if errorlevel 1 (
  echo 未检测到 %TOOL%，请手动上传以下两个文件到存储桶 %PREFIX%/ 目录：
  echo   desktop\release\SciPlatSetup-%VERSION%.exe
  echo   desktop\release\latest.json
  goto :done
)

echo [上传] 安装包...
%TOOL% cp desktop\release\SciPlatSetup-%VERSION%.exe oss://%BUCKET%/%PREFIX%/ --endpoint %ENDPOINT% || goto :fail
echo [上传] latest.json...
%TOOL% cp desktop\release\latest.json oss://%BUCKET%/%PREFIX%/ --endpoint %ENDPOINT% || goto :fail

:done
echo.
echo ============================================================
echo 发布完成！
echo 客户端更新源 URL：https://%BUCKET%.%ENDPOINT%/%PREFIX%/latest.json
echo （在应用「软件更新 → 更新源设置」中填写即可，一次发布全局生效）
echo ============================================================
exit /b 0

:fail
echo.
echo 发布失败，请检查上方错误信息。
exit /b 1
