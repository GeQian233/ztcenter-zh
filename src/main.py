"""ZTCenter 启动入口。

用法：
    python main.py              # 正常启动（自动请求管理员权限）
    python main.py --silent     # 静默启动，仅托盘
    python main.py --demo       # 演示模式（无需管理员，使用模拟数据）
    python main.py --no-elevate # 不自动提权
"""
from __future__ import annotations

import argparse
import ctypes
import socket
import sys
import threading
from pathlib import Path


def _enable_dpi_awareness() -> None:
    """必须在创建 Tk 窗口前启用，否则 150% 缩放下界面会被放大并裁切。"""
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)  # PER_MONITOR_AWARE
        return
    except Exception:
        pass
    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass


_enable_dpi_awareness()


def _log_startup(args) -> None:
    """记录启动环境，便于排查问题。"""
    import datetime

    try:
        from core import config as _cfg

        aware = ctypes.c_int(0)
        try:
            ctypes.windll.shcore.GetProcessDpiAwareness(None, ctypes.byref(aware))
        except Exception:
            pass
        with open(_cfg.LOG_FILE, "a", encoding="utf-8") as f:
            f.write(
                f"[{datetime.datetime.now():%Y-%m-%d %H:%M:%S}] start silent={args.silent} "
                f"demo={args.demo} admin={bool(ctypes.windll.shell32.IsUserAnAdmin())} "
                f"dpi_awareness={aware.value}\n"
            )
    except Exception:
        pass

if not getattr(sys, "frozen", False):
    sys.path.insert(0, str(Path(__file__).resolve().parent))

from core import config, syswin  # noqa: E402
from core.labels import LabelStore  # noqa: E402
from core.ztapi import DemoZTApi, ZTApi  # noqa: E402
from ui.app import App  # noqa: E402
from ui.tray import TrayIcon  # noqa: E402


def send_ipc(command: bytes) -> bool:
    """向已运行实例发送单实例指令（show / quit）。"""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(1)
        s.sendto(command, ("127.0.0.1", config.IPC_PORT))
        s.close()
        return True
    except Exception:
        return False


def signal_existing() -> None:
    send_ipc(b"show")


def instance_alive() -> bool:
    """通过单实例互斥体判断是否仍有实例在运行。"""
    from ctypes import wintypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.OpenMutexW.restype = wintypes.HANDLE
    handle = kernel32.OpenMutexW(0x00100000, False, config.MUTEX_NAME)
    if handle:
        kernel32.CloseHandle(handle)
        return True
    return False


def request_quit(timeout: float = 5.0) -> None:
    """请求已运行实例优雅退出（卸载程序调用，确保托盘图标被正常移除）。"""
    import time

    if not instance_alive():
        return
    send_ipc(b"quit")
    end = time.time() + timeout
    while time.time() < end:
        if not instance_alive():
            return
        time.sleep(0.2)


def start_ipc(app: App) -> None:
    def worker() -> None:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s.bind(("127.0.0.1", config.IPC_PORT))
        except Exception:
            return
        while True:
            try:
                data, _ = s.recvfrom(64)
            except Exception:
                break
            if data == b"show":
                app.dispatch.call(app.show_window)
            elif data == b"quit":
                app.dispatch.call(app.quit_app)

    threading.Thread(target=worker, daemon=True, name="ipc").start()


def _write_capabilities() -> None:
    """写入能力标记，供卸载程序判断是否支持 `--quit` 优雅退出。"""
    import json

    try:
        (config.DATA_DIR / "capabilities.json").write_text(
            json.dumps({"quit_arg": True, "version": config.APP_VERSION}, ensure_ascii=False),
            encoding="utf-8",
        )
    except Exception:
        pass


def ask_elevate() -> bool:
    import ctypes

    text = (
        "ZeroTier 控制台需要管理员权限，原因如下：\n\n"
        "1. 读取 ZeroTier 服务的本地鉴权令牌（authtoken.secret）；\n"
        "2. 替换根节点（planet）并重启 ZeroTier 服务。\n\n"
        "是否以管理员身份重新启动？\n（选择「否」将以受限模式运行，只能查看界面）"
    )
    MB_YESNO, MB_ICONWARNING, MB_SETFOREGROUND = 0x04, 0x30, 0x10000
    rc = ctypes.windll.user32.MessageBoxW(0, text, config.APP_NAME, MB_YESNO | MB_ICONWARNING | MB_SETFOREGROUND)
    return rc == 6


def main() -> None:
    parser = argparse.ArgumentParser(description=config.APP_NAME)
    parser.add_argument("--silent", action="store_true", help="静默启动（仅托盘）")
    parser.add_argument("--demo", action="store_true", help="演示模式（模拟数据）")
    parser.add_argument("--no-elevate", action="store_true", help="不自动提权")
    parser.add_argument("--page", default="", help="启动后直接打开指定页面（开发调试用）")
    parser.add_argument("--quit", action="store_true", help="让已运行的实例退出（卸载程序调用）")
    args, _unknown = parser.parse_known_args()
    _log_startup(args)

    if args.quit:
        request_quit()
        return

    if not syswin.ensure_single_instance():
        signal_existing()
        return

    if not args.demo and not args.no_elevate and not syswin.is_admin():
        if args.silent:
            pass  # 开机自启时静默运行，受限模式下仅显示界面
        elif ask_elevate():
            if syswin.elevate(["--no-elevate"]):
                return

    settings = config.load_settings()
    _write_capabilities()
    first_run = not config.SETTINGS_FILE.exists()
    labels = LabelStore()
    api = DemoZTApi() if args.demo else ZTApi()

    from ui.scaling import apply as apply_scaling

    apply_scaling(settings)

    app = App(api, labels, settings, demo=args.demo)

    # 彻底隐藏模式启动时不创建托盘图标（热键 / 重新运行程序仍可唤出）
    if settings.get("hide_mode") != "none":
        tray = TrayIcon(app)
        tray.start()
        app.tray = tray

    if settings.get("hotkey_enabled", True):
        syswin.start_hotkey_listener(lambda: app.dispatch.call(app.show_window))

    start_ipc(app)

    if args.page:
        app.show_page(args.page)

    # --silent（开机自启）不显示主窗口；手动启动默认显示窗口
    if args.silent or settings.get("start_minimized", False):
        app.withdraw()

    try:
        app.mainloop()
    finally:
        try:
            app._remove_tray()
        except Exception:
            pass


if __name__ == "__main__":
    main()
