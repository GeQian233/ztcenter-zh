"""Windows 系统能力：提权、服务控制、开机自启、单实例、全局热键、路径操作。

全部通过 ctypes / 系统 API 实现，不依赖 sc.exe 等外部命令（服务控制除外，
服务控制同样走 advapi32，避免受终端安全策略影响）。
"""
from __future__ import annotations

import ctypes
import os
import subprocess
import sys
from ctypes import wintypes
from pathlib import Path

from . import config

CREATE_NO_WINDOW = 0x08000000

# --------------------------------------------------------------------------- #
# 权限
# --------------------------------------------------------------------------- #
def is_admin() -> bool:
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def current_exe_and_args() -> tuple[str, str]:
    """返回 (可执行文件, 需要附加的参数前缀)。区分打包后的 exe 与源码运行。"""
    if getattr(sys, "frozen", False):
        return sys.executable, ""
    script = Path(sys.argv[0]).resolve()
    return sys.executable, f'"{script}"'


def elevate(extra_args: list[str] | None = None) -> bool:
    """以管理员身份重新启动自身，成功返回 True。"""
    exe, prefix = current_exe_and_args()
    args = list(sys.argv[1:] if not getattr(sys, "frozen", False) else sys.argv[1:])
    if extra_args:
        args += extra_args
    params = (prefix + " " if prefix else "") + " ".join(f'"{a}"' if " " in a else a for a in args)
    try:
        rc = ctypes.windll.shell32.ShellExecuteW(None, "runas", exe, params, None, 1)
        return rc > 32
    except Exception:
        return False


def open_path(path: str | Path) -> None:
    try:
        os.startfile(str(path))  # type: ignore[attr-defined]
    except Exception:
        pass


def run_hidden(cmd: list[str], timeout: int = 20) -> tuple[int, str]:
    try:
        p = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            creationflags=CREATE_NO_WINDOW,
            encoding="gbk",
            errors="ignore",
        )
        return p.returncode, (p.stdout or "") + (p.stderr or "")
    except Exception as exc:  # pragma: no cover
        return -1, str(exc)


# --------------------------------------------------------------------------- #
# 服务控制（advapi32）
# --------------------------------------------------------------------------- #
advapi32 = ctypes.WinDLL("advapi32", use_last_error=True)

SC_MANAGER_CONNECT = 0x0001
SERVICE_QUERY_STATUS = 0x0004
SERVICE_START = 0x0010
SERVICE_STOP = 0x0020          # 访问权限（OpenService 用）
SERVICE_INTERROGATE = 0x0080

# ControlService 的第二个参数是「控制码」，不是访问权限；
# 传 0x20 会被 SCM 判为「服务不接受此控件」并返回 ERROR_ACCESS_DENIED(5)。
SERVICE_CONTROL_STOP = 0x00000001

SERVICE_STOPPED = 1
SERVICE_START_PENDING = 2
SERVICE_STOP_PENDING = 3
SERVICE_RUNNING = 4

STATE_TEXT = {
    0: "未知",
    1: "已停止",
    2: "正在启动",
    3: "正在停止",
    4: "运行中",
    5: "正在继续",
    6: "正在暂停",
    7: "已暂停",
}


class SERVICE_STATUS(ctypes.Structure):
    _fields_ = [
        ("dwServiceType", wintypes.DWORD),
        ("dwCurrentState", wintypes.DWORD),
        ("dwControlsAccepted", wintypes.DWORD),
        ("dwWin32ExitCode", wintypes.DWORD),
        ("dwServiceSpecificExitCode", wintypes.DWORD),
        ("dwCheckPoint", wintypes.DWORD),
        ("dwWaitHint", wintypes.DWORD),
    ]

# 必须显式声明签名：默认 restype 为 c_int，64 位下 SC_HANDLE 会被截断，
# 导致 OpenServiceW 收到无效句柄并返回 ERROR_INVALID_HANDLE(6)——表现为
# 「无法打开 ZeroTier 服务（需要管理员权限）」，即使已经提权。
advapi32.OpenSCManagerW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD]
advapi32.OpenSCManagerW.restype = wintypes.HANDLE
advapi32.OpenServiceW.argtypes = [wintypes.HANDLE, wintypes.LPCWSTR, wintypes.DWORD]
advapi32.OpenServiceW.restype = wintypes.HANDLE
advapi32.QueryServiceStatus.argtypes = [wintypes.HANDLE, ctypes.POINTER(SERVICE_STATUS)]
advapi32.QueryServiceStatus.restype = wintypes.BOOL
advapi32.ControlService.argtypes = [wintypes.HANDLE, wintypes.DWORD, ctypes.POINTER(SERVICE_STATUS)]
advapi32.ControlService.restype = wintypes.BOOL
advapi32.StartServiceW.argtypes = [wintypes.HANDLE, wintypes.DWORD,
                                   ctypes.POINTER(wintypes.LPWSTR)]
advapi32.StartServiceW.restype = wintypes.BOOL
advapi32.CloseServiceHandle.argtypes = [wintypes.HANDLE]
advapi32.CloseServiceHandle.restype = wintypes.BOOL

_WINERR_HINT = {
    5: "拒绝访问（需要管理员权限）",
    6: "句柄无效",
    1060: "服务不存在（ZeroTier 未安装或服务名不符）",
    1072: "服务已被标记为删除",
}


def _open_service(access: int):
    ctypes.set_last_error(0)
    scm = advapi32.OpenSCManagerW(None, None, SC_MANAGER_CONNECT)
    if not scm:
        err = ctypes.get_last_error()
        raise OSError(err, f"无法连接服务控制管理器：{_WINERR_HINT.get(err, err)}")
    ctypes.set_last_error(0)
    svc = advapi32.OpenServiceW(scm, config.SERVICE_NAME, access)
    if not svc:
        err = ctypes.get_last_error()
        advapi32.CloseServiceHandle(scm)
        raise OSError(err, f"无法打开 ZeroTier 服务：{_WINERR_HINT.get(err, err)}")
    return scm, svc


def service_state() -> int:
    """返回服务状态码（4=运行中），无法访问返回 0。"""
    try:
        scm, svc = _open_service(SERVICE_QUERY_STATUS)
    except OSError:
        return 0
    try:
        st = SERVICE_STATUS()
        if not advapi32.QueryServiceStatus(svc, ctypes.byref(st)):
            return 0
        return int(st.dwCurrentState)
    finally:
        advapi32.CloseServiceHandle(svc)
        advapi32.CloseServiceHandle(scm)


def service_state_text() -> str:
    state = service_state()
    if state == 0:
        return "需要管理员" if not is_admin() else "无法访问"
    return STATE_TEXT.get(state, "未知")
    return STATE_TEXT.get(service_state(), "未知")


def _wait_for(target: int, timeout: float = 15.0) -> bool:
    import time

    end = time.time() + timeout
    while time.time() < end:
        if service_state() == target:
            return True
        time.sleep(0.35)
    return False


def service_start() -> tuple[bool, str]:
    try:
        scm, svc = _open_service(SERVICE_QUERY_STATUS | SERVICE_START)
    except OSError as exc:
        return False, str(exc)
    try:
        if service_state() == SERVICE_RUNNING:
            return True, "服务已在运行"
        ctypes.set_last_error(0)
        if not advapi32.StartServiceW(svc, 0, None):
            err = ctypes.get_last_error()
            if err != 1056:  # 服务已在运行
                return False, f"启动失败：{_WINERR_HINT.get(err, f'错误码 {err}')}"
        ok = _wait_for(SERVICE_RUNNING)
        return (True, "服务已启动") if ok else (False, "启动超时")
    finally:
        advapi32.CloseServiceHandle(svc)
        advapi32.CloseServiceHandle(scm)


def service_stop() -> tuple[bool, str]:
    try:
        scm, svc = _open_service(SERVICE_QUERY_STATUS | SERVICE_STOP)
    except OSError as exc:
        return False, str(exc)
    try:
        if service_state() == SERVICE_STOPPED:
            return True, "服务已停止"
        st = SERVICE_STATUS()
        ctypes.set_last_error(0)
        if not advapi32.ControlService(svc, SERVICE_CONTROL_STOP, ctypes.byref(st)):
            err = ctypes.get_last_error()
            return False, f"停止失败：{_WINERR_HINT.get(err, f'错误码 {err}')}"
        ok = _wait_for(SERVICE_STOPPED, 20)
        return (True, "服务已停止") if ok else (False, "停止超时")
    finally:
        advapi32.CloseServiceHandle(svc)
        advapi32.CloseServiceHandle(scm)


def service_restart() -> tuple[bool, str]:
    ok, msg = service_stop()
    if not ok:
        return False, msg
    import time

    time.sleep(0.6)
    return service_start()


# --------------------------------------------------------------------------- #
# 单实例
# --------------------------------------------------------------------------- #
_mutex_handle = None


def ensure_single_instance() -> bool:
    """首次运行返回 True；已有实例返回 False。"""
    global _mutex_handle
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateMutexW.argtypes = [wintypes.LPVOID, wintypes.BOOL, wintypes.LPCWSTR]
    kernel32.CreateMutexW.restype = wintypes.HANDLE
    _mutex_handle = kernel32.CreateMutexW(None, False, config.MUTEX_NAME)
    return ctypes.get_last_error() != 183  # ERROR_ALREADY_EXISTS


# --------------------------------------------------------------------------- #
# 开机自启（计划任务，最高权限，登录后静默启动）
# --------------------------------------------------------------------------- #
TASK_NAME = "ZTCenter_AutoStart"


def _startup_command() -> str:
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}" --silent'
    script = Path(sys.argv[0]).resolve()
    pyw = Path(sys.executable).with_name("pythonw.exe")
    runner = pyw if pyw.exists() else Path(sys.executable)
    return f'"{runner}" "{script}" --silent'


def autostart_enabled() -> bool:
    rc, _ = run_hidden(["schtasks", "/Query", "/TN", TASK_NAME])
    if rc == 0:
        return True
    try:
        import winreg

        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run") as k:
            winreg.QueryValueEx(k, config.APP_NAME_EN)
            return True
    except Exception:
        return False


def set_autostart(enable: bool) -> tuple[bool, str]:
    cmd = _startup_command()
    if enable:
        rc, out = run_hidden(
            ["schtasks", "/Create", "/TN", TASK_NAME, "/TR", cmd, "/SC", "ONLOGON",
             "/RL", "HIGHEST", "/F"]
        )
        if rc == 0:
            return True, "已启用开机自启（计划任务，最高权限，无 UAC 弹窗）"
        # 降级到注册表 Run 项（登录时会弹 UAC）
        try:
            import winreg

            with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Run",
                0,
                winreg.KEY_SET_VALUE,
            ) as k:
                winreg.SetValueEx(k, config.APP_NAME_EN, 0, winreg.REG_SZ, cmd)
            return True, "已启用开机自启（注册表方式，登录时可能弹出 UAC 确认）"
        except Exception as exc:
            return False, f"启用失败：{exc}"
    else:
        run_hidden(["schtasks", "/Delete", "/TN", TASK_NAME, "/F"])
        try:
            import winreg

            with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Run",
                0,
                winreg.KEY_SET_VALUE,
            ) as k:
                winreg.DeleteValue(k, config.APP_NAME_EN)
        except Exception:
            pass
        return True, "已关闭开机自启"


# --------------------------------------------------------------------------- #
# 全局热键
# --------------------------------------------------------------------------- #
MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_NOREPEAT = 0x4000
WM_HOTKEY = 0x0312


class MSG(ctypes.Structure):
    _fields_ = [
        ("hwnd", wintypes.HWND),
        ("message", wintypes.UINT),
        ("wParam", wintypes.WPARAM),
        ("lParam", wintypes.LPARAM),
        ("time", wintypes.DWORD),
        ("pt", wintypes.POINT),
    ]


OFFICIAL_UI_EXE = "zerotier_desktop_ui.exe"


def kill_process(image: str) -> bool:
    """按映像名结束进程；进程不存在或失败返回 False。"""
    code, _out = run_hidden(["taskkill", "/IM", image, "/F"])
    return code == 0


def suppress_official_ui() -> tuple[bool, str]:
    """关闭官方 ZeroTier 托盘 UI，并清除其自启项。

    仅结束进程 + 清理 Run 键，不删除、不改名官方文件，因此不影响内核升级与修复安装。
    """
    import winreg

    killed = kill_process(OFFICIAL_UI_EXE)
    removed = 0
    targets = [
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Run"),
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Run"),
        (winreg.HKEY_CURRENT_USER, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Run"),
    ]
    for hive, path in targets:
        try:
            with winreg.OpenKey(hive, path, 0, winreg.KEY_READ | winreg.KEY_SET_VALUE) as key:
                names: list[str] = []
                idx = 0
                while True:
                    try:
                        names.append(winreg.EnumValue(key, idx)[0])
                    except OSError:
                        break
                    idx += 1
                for name in names:
                    try:
                        value = str(winreg.QueryValueEx(key, name)[0]).lower()
                    except Exception:
                        continue
                    if OFFICIAL_UI_EXE in value:
                        try:
                            winreg.DeleteValue(key, name)
                            removed += 1
                        except Exception:
                            pass
        except Exception:
            continue

    if killed or removed:
        return True, f"已关闭官方托盘图标（进程 {1 if killed else 0} 个，自启项 {removed} 个）"
    return False, "官方托盘图标当前未运行"


def start_hotkey_listener(callback) -> bool:
    """在后台线程注册 Ctrl+Alt+Z，按下时回调。"""
    import threading

    user32 = ctypes.WinDLL("user32", use_last_error=True)

    def worker() -> None:
        if not user32.RegisterHotKey(None, 1, MOD_CONTROL | MOD_ALT | MOD_NOREPEAT, ord("Z")):
            return
        msg = MSG()
        while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            if msg.message == WM_HOTKEY and msg.wParam == 1:
                try:
                    callback()
                except Exception:
                    pass

    t = threading.Thread(target=worker, daemon=True, name="hotkey")
    t.start()
    return True
