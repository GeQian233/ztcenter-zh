@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"

echo ============================================================
echo  ZeroTier 中文控制台 - 安装包构建
echo ============================================================

if not exist "tools\nsis\makensis.exe" (
  echo [错误] 未找到 NSIS 编译器 tools\nsis\makensis.exe
  echo        请下载 nsis-3.10.zip 并解压到 tools\nsis\
  exit /b 1
)

if not exist "dist\ZTCenter.exe" (
  echo [提示] 未找到 dist\ZTCenter.exe，先打包主程序...
  call build.bat || exit /b 1
)

if not exist "upgrade\ZeroTierOne-1.16.2.msi" (
  echo [提示] 未找到官方内核安装包，正在尝试下载...
  call fetch_core.bat || (
    echo [错误] 缺少 upgrade\ZeroTierOne-1.16.2.msi，可手动下载后放到该路径
    echo        https://download.zerotier.com/RELEASES/1.16.2/dist/ZeroTierOne.msi
    exit /b 1
  )
)

if /i "%~1"=="test" (
  echo [构建] 测试版（无需管理员，安装到 %%TEMP%%\ZTCenterTest）
  "tools\nsis\makensis.exe" -V3 -DTESTBUILD installer\ZTCenter.nsi || goto :err
  echo 产物：dist\ZTCenter-Setup-test.exe
  echo 验证：dist\ZTCenter-Setup-test.exe /S   然后检查 %%TEMP%%\ZTCenterTest
  echo 卸载：%%TEMP%%\ZTCenterTest\Uninstall.exe /S
  exit /b 0
)

echo [构建] 正式版...
"tools\nsis\makensis.exe" -V3 installer\ZTCenter.nsi || goto :err
echo.
echo 完成，产物：
dir /b dist\ZTCenter-Setup-*.exe
exit /b 0

:err
echo 构建失败，请查看上方日志。
exit /b 1
