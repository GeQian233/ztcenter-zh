"""系统托盘图标与菜单。"""
from __future__ import annotations

import threading

from PIL import Image, ImageDraw

from core import config


def make_icon_image(size: int = 64, color: str = "#4F46E5") -> Image.Image:
    """生成圆角方块 + Z 字形图标。"""
    scale = 4
    s = size * scale
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([0, 0, s - 1, s - 1], radius=int(s * 0.26), fill=color)
    w = max(2, int(s * 0.085))
    pad = int(s * 0.27)
    white = "#FFFFFF"
    # 上横线
    d.line([(pad, pad), (s - pad, pad)], fill=white, width=w)
    # 斜线
    d.line([(s - pad, pad), (pad, s - pad)], fill=white, width=w)
    # 下横线
    d.line([(pad, s - pad), (s - pad, s - pad)], fill=white, width=w)
    return img.resize((size, size), Image.LANCZOS)


class TrayIcon:
    def __init__(self, app):
        self.app = app
        self._icon = None
        self._thread = None

    def start(self) -> None:
        try:
            import pystray
        except Exception:
            return
        image = make_icon_image(64)
        menu = pystray.Menu(
            pystray.MenuItem("显示控制台", lambda: self.app.dispatch.call(self.app.show_window), default=True),
            pystray.MenuItem("刷新状态", lambda: self.app.dispatch.call(self.app.poll)),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("隐藏到托盘", lambda: self.app.dispatch.call(self.app.hide_window)),
            pystray.MenuItem("彻底隐藏（移除托盘图标）",
                             lambda: self.app.dispatch.call(self.app.hide_completely)),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("重启 ZeroTier 服务", self._restart_service),
            pystray.MenuItem("打开配置目录", self._open_home),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("退出", lambda: self.app.dispatch.call(self.app.quit_app)),
        )
        self._icon = pystray.Icon("ZTCenter", image, config.APP_NAME, menu)
        self._thread = threading.Thread(target=self._icon.run, daemon=True, name="tray")
        self._thread.start()

    # 菜单回调运行在托盘线程，统一切回 UI 线程
    def _restart_service(self) -> None:
        self.app.dispatch.call(self.app.restart_service)

    def _open_home(self) -> None:
        from core import syswin

        syswin.open_path(config.ZT_HOME)

    def notify(self, title: str, message: str) -> None:
        if self._icon:
            try:
                self._icon.notify(message, title)
            except Exception:
                pass

    def update_tooltip(self, text: str) -> None:
        if self._icon:
            try:
                self._icon.title = text
            except Exception:
                pass

    def stop(self) -> None:
        if self._icon:
            try:
                self._icon.stop()
            except Exception:
                pass
            self._icon = None
