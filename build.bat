@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"

echo [1/3] 生成图标...
".venv\Scripts\python.exe" tools\make_icon.py || goto :err

echo [2/3] 打包单文件 exe（首次约需 1-3 分钟）...
echo       嵌入 requireAdministrator 清单：双击即请求管理员权限
".venv\Scripts\python.exe" -m PyInstaller --noconfirm --clean --onefile --windowed ^
  --name ZTCenter ^
  --uac-admin ^
  --icon build\icon.ico ^
  --paths src ^
  --collect-all customtkinter ^
  --hidden-import pystray._win32 ^
  --hidden-import PIL.Image ^
  --hidden-import PIL.ImageDraw ^
  --exclude-module numpy ^
  --exclude-module matplotlib ^
  src\main.py || goto :err

echo [3/3] 完成：dist\ZTCenter.exe
dir dist\ZTCenter.exe
exit /b 0

:err
echo 构建失败，请检查上方日志。
exit /b 1
