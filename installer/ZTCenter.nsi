; ============================================================================
; ZeroTier 中文控制台 —— 合并安装包（官方内核 + 控制台）
;
; 构建：build_setup.bat          产物：dist\ZTCenter-Setup-<版本>.exe
; 测试：build_setup.bat test     产物：dist\ZTCenter-Setup-test.exe（无需管理员，装到 %TEMP%）
;
; 安装内容：
;   1) 官方 ZeroTier One 内核（MSI；已装同版本或更高版本时自动跳过）
;   2) ZTCenter.exe 控制台
;   3) 开始菜单 / 桌面快捷方式、控制面板卸载项
;   4) 可选：开机自启（计划任务，最高权限，登录后静默驻留托盘）
;
; 设计说明：
;   - 不用 taskkill 关闭旧实例，改为「重命名 + 重启后删除」，避免进程占用导致安装中断；
;   - 注册表统一 64 位视图写入，避免落入 WOW6432Node。
; ============================================================================

Unicode true
Var /GLOBAL ZtView
SetCompressor /SOLID lzma
SetCompressorDictSize 32
ShowInstDetails show
ShowUninstDetails show
BrandingText "ZeroTier 中文控制台"

!define APP_NAME      "ZeroTier 中文控制台"
!define APP_VERSION   "1.11.0"
!define APP_EXE       "ZTCenter.exe"
!define ZT_MSI        "ZeroTierOne-1.16.2.msi"
!define ZT_VER        "1.16.2"
!define UNINST_KEY    "Software\Microsoft\Windows\CurrentVersion\Uninstall\ZTCenter"
!define TASK_NAME     "ZTCenter_AutoStart"
!define SM_FOLDER     "$SMPROGRAMS\ZeroTier 中文控制台"

!ifdef TESTBUILD
  !define INSTALL_ROOT "$TEMP\ZTCenterTest"
  RequestExecutionLevel user
!else
  !define INSTALL_ROOT "$PROGRAMFILES64\ZTCenter"
  RequestExecutionLevel admin
!endif

Name "${APP_NAME} ${APP_VERSION}"
!ifdef TESTBUILD
  OutFile "..\dist\ZTCenter-Setup-test.exe"
!else
  OutFile "..\dist\ZTCenter-Setup-${APP_VERSION}.exe"
!endif
InstallDir "${INSTALL_ROOT}"
InstallDirRegKey HKLM "Software\ZTCenter" "InstallDir"

!include "MUI2.nsh"
!include "LogicLib.nsh"
!include "x64.nsh"
!include "WordFunc.nsh"
!insertmacro VersionCompare

!define MUI_ICON "..\build\icon.ico"
!define MUI_WELCOMEFINISHPAGE_BITMAP "..\build\welcome.bmp"
!define MUI_UNICON "..\build\icon.ico"
!define MUI_ABORTWARNING
!define MUI_WELCOMEPAGE_TITLE "安装 ${APP_NAME}"
!define MUI_WELCOMEPAGE_TEXT "本安装包一次性完成以下内容，无需另外安装官方客户端：$\r$\n$\r$\n  1. 官方 ZeroTier One ${ZT_VER} 内核（服务 + 虚拟网卡驱动）$\r$\n  2. ZeroTier 中文控制台$\r$\n  3. 开始菜单 / 桌面快捷方式$\r$\n  4. 可选：开机自启（登录后静默驻留系统托盘）$\r$\n  5. 自动关闭官方自带的托盘图标，只保留本控制台图标$\r$\n$\r$\n下一步可勾选要安装的组件；安装过程会请求管理员权限。"
!define MUI_FINISHPAGE_RUN "$INSTDIR\${APP_EXE}"
!define MUI_FINISHPAGE_RUN_TEXT "立即启动 ${APP_NAME}"
!define MUI_FINISHPAGE_TEXT "安装完成。$\r$\n$\r$\n控制台关闭窗口即最小化到托盘，按 Ctrl + Alt + Z 可随时唤出。$\r$\n开机自启可在「设置 → 启动与后台运行」中随时开关。"

!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_COMPONENTS
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH

!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES

!insertmacro MUI_LANGUAGE "SimpChinese"

; ---------------------------------------------------------------------------
; 查找已安装的 ZeroTier One
;   输出：$R0 = 版本号（空表示未安装）  $R1 = 卸载注册表子键名
; ---------------------------------------------------------------------------
!macro ZT_FIND_BODY
  StrCpy $R0 ""
  StrCpy $R1 ""
  StrCpy $ZtView 0
  StrCpy $R5 0
  ${Do}
    ${If} $R5 == 0
      SetRegView 64
    ${Else}
      SetRegView 32
    ${EndIf}
    StrCpy $R2 0
    ${Do}
      EnumRegKey $R3 HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall" $R2
      ${If} $R3 == ""
        ${ExitDo}
      ${EndIf}
      IntOp $R2 $R2 + 1
      ReadRegStr $R4 HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\$R3" "DisplayName"
      ${If} $R4 == "ZeroTier One"
        ReadRegStr $R0 HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\$R3" "DisplayVersion"
        StrCpy $R1 "$R3"
        StrCpy $ZtView "$R5"
        ${ExitDo}
      ${EndIf}
      ${If} $R2 > 500
        ${ExitDo}
      ${EndIf}
    ${Loop}
    IntOp $R5 $R5 + 1
  ${LoopUntil} $R5 > 1
  SetRegView 64
!macroend

Function FindZeroTier
  !insertmacro ZT_FIND_BODY
FunctionEnd

; ---------------------------------------------------------------------------
Function .onInit
  ${IfNot} ${RunningX64}
    MessageBox MB_ICONSTOP "本程序仅支持 64 位 Windows。"
    Abort
  ${EndIf}
  SetRegView 64

  Call FindZeroTier
  ${If} $R0 != ""
    DetailPrint "检测到已安装 ZeroTier One $R0"
  ${Else}
    DetailPrint "未检测到 ZeroTier One，将安装 ${ZT_VER}"
  ${EndIf}
FunctionEnd

; ---------------------------------------------------------------------------
Section "主程序（必选）" SEC_MAIN
  SectionIn RO
  SetOutPath "$INSTDIR"
  SetOverwrite on

  ; 旧版本可能正在运行：重命名为 .old 后写入新文件，由系统在重启时清理
  ${If} ${FileExists} "$INSTDIR\${APP_EXE}"
    Delete "$INSTDIR\${APP_EXE}.old"
    ClearErrors
    Rename "$INSTDIR\${APP_EXE}" "$INSTDIR\${APP_EXE}.old"
    ${If} ${Errors}
      Delete "$INSTDIR\${APP_EXE}"
    ${Else}
      Delete /REBOOTOK "$INSTDIR\${APP_EXE}.old"
    ${EndIf}
  ${EndIf}

  File "..\dist\${APP_EXE}"
  WriteUninstaller "$INSTDIR\Uninstall.exe"

  CreateDirectory "${SM_FOLDER}"
  CreateShortCut "${SM_FOLDER}\${APP_NAME}.lnk" "$INSTDIR\${APP_EXE}" "" "$INSTDIR\${APP_EXE}" 0 "" "" "ZeroTier 中文控制台"
  CreateShortCut "${SM_FOLDER}\卸载 ${APP_NAME}.lnk" "$INSTDIR\Uninstall.exe"

  ; 标记当前版本支持 --quit（即使应用从未运行过，卸载时也能优雅关闭）
  CreateDirectory "$APPDATA\ZTCenter"
  FileOpen $9 "$APPDATA\ZTCenter\capabilities.json" w
  FileWrite $9 '{"quit_arg": true, "version": "${APP_VERSION}"}'
  FileClose $9

  SetRegView 64
  WriteRegStr HKLM "Software\ZTCenter" "InstallDir" "$INSTDIR"
  WriteRegStr HKLM "${UNINST_KEY}" "DisplayName" "${APP_NAME}"
  WriteRegStr HKLM "${UNINST_KEY}" "DisplayVersion" "${APP_VERSION}"
  WriteRegStr HKLM "${UNINST_KEY}" "Publisher" "ZTCenter"
  WriteRegStr HKLM "${UNINST_KEY}" "DisplayIcon" "$INSTDIR\${APP_EXE}"
  WriteRegStr HKLM "${UNINST_KEY}" "InstallLocation" "$INSTDIR"
  WriteRegStr HKLM "${UNINST_KEY}" "UninstallString" '"$INSTDIR\Uninstall.exe"'
  WriteRegStr HKLM "${UNINST_KEY}" "QuietUninstallString" '"$INSTDIR\Uninstall.exe" /S'
  WriteRegDWORD HKLM "${UNINST_KEY}" "NoModify" 1
  WriteRegDWORD HKLM "${UNINST_KEY}" "NoRepair" 1
SectionEnd

; ---------------------------------------------------------------------------
Section "官方内核 ${ZT_VER}" SEC_CORE
!ifdef TESTBUILD
  DetailPrint "测试构建：跳过官方内核安装。"
!else
  Call FindZeroTier
  ${If} $R0 != ""
    ${VersionCompare} "$R0" "${ZT_VER}" $R7
    ${If} $R7 == 0
      DetailPrint "已安装 ZeroTier One $R0，与目标版本相同，跳过。"
      Goto core_done
    ${ElseIf} $R7 == 1
      DetailPrint "已安装 ZeroTier One $R0（高于 ${ZT_VER}），跳过。"
      Goto core_done
    ${Else}
      DetailPrint "检测到旧版本 $R0，将升级到 ${ZT_VER}。"
    ${EndIf}
  ${EndIf}

  SetOutPath "$INSTDIR"
  File "..\upgrade\${ZT_MSI}"

  DetailPrint "正在安装 ZeroTier One ${ZT_VER}（若出现驱动安装提示，请选择「安装」）…"
  ExecWait 'msiexec /i "$INSTDIR\${ZT_MSI}" /qb /norestart' $R8
  DetailPrint "msiexec 返回码：$R8"

  ${If} $R8 == 0
    DetailPrint "内核安装完成。"
  ${ElseIf} $R8 == 3010
    DetailPrint "内核安装完成，系统提示需要重启。"
  ${Else}
    MessageBox MB_RETRYCANCEL|MB_ICONEXCLAMATION \
      "官方内核静默安装未成功（返回码 $R8）。$\r$\n$\r$\n是否改用官方安装向导重试？$\r$\n（选择「取消」将跳过内核安装，控制台需你稍后手动安装内核）" \
      IDRETRY core_retry
    Goto core_done
    core_retry:
      ExecWait 'msiexec /i "$INSTDIR\${ZT_MSI}" /norestart' $R8
      ${If} $R8 == 0
        DetailPrint "官方向导安装完成。"
      ${ElseIf} $R8 == 3010
        DetailPrint "官方向导安装完成，需要重启。"
      ${Else}
        MessageBox MB_ICONEXCLAMATION "内核仍安装失败（返回码 $R8）。可稍后手动运行 $INSTDIR\${ZT_MSI} 安装。"
      ${EndIf}
  ${EndIf}

  ; 官方内核自带托盘 UI（zerotier_desktop_ui.exe），图标与本控制台重复，安装后立即关闭
  DetailPrint "关闭官方 ZeroTier 托盘 UI…"
  ExecWait '"$SYSDIR\taskkill.exe" /IM zerotier_desktop_ui.exe /F' $0
  DeleteRegValue HKLM "Software\Microsoft\Windows\CurrentVersion\Run" "ZeroTier One"
  DeleteRegValue HKLM "Software\WOW6432Node\Microsoft\Windows\CurrentVersion\Run" "ZeroTier One"
  DeleteRegValue HKCU "Software\Microsoft\Windows\CurrentVersion\Run" "ZeroTier One"

  core_done:
!endif
SectionEnd

; ---------------------------------------------------------------------------
Section "开机自启" SEC_AUTOSTART
!ifdef TESTBUILD
  DetailPrint "测试构建：跳过开机自启计划任务。"
!else
  ; 用临时批处理规避 schtasks 参数的嵌套引号问题
  FileOpen $9 "$TEMP\zt_autostart.bat" w
  FileWrite $9 '@echo off$\r$\n'
  FileWrite $9 'schtasks /Create /TN "${TASK_NAME}" /TR "\"$INSTDIR\${APP_EXE}\" --silent" /SC ONLOGON /RL HIGHEST /F$\r$\n'
  FileClose $9
  ExecWait '"$TEMP\zt_autostart.bat"' $0
  DetailPrint "开机自启计划任务返回码：$0"
  Delete "$TEMP\zt_autostart.bat"
!endif
SectionEnd

; ---------------------------------------------------------------------------
Section "桌面快捷方式" SEC_DESKTOP
  CreateShortCut "$DESKTOP\${APP_NAME}.lnk" "$INSTDIR\${APP_EXE}" "" "$INSTDIR\${APP_EXE}" 0 "" "" "ZeroTier 中文控制台"
SectionEnd

!insertmacro MUI_FUNCTION_DESCRIPTION_BEGIN
  !insertmacro MUI_DESCRIPTION_TEXT ${SEC_MAIN}      "控制台主程序：中文界面、网络标签、planet 与 MOON 管理、托盘驻留、全局热键。"
  !insertmacro MUI_DESCRIPTION_TEXT ${SEC_CORE}      "官方 ZeroTier One ${ZT_VER} 内核（Windows 服务 + 虚拟网卡驱动）。已安装同版本或更高版本时自动跳过；未安装时会一并装上，之后无需再装官方客户端。"
  !insertmacro MUI_DESCRIPTION_TEXT ${SEC_AUTOSTART} "登录后以最高权限静默启动控制台（计划任务），不弹 UAC，只在系统托盘显示图标。安装后可在「设置 → 启动与后台运行」中随时关闭。"
  !insertmacro MUI_DESCRIPTION_TEXT ${SEC_DESKTOP}   "在桌面创建快捷方式。"
!insertmacro MUI_FUNCTION_DESCRIPTION_END

; ---------------------------------------------------------------------------
Section "Uninstall"
  SetRegView 64

  ; ProgramData 真实路径（NSIS 未内置 $COMMONAPPDATA）
  ReadRegStr $R6 HKLM "SOFTWARE\Microsoft\Windows\CurrentVersion\Explorer\Shell Folders" "Common AppData"
  ${If} $R6 == ""
    StrCpy $R6 "C://ProgramData"
  ${EndIf}

  ; 1) 结束相关进程（本控制台 + 官方托盘 UI）
  DetailPrint "请求控制台退出…"
  ; 仅当程序支持 --quit（由应用启动时写入的能力标记判定）才调用，
  ; 避免旧版本把 --quit 当作正常启动而阻塞卸载。
  ${If} ${FileExists} "$APPDATA\ZTCenter\capabilities.json"
  ${AndIf} ${FileExists} "$INSTDIR\${APP_EXE}"
    ExecWait '"$INSTDIR\${APP_EXE}" --quit' $0
  ${EndIf}
  ExecWait '"$SYSDIR\taskkill.exe" /IM ${APP_EXE} /F' $0
  ExecWait '"$SYSDIR\taskkill.exe" /IM zerotier_desktop_ui.exe /F' $0

  ; 2) 移除开机自启计划任务与注册表 Run 项
!ifndef TESTBUILD
  FileOpen $9 "$TEMP\zt_autostart_del.bat" w
  FileWrite $9 '@echo off$\r$\n'
  FileWrite $9 'schtasks /Delete /TN "${TASK_NAME}" /F >nul 2>&1$\r$\n'
  FileClose $9
  ExecWait '"$TEMP\zt_autostart_del.bat"' $0
  Delete "$TEMP\zt_autostart_del.bat"
!endif
  DeleteRegValue HKCU "Software\Microsoft\Windows\CurrentVersion\Run" "ZTCenter"
  DeleteRegValue HKLM "Software\Microsoft\Windows\CurrentVersion\Run" "ZeroTier One"
  DeleteRegValue HKLM "Software\WOW6432Node\Microsoft\Windows\CurrentVersion\Run" "ZeroTier One"

  ; 3) 一并卸载官方 ZeroTier One 内核（不再询问，避免残留服务与驱动）
  Call un.FindZeroTier
  ${If} $R0 != ""
    DetailPrint "正在卸载官方 ZeroTier One 内核（$R0）…"
    ; 必须在「找到该键时所在的注册表视图」里读取，否则会读空（v1.3.0 的 bug）
    ${If} $ZtView == 1
      SetRegView 32
    ${Else}
      SetRegView 64
    ${EndIf}
    ReadRegStr $R9 HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\$R1" "QuietUninstallString"
    ${If} $R9 == ""
      ReadRegStr $R9 HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\$R1" "UninstallString"
    ${EndIf}
    SetRegView 64
    ${If} $R9 == ""
      ; 兜底：换另一视图再试
      ${If} $ZtView == 1
        SetRegView 64
      ${Else}
        SetRegView 32
      ${EndIf}
      ReadRegStr $R9 HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\$R1" "UninstallString"
      SetRegView 64
    ${EndIf}
    ${If} $R9 != ""
      ExecWait '$R9 /qb /norestart' $R8
      DetailPrint "内核卸载返回码：$R8"
    ${Else}
      MessageBox MB_ICONEXCLAMATION "未能读取 ZeroTier One（$R0）的卸载命令，请到「设置 → 应用」中手动卸载。"
    ${EndIf}
  ${Else}
    DetailPrint "未检测到官方内核，跳过。"
  ${EndIf}

  ; 清理官方 MSI 卸载后残留的包装脚本与空目录
  Delete "$PROGRAMFILES32\ZeroTier\One\zerotier-cli.bat"
  Delete "$PROGRAMFILES32\ZeroTier\One\zerotier-idtool.bat"
  RMDir "$PROGRAMFILES32\ZeroTier\One"
  RMDir "$PROGRAMFILES32\ZeroTier"
  Delete "$PROGRAMFILES64\ZeroTier\One\zerotier-cli.bat"
  Delete "$PROGRAMFILES64\ZeroTier\One\zerotier-idtool.bat"
  RMDir "$PROGRAMFILES64\ZeroTier\One"
  RMDir "$PROGRAMFILES64\ZeroTier"

  ; 4) 询问是否删除节点身份与网络配置（删除后重装会生成新的节点 ID，不可恢复）
  IfSilent keep_data
  MessageBox MB_YESNO|MB_ICONEXCLAMATION|MB_DEFBUTTON1 \
    "是否同时删除 ZeroTier 的节点身份与网络配置？$\r$\n$\r$\n涉及目录：$R6\ZeroTier（identity、planet、moons、已加入网络）$\r$\n$\r$\n选择「是」将彻底清理，重装后节点 ID 会变化且无法恢复；$\r$\n选择「否」则保留这些配置，便于日后重装沿用同一节点 ID。" \
    IDNO keep_data
  RMDir /r "$R6\ZeroTier"
  keep_data:

  ; 5) 删除本控制台数据（标签、设置、planet/moon 备份、下载的安装包）
  RMDir /r "$APPDATA\ZTCenter"

  ; 6) 删除程序文件与快捷方式
  Delete "$INSTDIR\${APP_EXE}"
  Delete /REBOOTOK "$INSTDIR\${APP_EXE}"
  Delete /REBOOTOK "$INSTDIR\${APP_EXE}.old"
  Delete "$INSTDIR\${ZT_MSI}"
  Delete "$INSTDIR\Uninstall.exe"
  RMDir /r "$INSTDIR"

  Delete "${SM_FOLDER}\${APP_NAME}.lnk"
  Delete "${SM_FOLDER}\卸载 ${APP_NAME}.lnk"
  RMDir "${SM_FOLDER}"
  Delete "$DESKTOP\${APP_NAME}.lnk"

  DeleteRegKey HKLM "${UNINST_KEY}"
  DeleteRegKey HKLM "Software\ZTCenter"
SectionEnd

Function un.FindZeroTier
  !insertmacro ZT_FIND_BODY
FunctionEnd
