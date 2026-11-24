@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"

set VER=1.16.2
set OUT=upgrade\ZeroTierOne-%VER%.msi

if exist "%OUT%" (
  echo [跳过] 已存在：%OUT%
  exit /b 0
)

if not exist upgrade mkdir upgrade

echo [下载] ZeroTier One %VER% 官方安装包...
echo        来源：https://download.zerotier.com/RELEASES/%VER%/dist/ZeroTierOne.msi
curl -L --fail --progress-bar -o "%OUT%.part" ^
  "https://download.zerotier.com/RELEASES/%VER%/dist/ZeroTierOne.msi"
if errorlevel 1 (
  echo [失败] 下载失败。请手动下载后重命名放到 %OUT%
  if exist "%OUT%.part" del /q "%OUT%.part"
  exit /b 1
)

move /y "%OUT%.part" "%OUT%" >nul
echo [完成] %OUT%
echo.
echo 提示：该文件属于 ZeroTier, Inc.，不纳入本仓库版本管理（见 THIRD-PARTY-NOTICES.md）。
exit /b 0
