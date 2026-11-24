"""主窗口：侧边栏导航 + 内容区 + 后台轮询刷新。"""
from __future__ import annotations

import datetime
import queue
import threading
import traceback

import customtkinter as ctk

from core import config, planet, syswin, version
from core.peer_labels import PeerLabelStore
from core.network_order import NetworkOrderStore
from core.peer_order import PeerOrderStore
from core.ztapi import ZTError

from . import theme
from .pages.networks import NetworksPage
from .pages.overview import OverviewPage
from .pages.planet import PlanetPage
from .pages.settings import SettingsPage
from .pages.tags import TagsPage
from .widgets import Pill

PAGES = [
    ("overview", "◈", "概览", "节点与网络总览"),
    ("networks", "⌘", "网络管理", "加入、配置与退出网络"),
    ("tags", "◇", "标签管理", "为网络命名、着色与分组"),
    ("planet", "◎", "根节点", "planet 替换、备份与恢复"),
    ("settings", "⚙", "设置", "开机自启、后台运行与外观"),
]


class Dispatcher:
    """线程安全地把回调排队到 Tk 主线程执行（托盘、热键、后台线程共用）。"""

    def __init__(self, root, interval_ms: int = 80):
        self._root = root
        self._q: queue.Queue = queue.Queue()
        self._interval = interval_ms
        self._alive = True
        self._root.after(self._interval, self._tick)

    def call(self, fn) -> None:
        if self._alive:
            self._q.put(fn)

    def stop(self) -> None:
        self._alive = False

    def _tick(self) -> None:
        if not self._alive:
            return
        for _ in range(20):
            try:
                fn = self._q.get_nowait()
            except queue.Empty:
                break
            try:
                fn()
            except Exception:
                pass
        try:
            self._root.after(self._interval, self._tick)
        except Exception:
            self._alive = False


class App(ctk.CTk):
    def __init__(self, api, labels, settings: dict, demo: bool = False):
        theme.set_mode(settings.get("theme", "light"))
        super().__init__(fg_color=theme.C()["bg"])
        self.api = api
        self.labels = labels
        self.peer_labels = PeerLabelStore()
        self.peer_order = PeerOrderStore()
        self.net_order = NetworkOrderStore()
        self.settings = settings
        self.demo = demo
        self.summary: dict | None = None
        self.last_error: str | None = None
        self.tray = None
        self._polling = False
        self._tick_after = None
        self._pages: dict[str, ctk.CTkFrame] = {}
        self._nav_buttons: dict[str, ctk.CTkButton] = {}
        self._current_page = ""

        self.title(config.APP_NAME)
        self._fit_window()
        self.protocol("WM_DELETE_WINDOW", self.on_close)
        self._set_icon()
        self.dispatch = Dispatcher(self)

        self.grid_columnconfigure(0, weight=0)
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        self._build_sidebar()
        self._build_main()
        self.show_page(settings.get("last_page", "overview"))

        self.after(150, self.poll)
        self.after(300, self._schedule_tick)
        self.after(1500, self._maybe_suppress_official_ui)

    # ------------------------------------------------------------------ #
    def _fit_window(self) -> None:
        """按屏幕物理尺寸与 DPI 缩放自适应窗口大小，避免高缩放下内容被裁切。"""
        try:
            from customtkinter import ScalingTracker

            scale = float(ScalingTracker.get_widget_scaling(self)) or 1.0
        except Exception:
            scale = 1.0
        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        max_w = max(880.0, (sw - 40 * scale) / scale)
        max_h = max(580.0, (sh - 110 * scale) / scale)
        self._logical_size = (int(min(1180, max_w)), int(min(772, max_h)))
        w, h = self._logical_size
        self.geometry(f"{w}x{h}")
        self.minsize(int(min(960, w)), int(min(600, h)))
        self.after(60, lambda: self._center(scale))

    def _center(self, scale: float) -> None:
        try:
            w, h = self._logical_size
            sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
            x = int((sw - w * scale) / 2)
            y = int((sh - h * scale) / 2.6)
            self.geometry(f"+{max(0, x)}+{max(0, y)}")
        except Exception:
            pass

    def _set_icon(self) -> None:
        try:
            from ui.tray import make_icon_image

            img = make_icon_image(64, theme.C()["accent"])
            self._icon_photo = ctk.CTkImage(light_image=img, dark_image=img, size=(32, 32))
            self.iconphoto(True, self._icon_photo)
        except Exception:
            pass

    # ------------------------------------------------------------------ #
    # 侧边栏
    # ------------------------------------------------------------------ #
    def _build_sidebar(self) -> None:
        c = theme.C()
        bar = ctk.CTkFrame(self, width=228, corner_radius=0, fg_color=c["sidebar"])
        bar.grid(row=0, column=0, sticky="nsw")
        bar.grid_propagate(False)
        bar.grid_rowconfigure(2, weight=1)
        self.sidebar = bar

        brand = ctk.CTkFrame(bar, fg_color="transparent")
        brand.grid(row=0, column=0, sticky="ew", padx=20, pady=(22, 6))
        ctk.CTkLabel(brand, text="ZeroTier", font=theme.font(19, "bold"),
                     text_color=c["text"], anchor="w").pack(anchor="w")
        ctk.CTkLabel(brand, text="中文控制台", font=theme.font(12),
                     text_color=c["text_faint"], anchor="w").pack(anchor="w")

        nav = ctk.CTkFrame(bar, fg_color="transparent")
        nav.grid(row=1, column=0, sticky="ew", padx=12, pady=(16, 0))
        for key, glyph, label, _sub in PAGES:
            btn = ctk.CTkButton(
                nav,
                text=f"  {glyph}   {label}",
                anchor="w",
                height=40,
                corner_radius=9,
                fg_color="transparent",
                hover_color=c["nav_hover"],
                text_color=c["text_muted"],
                font=theme.font(13),
                command=lambda k=key: self.show_page(k),
            )
            btn.pack(fill="x", pady=2)
            self._nav_buttons[key] = btn

        footer = ctk.CTkFrame(bar, fg_color="transparent")
        footer.grid(row=3, column=0, sticky="ew", padx=18, pady=(0, 18))
        self.footer_node = ctk.CTkLabel(footer, text="节点 ID  —", font=theme.font(11),
                                        text_color=c["text_faint"], anchor="w")
        self.footer_node.pack(anchor="w")
        self.footer_service = Pill(footer, "服务检测中", fg=c["text_muted"], bg=c["card_alt"])
        self.footer_service.pack(anchor="w", pady=(8, 0))
        self.footer_ver = ctk.CTkLabel(
            footer,
            text=f"内核 —  ·  控制台 v{config.APP_VERSION}" + ("  ·  演示模式" if self.demo else ""),
            font=theme.font(10), text_color=c["text_faint"], anchor="w",
        )
        self.footer_ver.pack(anchor="w", pady=(8, 0))

    # ------------------------------------------------------------------ #
    # 主区域
    # ------------------------------------------------------------------ #
    def _build_main(self) -> None:
        c = theme.C()
        main = ctk.CTkFrame(self, fg_color=c["bg"], corner_radius=0)
        main.grid(row=0, column=1, sticky="nsew")
        main.grid_columnconfigure(0, weight=1)
        main.grid_rowconfigure(1, weight=1)
        self.main = main

        header = ctk.CTkFrame(main, fg_color="transparent", height=76)
        header.grid(row=0, column=0, sticky="ew", padx=24, pady=(20, 6))
        header.grid_columnconfigure(0, weight=1)
        self.header_title = ctk.CTkLabel(header, text="概览", font=theme.font(21, "bold"),
                                         text_color=c["text"], anchor="w")
        self.header_title.grid(row=0, column=0, sticky="w")
        self.header_sub = ctk.CTkLabel(header, text="", font=theme.font(12),
                                       text_color=c["text_muted"], anchor="w")
        self.header_sub.grid(row=1, column=0, sticky="w", pady=(2, 0))

        actions = ctk.CTkFrame(header, fg_color="transparent")
        actions.grid(row=0, column=1, rowspan=2, sticky="e")
        self.header_status = Pill(actions, "检测中", fg=c["text_muted"], bg=c["card_alt"])
        self.header_status.pack(side="left", padx=(0, 10))
        ctk.CTkButton(actions, text="刷新", width=64, height=32, corner_radius=8,
                      fg_color=c["card"], hover_color=c["nav_hover"], text_color=c["text"],
                      border_width=1, border_color=c["border"], font=theme.font(12),
                      command=self.poll).pack(side="left", padx=4)
        ctk.CTkButton(actions, text="隐藏", width=64, height=32, corner_radius=8,
                      fg_color=c["card"], hover_color=c["nav_hover"], text_color=c["text"],
                      border_width=1, border_color=c["border"], font=theme.font(12),
                      command=self.hide_window).pack(side="left", padx=4)

        self.container = ctk.CTkFrame(main, fg_color="transparent")
        self.container.grid(row=1, column=0, sticky="nsew", padx=18, pady=(0, 18))
        self.container.grid_rowconfigure(0, weight=1)
        self.container.grid_columnconfigure(0, weight=1)

        self._toast = ctk.CTkLabel(self.container, text="", font=theme.font(12),
                                   fg_color=c["text"], text_color=c["card"],
                                   corner_radius=8, height=32)
        self._toast_after = None

    # ------------------------------------------------------------------ #
    # 页面切换
    # ------------------------------------------------------------------ #
    def restart_service(self) -> None:
        """重启 ZeroTier 服务；未提权时引导以管理员身份重启。"""
        if not syswin.is_admin():
            from ui.dialogs import confirm

            if confirm(self, "需要管理员权限",
                       "重启 ZeroTier 服务需要管理员权限。\n\n"
                       "是否以管理员身份重新启动本程序？（当前程序会退出，随后弹出 UAC 提示）",
                       ok_text="以管理员身份重启"):
                if syswin.elevate():
                    self.quit_app()
                else:
                    self.toast("提权请求被取消", "warn")
            return
        self.toast("正在重启 ZeroTier 服务…")
        try:
            self.update_idletasks()
        except Exception:
            pass
        ok, msg = syswin.service_restart()
        self.toast(msg, "ok" if ok else "err")
        self.poll()

    def apply_ui_scale(self, mode: str) -> None:
        """应用界面缩放（重建界面并重新适配窗口尺寸）。"""
        from ui import scaling

        self.settings["ui_scale"] = mode
        config.save_settings(self.settings)
        factor = scaling.apply(self.settings)
        c = theme.C()
        self.configure(fg_color=c["bg"])
        for w in list(self.winfo_children()):
            w.destroy()
        self._pages.clear()
        self._nav_buttons.clear()
        self._build_sidebar()
        self._build_main()
        self._fit_window()
        self.show_page(self.settings.get("last_page", "overview"))
        self._apply(self.summary, self.last_error)
        self.toast(f"界面缩放已应用：{scaling.LABELS.get(mode, mode)}（{factor:.2f}x）", "ok")

    def show_page(self, key: str) -> None:
        if key not in dict((p[0], p) for p in PAGES):
            key = "overview"
        c = theme.C()
        for k, btn in self._nav_buttons.items():
            if k == key:
                btn.configure(fg_color=c["nav_active"], text_color=c["accent"],
                              font=theme.font(13, "bold"))
            else:
                btn.configure(fg_color="transparent", text_color=c["text_muted"],
                              font=theme.font(13))

        page = self._pages.get(key)
        if page is None:
            page = self._create_page(key)
            page.grid(row=0, column=0, sticky="nsew")
            self._pages[key] = page
        for k, p in self._pages.items():
            if k != key:
                p.grid_remove()
        page.grid()
        page.tkraise()
        self._current_page = key
        self.settings["last_page"] = key
        config.save_settings(self.settings)
        for k, _g, label, sub in PAGES:
            if k == key:
                self.header_title.configure(text=label)
                self.header_sub.configure(text=sub)
        try:
            page.refresh()
        except Exception:
            pass

    def _create_page(self, key: str) -> ctk.CTkFrame:
        mapping = {
            "overview": OverviewPage,
            "networks": NetworksPage,
            "tags": TagsPage,
            "planet": PlanetPage,
            "settings": SettingsPage,
        }
        return mapping[key](self.container, self)

    # ------------------------------------------------------------------ #
    # 数据刷新
    # ------------------------------------------------------------------ #
    def poll(self) -> None:
        if self._polling:
            return
        self._polling = True

        def worker() -> None:
            data, err = None, None
            try:
                data = self.api.summary()
            except ZTError as exc:
                err = f"{exc}"
            except Exception:
                err = "未知错误：" + traceback.format_exc(limit=1)
            self.dispatch.call(lambda: self._apply(data, err))

        threading.Thread(target=worker, daemon=True, name="poll").start()

    def _apply(self, data, err) -> None:
        self._polling = False
        self.summary = data
        self.last_error = err
        text, fg, bg = self._compute_status(data, err)
        self.header_status.restyle(text, fg, bg)
        self.footer_service.restyle(text, fg, bg)
        if data:
            self.footer_node.configure(text=f"节点 ID  {data['status'].get('address', '—')}")
        self._update_footer_version(data)
        page = self._pages.get(self._current_page)
        if page is not None:
            try:
                page.refresh()
            except Exception:
                pass

    def _compute_status(self, data, err) -> tuple[str, str, str]:
        """左下角 / 头部状态：优先显示根节点归属（官方/自定义）+ 在线状态。

        判定顺序刻意把「本地 API 是否可用」放在前面：只要 API 有数据，
        服务必然在运行，此时直接给出归属与在线态，不再依赖 SCM 查询结果
        （避免出现「服务未知」这类无信息量的文案）。
        """
        c = theme.C()

        # 1) 内核文件缺失可无条件判定
        if not version.kernel_installed():
            return "内核未安装", c["danger"], c["danger_soft"]

        # 2) API 可用：服务在运行 → 归属 + 在线状态
        if data is not None and not err:
            kind = planet.current_kind()
            if kind in ("missing", "invalid"):
                return planet.kind_text(kind), c["danger"], c["danger_soft"]

            online = bool(data["status"].get("online"))
            base = "官方" if kind == "official" else "自定义"
            text = f"{base}-{'在线' if online else '离线'}"

            # 追加联机方式（P2P / 中继），仅统计成员节点
            try:
                from core import peers as _peers

                mode = _peers.mode_short(
                    _peers.connection_mode(data.get("peers"),
                                           str(data["status"].get("address") or "").lower())
                )
                if mode and online:
                    text += f"·{mode}"
            except Exception:
                pass

            # 磁盘 planet 与运行中服务不一致 → 需重启才生效
            try:
                file_id = planet.current_info()["world_id_dec"]  # type: ignore[index]
                run_id = data["status"].get("planetWorldId")
                if isinstance(run_id, int) and run_id and file_id != run_id:
                    text += "·待重启"
            except Exception:
                pass

            if online:
                return text, c["success"], c["success_soft"]
            return text, c["warn"], c["warn_soft"]

        # 3) API 不可用：诊断原因
        if not syswin.is_admin():
            return "需要管理员", c["warn"], c["warn_soft"]

        state = syswin.service_state()
        if state == 0:
            return "服务不可访问", c["danger"], c["danger_soft"]
        if state != syswin.SERVICE_RUNNING:
            label = syswin.STATE_TEXT.get(state, "未知")
            color = c["danger"] if state == syswin.SERVICE_STOPPED else c["warn"]
            soft = c["danger_soft"] if state == syswin.SERVICE_STOPPED else c["warn_soft"]
            return f"服务{label}", color, soft

        return "本地接口异常", c["danger"], c["danger_soft"]

    def _update_footer_version(self, data) -> None:
        """侧边栏底部显示当前内核版本（而不是只显示控制台版本）。"""
        try:
            present = version.kernel_installed()
            runtime = ((data or {}).get("status") or {}).get("version") if present else None
            kernel = (runtime or version.installed_version()) if present else "未安装"
            if present and not kernel:
                kernel = "未知"
            text = f"内核 {kernel}  ·  控制台 v{config.APP_VERSION}"
            if self.demo:
                text += "  ·  演示模式"
            self.footer_ver.configure(text=text)
        except Exception:
            pass

    def _maybe_suppress_official_ui(self) -> None:
        """启动后关闭官方 ZeroTier 托盘 UI（其图标与本控制台重复）。"""
        if not self.settings.get("kill_official_ui", True):
            return
        if not syswin.is_admin():
            return
        threading.Thread(target=syswin.suppress_official_ui, daemon=True,
                         name="suppress-zt-ui").start()

    def _schedule_tick(self) -> None:
        """按设置周期刷新；间隔为 0（关闭）时不再自动刷新。"""
        try:
            interval = int(self.settings.get("refresh_interval", 5) or 0)
        except Exception:
            interval = 5
        if interval <= 0:
            self._tick_after = None
            return
        self.poll()
        self._tick_after = self.after(max(2, interval) * 1000, self._schedule_tick)

    def restart_tick(self) -> None:
        """设置变更后重建刷新定时器（用于从「关闭」切回自动刷新）。"""
        if self._tick_after is not None:
            try:
                self.after_cancel(self._tick_after)
            except Exception:
                pass
            self._tick_after = None
        try:
            interval = int(self.settings.get("refresh_interval", 5) or 0)
        except Exception:
            interval = 5
        if interval <= 0:
            self.poll()  # 关闭自动刷新时，仍立即刷新一次
            return
        self._schedule_tick()

    # ------------------------------------------------------------------ #
    # 提示条
    # ------------------------------------------------------------------ #
    def log(self, message: str) -> None:
        """写入运行日志（界面渲染异常等非致命问题）。"""
        try:
            stamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            with open(config.LOG_FILE, "a", encoding="utf-8") as f:
                f.write(f"[{stamp}] {message}\n")
        except Exception:
            pass

    def toast(self, text: str, kind: str = "info") -> None:
        c = theme.C()
        bg = {"info": c["text"], "ok": c["success"], "warn": c["warn"], "err": c["danger"]}.get(kind, c["text"])
        self._toast.configure(text=f"  {text}  ", fg_color=bg, text_color="#FFFFFF")
        self._toast.place(relx=0.5, rely=0.97, anchor="s")
        self._toast.lift()
        if self._toast_after:
            try:
                self.after_cancel(self._toast_after)
            except Exception:
                pass
        self._toast_after = self.after(2800, lambda: self._toast.place_forget())

    # ------------------------------------------------------------------ #
    # 窗口显隐 / 退出
    # ------------------------------------------------------------------ #
    def hide_mode(self) -> str:
        return "none" if self.settings.get("hide_mode") == "none" else "tray"

    def _ensure_tray(self) -> None:
        """按需创建托盘图标（彻底隐藏模式下可能已被移除）。"""
        if self.tray is not None:
            return
        try:
            from ui.tray import TrayIcon

            tray = TrayIcon(self)
            tray.start()
            self.tray = tray
        except Exception:
            self.tray = None

    def _remove_tray(self) -> None:
        if self.tray is not None:
            try:
                self.tray.stop()
            except Exception:
                pass
            self.tray = None

    def hide_window(self) -> None:
        """按当前隐藏方式隐藏：托盘常驻 / 彻底隐藏（无托盘图标）。"""
        if self.hide_mode() == "none":
            self.hide_completely()
        else:
            self.hide_to_tray()

    def hide_to_tray(self) -> None:
        """隐藏到托盘（同时把隐藏方式记为「托盘」）。"""
        self.settings["hide_mode"] = "tray"
        config.save_settings(self.settings)
        self._ensure_tray()
        self.withdraw()
        if not self.settings.get("hide_tray_hint"):
            self.settings["hide_tray_hint"] = True
            config.save_settings(self.settings)
            if self.tray:
                try:
                    self.tray.notify("已隐藏到系统托盘", f"按 {config.HOTKEY_TEXT} 可随时唤出控制台")
                except Exception:
                    pass

    def hide_completely(self, notify: bool = True) -> None:
        """彻底隐藏：移除托盘图标，仅后台运行。"""
        if notify and self.tray is not None:
            try:
                self.tray.notify(
                    "已彻底隐藏",
                    f"托盘图标已移除，仅在后台运行；按 {config.HOTKEY_TEXT} 或重新运行程序可恢复",
                )
            except Exception:
                pass
        self.withdraw()
        self._remove_tray()
        self.settings["hide_mode"] = "none"
        config.save_settings(self.settings)

    def show_window(self) -> None:
        """唤出界面：恢复窗口并补回托盘图标（隐藏方式偏好保持不变）。"""
        self._ensure_tray()
        self.deiconify()
        self.lift()
        self.focus_force()
        self.after(80, lambda: self.attributes("-topmost", True))
        self.after(400, lambda: self.attributes("-topmost", False))
        self.poll()

    def on_close(self) -> None:
        if self.settings.get("close_to_tray", True):
            self.hide_window()
        else:
            self.quit_app()

    def quit_app(self) -> None:
        config.save_settings(self.settings)
        try:
            self.dispatch.stop()
        except Exception:
            pass
        self._remove_tray()
        try:
            self.destroy()
        except Exception:
            pass

    # ------------------------------------------------------------------ #
    def rebuild_theme(self, mode: str) -> None:
        """切换主题后重建界面。"""
        self.settings["theme"] = mode
        config.save_settings(self.settings)
        theme.set_mode(mode)
        c = theme.C()
        self.configure(fg_color=c["bg"])
        for w in list(self.winfo_children()):
            w.destroy()
        self._pages.clear()
        self._nav_buttons.clear()
        self._build_sidebar()
        self._build_main()
        self.show_page(self.settings.get("last_page", "overview"))
        self._apply(self.summary, self.last_error)
