"""设置页：启动方式、后台运行、外观与服务操作。"""
from __future__ import annotations

import threading
from pathlib import Path

import customtkinter as ctk

from core import config, syswin, version
from ui import theme
from ui.dialogs import confirm
from ui.widgets import Card, Pill, ghost_button, primary_button


class SettingsPage(ctk.CTkFrame):
    def __init__(self, master, app):
        super().__init__(master, fg_color="transparent")
        self.app = app
        self._downloading = False
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)
        self.scroll = ctk.CTkScrollableFrame(self, fg_color="transparent",
                                             scrollbar_button_color=theme.C()["border"])
        self.scroll.grid(row=0, column=0, sticky="nsew", padx=2, pady=2)
        self.scroll.grid_columnconfigure(0, weight=1)
        self._build()

    # ------------------------------------------------------------------ #
    def _build(self) -> None:
        c = theme.C()
        s = self.app.settings
        wrap = ctk.CTkFrame(self.scroll, fg_color="transparent")
        wrap.grid(row=0, column=0, sticky="nsew", padx=4, pady=(2, 12))
        wrap.grid_columnconfigure(0, weight=1)

        # ---------------- 启动与后台 ---------------- #
        card = Card(wrap)
        card.grid(row=0, column=0, sticky="ew")
        head = card.title("启动与后台运行", "让客户端像系统组件一样安静运行")
        admin = syswin.is_admin()
        Pill(head, "管理员权限" if admin else "普通权限",
             fg=c["success"] if admin else c["warn"],
             bg=c["success_soft"] if admin else c["warn_soft"]).pack(side="left", padx=8)

        self._auto_switch = self._switch(card.body, "开机自动启动",
                                         "登录后以最高权限静默启动，不弹出 UAC 窗口",
                                         bool(s.get("autostart")), self._toggle_autostart)
        # 开关初值来自配置文件，随后按实际计划任务/注册表状态校准（安装包可能已创建任务）
        threading.Thread(target=self._sync_autostart, daemon=True, name="autostart-sync").start()
        self._switch(card.body, "启动后不显示窗口",
                     "启动时直接进入后台，按下方「隐藏方式」处理",
                     bool(s.get("start_minimized")), lambda v: self._save("start_minimized", v))
        self._switch(card.body, "关闭窗口时隐藏（不退出）",
                     "点击右上角关闭按钮时隐藏到后台，而不是退出程序",
                     bool(s.get("close_to_tray", True)), lambda v: self._save("close_to_tray", v))
        self._switch(card.body, "启用全局热键",
                     f"{config.HOTKEY_TEXT} 可在任意界面唤出控制台",
                     bool(s.get("hotkey_enabled", True)), lambda v: self._save("hotkey_enabled", v))
        self._switch(card.body, "自动关闭官方 ZeroTier 托盘图标",
                     "官方内核附带自己的托盘 UI（蓝色 Z）；开启后自动结束该进程并清理其自启项，只保留本控制台图标",
                     bool(s.get("kill_official_ui", True)), self._toggle_kill_ui)

        # ---------------- 隐藏方式 ---------------- #
        ctk.CTkFrame(card.body, height=1, fg_color=c["border"]).pack(fill="x", pady=(12, 12))
        row = ctk.CTkFrame(card.body, fg_color="transparent")
        row.pack(fill="x")
        col = ctk.CTkFrame(row, fg_color="transparent")
        col.pack(side="left", fill="x", expand=True)
        ctk.CTkLabel(col, text="隐藏方式", font=theme.font(13), text_color=c["text"],
                     anchor="w").pack(anchor="w")
        ctk.CTkLabel(col, text=f"彻底隐藏会移除托盘图标，仅在后台运行；按 {config.HOTKEY_TEXT} 或重新运行程序即可恢复",
                     font=theme.font(11), text_color=c["text_faint"], anchor="w",
                     justify="left", wraplength=520).pack(anchor="w")

        seg = ctk.CTkFrame(row, fg_color=c["card_alt"], corner_radius=9,
                           border_width=1, border_color=c["border"])
        seg.pack(side="right")
        self._hide_btns: dict[str, ctk.CTkButton] = {}
        for key, label in (("tray", "隐藏到托盘"), ("none", "彻底隐藏")):
            active = self.app.hide_mode() == key
            b = ctk.CTkButton(
                seg, text=label, width=88, height=26, corner_radius=7,
                fg_color=c["accent"] if active else "transparent",
                hover_color=c["accent_hover"] if active else c["nav_hover"],
                text_color="#FFFFFF" if active else c["text_muted"],
                font=theme.font(12, "bold" if active else "normal"),
                command=lambda k=key: self._set_hide_mode(k),
            )
            b.pack(side="left", padx=2, pady=2)
            self._hide_btns[key] = b

        btnrow = ctk.CTkFrame(card.body, fg_color="transparent")
        btnrow.pack(fill="x", pady=(10, 0))
        ghost_button(btnrow, "立即隐藏到托盘", self.app.hide_window, width=126, height=30).pack(
            side="left", padx=(0, 6))
        ghost_button(btnrow, "立即彻底隐藏", self._hide_now, width=126, height=30).pack(side="left")

        if not admin:
            row = ctk.CTkFrame(card.body, fg_color="transparent")
            row.pack(fill="x", pady=(10, 0))
            primary_button(row, "以管理员身份重启", self._elevate, width=150).pack(side="left")
            ctk.CTkLabel(row, text="读取 ZeroTier 令牌、替换根节点、重启服务均需要管理员权限",
                         font=theme.font(11), text_color=c["text_faint"]).pack(side="left", padx=10)

        # ---------------- 外观 ---------------- #
        card2 = Card(wrap)
        card2.grid(row=1, column=0, sticky="ew", pady=(12, 0))
        card2.title("外观与刷新")

        row = ctk.CTkFrame(card2.body, fg_color="transparent")
        row.pack(fill="x", pady=4)
        ctk.CTkLabel(row, text="界面主题", font=theme.font(13), text_color=c["text"],
                     width=120, anchor="w").pack(side="left")
        seg = ctk.CTkFrame(row, fg_color=c["card_alt"], corner_radius=9,
                           border_width=1, border_color=c["border"])
        seg.pack(side="left")
        current = self.app.settings.get("theme", "light")
        for key, label in (("light", "浅色"), ("dark", "深色")):
            active = current == key
            ctk.CTkButton(
                seg, text=label, width=62, height=26, corner_radius=7,
                fg_color=c["accent"] if active else "transparent",
                hover_color=c["accent_hover"] if active else c["nav_hover"],
                text_color="#FFFFFF" if active else c["text_muted"],
                font=theme.font(12, "bold" if active else "normal"),
                command=lambda k=key: self.app.after(60, lambda: self.app.rebuild_theme(k)),
            ).pack(side="left", padx=2, pady=2)

        # 界面缩放
        row_scale = ctk.CTkFrame(card2.body, fg_color="transparent")
        row_scale.pack(fill="x", pady=(8, 4))
        ctk.CTkLabel(row_scale, text="界面缩放", font=theme.font(13), text_color=c["text"],
                     width=120, anchor="w").pack(side="left")
        from ui import scaling as _scaling

        scale_values = list(_scaling.OPTIONS.keys())
        current_scale = _scaling.LABELS.get(str(s.get("ui_scale", "auto")), "跟随系统")
        scale_menu = ctk.CTkOptionMenu(
            row_scale, values=scale_values, width=110, height=30, corner_radius=8,
            fg_color=c["card_alt"], button_color=c["border"], button_hover_color=c["nav_hover"],
            text_color=c["text"], font=theme.font(12), dropdown_font=theme.font(12),
            command=self._set_ui_scale,
        )
        scale_menu.pack(side="left")
        scale_menu.set(current_scale if current_scale in scale_values else "跟随系统")
        ctk.CTkLabel(row_scale, text="跟随系统时按 Windows 显示缩放自动适配 100%~200%",
                     font=theme.font(11), text_color=c["text_faint"]).pack(side="left", padx=(10, 0))

        row2 = ctk.CTkFrame(card2.body, fg_color="transparent")
        row2.pack(fill="x", pady=(8, 4))
        ctk.CTkLabel(row2, text="状态刷新间隔", font=theme.font(13), text_color=c["text"],
                     width=120, anchor="w").pack(side="left")
        values = ["关闭", "3 秒", "5 秒", "10 秒", "30 秒"]
        try:
            iv = int(self.app.settings.get("refresh_interval", 5) or 0)
        except Exception:
            iv = 5
        current = "关闭" if iv <= 0 else f"{iv} 秒"
        menu = ctk.CTkOptionMenu(
            row2, values=values, width=110, height=30, corner_radius=8,
            fg_color=c["card_alt"], button_color=c["border"], button_hover_color=c["nav_hover"],
            text_color=c["text"], font=theme.font(12), dropdown_font=theme.font(12),
            command=self._set_interval,
        )
        menu.pack(side="left")
        menu.set(current if current in values else "5 秒")
        ctk.CTkLabel(row2, text="选择「关闭」后不再自动轮询，仅手动刷新或切换页面时更新",
                     font=theme.font(11), text_color=c["text_faint"]).pack(side="left", padx=(10, 0))

        # ---------------- 版本信息（控制台 / 内核分开） ---------------- #
        kcard = Card(wrap)
        kcard.grid(row=2, column=0, sticky="ew", pady=(12, 0))
        khead = kcard.title("版本信息", "控制台版本与官方内核版本分别显示")
        vinfo = version.status()
        self._kpill = Pill(khead, "", fg=c["text_muted"], bg=c["card_alt"])
        self._kpill.pack(side="left", padx=8)
        self._refresh_kernel_pill(vinfo)

        self._vlabels: dict[str, ctk.CTkLabel] = {}
        rows = (
            ("当前控制台版本", vinfo["control"]),
            ("最新控制台版本", f"{vinfo['control_latest']}（离线分发，无在线更新源）"),
            ("当前内核版本", vinfo["kernel"]),
            ("最新内核版本", vinfo["target"]),
        )
        for key, value in rows:
            row = ctk.CTkFrame(kcard.body, fg_color="transparent")
            row.pack(fill="x", pady=2)
            ctk.CTkLabel(row, text=key, font=theme.font(12), text_color=c["text_muted"],
                         width=118, anchor="w").pack(side="left")
            lab = ctk.CTkLabel(row, text=value, font=ctk.CTkFont(family="Consolas", size=12),
                               text_color=c["text"], anchor="w")
            lab.pack(side="left")
            self._vlabels[key] = lab

        kb = ctk.CTkFrame(kcard.body, fg_color="transparent")
        kb.pack(fill="x", pady=(10, 0))
        installer = version.installer_path()
        self._kbtn = primary_button(kb, f"安装官方 {vinfo['target']}" if installer else "下载安装包",
                                    self._install_core, width=150)
        self._kbtn.pack(side="left", padx=(0, 6))
        ghost_button(kb, "手动选择安装包…", self._pick_installer, width=132).pack(side="left", padx=3)
        ghost_button(kb, "打开官方下载页", self._open_download_page, width=118).pack(side="left", padx=3)

        self._kpath = ctk.CTkLabel(
            kcard.body,
            text=(f"本地安装包：{installer}" if installer else
                  "本地未找到安装包：可点击左侧按钮下载，或手动选择已有的 .msi"),
            font=theme.font(11), text_color=c["text_faint"], anchor="w", justify="left",
            wraplength=740,
        )
        self._kpath.pack(fill="x", pady=(8, 0))
        ctk.CTkLabel(kcard.body,
                     text="升级会重启 ZeroTier 服务并短暂断网；节点身份、已加入网络与 planet 配置均保留。安装完成后请重启本控制台以刷新版本号。",
                     font=theme.font(11), text_color=c["text_faint"], anchor="w",
                     justify="left", wraplength=740).pack(fill="x", pady=(4, 0))

        # ---------------- 服务与目录 ---------------- #
        card3 = Card(wrap)
        card3.grid(row=3, column=0, sticky="ew", pady=(12, 0))
        card3.title("服务与目录")
        btns = ctk.CTkFrame(card3.body, fg_color="transparent")
        btns.pack(fill="x", pady=4)
        ghost_button(btns, "重启 ZeroTier 服务", self._restart_service, width=140).pack(side="left", padx=(0, 6))
        ghost_button(btns, "打开数据目录", lambda: syswin.open_path(config.DATA_DIR), width=110).pack(side="left", padx=3)
        ghost_button(btns, "打开 ZeroTier 目录", lambda: syswin.open_path(config.ZT_HOME), width=140).pack(side="left", padx=3)
        ghost_button(btns, "退出程序", self.app.quit_app, width=90, danger=True).pack(side="left", padx=3)

        # ---------------- 关于 ---------------- #
        card4 = Card(wrap)
        card4.grid(row=4, column=0, sticky="ew", pady=(12, 0))
        card4.title("关于")
        about = (
            f"{config.APP_NAME} v{config.APP_VERSION}\n"
            "基于官方 ZeroTier One 服务（zerotier-one_x64.exe）的本地控制台，"
            "通过官方本地 JSON 接口管理节点与网络，不修改、不替换官方二进制。\n\n"
            "标签与偏好设置仅保存在本机 %APPDATA%\\ZTCenter 目录，不会上传到任何服务器。\n"
            "planet 替换属于高级操作，请确保使用与你网络控制器匹配的世界配置。"
        )
        ctk.CTkLabel(card4.body, text=about, font=theme.font(12), text_color=c["text_muted"],
                     anchor="w", justify="left", wraplength=760).pack(fill="x")
        ctk.CTkLabel(card4.body, text=f"数据目录：{config.DATA_DIR}", font=ctk.CTkFont(family="Consolas", size=11),
                     text_color=c["text_faint"], anchor="w").pack(fill="x", pady=(8, 0))

    # ------------------------------------------------------------------ #
    def _switch(self, parent, title: str, hint: str, value: bool, command) -> ctk.CTkSwitch:
        c = theme.C()
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x", pady=6)
        col = ctk.CTkFrame(row, fg_color="transparent")
        col.pack(side="left", fill="x", expand=True)
        ctk.CTkLabel(col, text=title, font=theme.font(13), text_color=c["text"], anchor="w").pack(anchor="w")
        ctk.CTkLabel(col, text=hint, font=theme.font(11), text_color=c["text_faint"], anchor="w").pack(anchor="w")
        var = ctk.BooleanVar(value=value)
        sw = ctk.CTkSwitch(row, text="", variable=var, onvalue=True, offvalue=False, width=46,
                           progress_color=c["accent"], command=lambda: command(bool(var.get())))
        sw.pack(side="right")
        return sw

    def _save(self, key: str, value) -> None:
        self.app.settings[key] = value
        config.save_settings(self.app.settings)
        self.app.toast("设置已保存", "ok")

    def _set_ui_scale(self, value: str) -> None:
        from ui import scaling

        mode = scaling.OPTIONS.get(value, "auto")
        self.app.apply_ui_scale(mode)

    def _set_interval(self, value: str) -> None:
        if value.strip() == "关闭":
            self._save("refresh_interval", 0)
            self.app.restart_tick()
            self.app.toast("已关闭自动刷新，可随时点「刷新」手动更新", "ok")
            return
        try:
            seconds = int(value.split(" ")[0])
        except Exception:
            seconds = 5
        self._save("refresh_interval", seconds)
        self.app.restart_tick()

    def _toggle_autostart(self, value: bool) -> None:
        ok, msg = syswin.set_autostart(value)
        self.app.settings["autostart"] = value if ok else (not value)
        config.save_settings(self.app.settings)
        self.app.toast(msg, "ok" if ok else "err")

    def _toggle_kill_ui(self, value: bool) -> None:
        self._save("kill_official_ui", value)
        if not value:
            return
        if not syswin.is_admin():
            self.app.toast("结束官方 UI 进程需要管理员权限", "err")
            return

        def worker() -> None:
            ok, msg = syswin.suppress_official_ui()
            self.app.dispatch.call(lambda: self.app.toast(msg, "ok" if ok else "warn"))

        threading.Thread(target=worker, daemon=True, name="suppress-ui").start()

    def _sync_autostart(self) -> None:
        """后台读取计划任务/注册表的真实状态，回填开关（安装包可能已启用自启）。"""
        try:
            actual = syswin.autostart_enabled()
        except Exception:
            return
        if actual == bool(self.app.settings.get("autostart")):
            return
        self.app.settings["autostart"] = actual
        config.save_settings(self.app.settings)

        def apply() -> None:
            try:
                if actual:
                    self._auto_switch.select()
                else:
                    self._auto_switch.deselect()
            except Exception:
                pass

        self.app.dispatch.call(apply)

    # ------------------------------ 内核升级 ------------------------------ #
    def _open_installer_dir(self) -> None:
        p = version.installer_path()
        d = p.parent if p else (config.DATA_DIR / "downloads")
        d.mkdir(parents=True, exist_ok=True)
        syswin.open_path(d)

    def _open_download_page(self) -> None:
        try:
            import webbrowser

            webbrowser.open(version.DOWNLOAD_URL)
        except Exception as exc:
            self.app.toast(f"无法打开浏览器：{exc}", "err")

    def _pick_installer(self) -> None:
        from tkinter import filedialog

        path = filedialog.askopenfilename(
            parent=self.app,
            title="选择 ZeroTier 官方安装包（.msi）",
            filetypes=[("MSI 安装包", "*.msi"), ("所有文件", "*.*")],
        )
        if not path:
            return
        if not version.is_installer_file(path):
            self.app.toast("所选文件不是有效的 MSI 安装包（或体积异常）", "err")
            return
        self._run_installer(Path(path))

    def _run_installer(self, path: Path) -> None:
        if not syswin.is_admin():
            self.app.toast("安装内核需要管理员权限，请以管理员身份运行", "err")
            return
        if not confirm(
            self.app, "安装官方 ZeroTier 内核",
            f"即将启动官方安装向导：\n{path}\n\n"
            "安装过程会停止并重启 ZeroTier 服务，现有连接会短暂中断；\n"
            "节点身份、已加入网络与 planet 配置都会保留。\n\n"
            "安装完成后请重启本控制台以读取新版本号。",
            ok_text="开始安装",
        ):
            return
        try:
            version.run_installer(path)
            self.app.toast("安装向导已启动，请按提示完成安装", "ok")
        except Exception as exc:
            self.app.toast(f"启动安装失败：{exc}", "err")

    def _install_core(self) -> None:
        p = version.installer_path()
        if not p:
            self.app.toast("本地未找到安装包，开始下载官方安装包…")
            self._download_core()
            return
        self._run_installer(p)

    def _download_core(self) -> None:
        if self._downloading:
            self.app.toast("正在下载中，请稍候…", "warn")
            return
        self._downloading = True
        self.app.toast("正在下载官方安装包…")
        target = version.TARGET_VERSION
        last = {"pct": -1}

        def progress(frac: float) -> None:
            pct = int(frac * 100)
            if pct == last["pct"] or pct % 5:
                return
            last["pct"] = pct
            self.app.dispatch.call(lambda: self._set_kbtn_text(f"下载中 {pct}%"))

        def worker() -> None:
            try:
                p = version.download_installer(progress=progress)
                self.app.dispatch.call(lambda: self._after_download(p, None, target))
            except Exception as exc:
                self.app.dispatch.call(lambda e=exc: self._after_download(None, e, target))

        threading.Thread(target=worker, daemon=True, name="core-download").start()

    def _set_kbtn_text(self, text: str) -> None:
        try:
            self._kbtn.configure(text=text)
        except Exception:
            pass

    def _after_download(self, path, err, target: str) -> None:
        self._downloading = False
        if err is not None:
            self._set_kbtn_text("重新下载")
            self.app.toast(f"下载失败：{err}；可改用「手动选择安装包…」", "err")
            return
        self._set_kbtn_text(f"安装官方 {target}")
        try:
            self._kpath.configure(text=f"本地安装包：{path}")
        except Exception:
            pass
        self.app.toast("安装包下载完成，点击「安装官方」继续", "ok")

    # ------------------------------ 隐藏方式 ------------------------------ #
    def _refresh_hide_buttons(self) -> None:
        c = theme.C()
        current = self.app.hide_mode()
        for key, btn in getattr(self, "_hide_btns", {}).items():
            active = key == current
            try:
                btn.configure(
                    fg_color=c["accent"] if active else "transparent",
                    hover_color=c["accent_hover"] if active else c["nav_hover"],
                    text_color="#FFFFFF" if active else c["text_muted"],
                    font=theme.font(12, "bold" if active else "normal"),
                )
            except Exception:
                pass

    def _set_hide_mode(self, mode: str) -> None:
        self.app.settings["hide_mode"] = "none" if mode == "none" else "tray"
        config.save_settings(self.app.settings)
        self._refresh_hide_buttons()
        self.app.toast(
            "已设为「彻底隐藏」：隐藏时不再显示托盘图标" if mode == "none" else "已设为「隐藏到托盘」",
            "ok",
        )

    def _hide_now(self) -> None:
        if not confirm(
            self.app, "彻底隐藏",
            f"程序将移除托盘图标并隐藏窗口，仅在后台运行。\n\n"
            f"恢复方式：\n· 按 {config.HOTKEY_TEXT}\n· 或再次运行 ZTCenter.exe\n\n"
            "说明：进程仍会出现在任务管理器中，本功能只隐藏界面，不做任何反检测处理。",
            ok_text="彻底隐藏",
        ):
            return
        self.app.hide_completely()
        self._refresh_hide_buttons()

    def _elevate(self) -> None:
        if syswin.elevate():
            self.app.quit_app()
        else:
            self.app.toast("提权请求被取消", "warn")

    def _restart_service(self) -> None:
        self.app.restart_service()

    def _refresh_kernel_pill(self, vinfo: dict | None = None) -> None:
        c = theme.C()
        vinfo = vinfo or version.status()
        try:
            if not vinfo.get("kernel_installed"):
                self._kpill.restyle("内核未安装", c["danger"], c["danger_soft"])
            elif vinfo.get("outdated"):
                self._kpill.restyle(f"内核可升级至 {vinfo['target']}", c["warn"], c["warn_soft"])
            elif vinfo.get("up_to_date"):
                self._kpill.restyle("内核已是最新", c["success"], c["success_soft"])
            else:
                self._kpill.restyle("内核版本未知", c["text_muted"], c["card_alt"])
        except Exception:
            pass

    def refresh(self) -> None:
        """页面数据刷新：内核版本优先取运行中服务（/status），回退注册表。"""
        try:
            present = version.kernel_installed()
            st = ((self.app.summary or {}).get("status") or {}) if (self.app.summary and present) else {}
            runtime = st.get("version")
            vinfo = version.status()
            lab = getattr(self, "_vlabels", {}).get("当前内核版本")
            if lab is not None:
                lab.configure(text=(runtime or vinfo["kernel"]) if present else "未安装")
            self._refresh_kernel_pill(vinfo)
        except Exception:
            pass
