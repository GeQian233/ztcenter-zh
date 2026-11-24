"""概览页。"""
from __future__ import annotations

import datetime as _dt

import customtkinter as ctk

from core import config, planet, syswin, version
from core.ztapi import net_id, net_ipv4, net_ipv6
from ui import theme
from ui.dialogs import confirm
from ui.widgets import Card, Pill, empty_state, ghost_button, kv_row, primary_button


class OverviewPage(ctk.CTkFrame):
    def __init__(self, master, app):
        super().__init__(master, fg_color="transparent")
        self.app = app
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)
        self.scroll = ctk.CTkScrollableFrame(self, fg_color="transparent",
                                             scrollbar_button_color=theme.C()["border"])
        self.scroll.grid(row=0, column=0, sticky="nsew")
        self.scroll.grid_columnconfigure(0, weight=1)
        self._refs: dict = {}
        self._build()

    # ------------------------------------------------------------------ #
    def _build(self) -> None:
        c = theme.C()
        wrap = ctk.CTkFrame(self.scroll, fg_color="transparent")
        wrap.grid(row=0, column=0, sticky="nsew", padx=6, pady=(4, 12))
        wrap.grid_columnconfigure(0, weight=1)

        # 顶部提示条（异常时显示）
        self.banner = ctk.CTkFrame(wrap, fg_color=c["warn_soft"], corner_radius=10)
        self.banner_label = ctk.CTkLabel(self.banner, text="", font=theme.font(12),
                                         text_color=c["warn"], anchor="w", justify="left")
        self.banner_label.pack(side="left", fill="x", expand=True, padx=14, pady=10)
        self.banner_btn = ctk.CTkButton(
            self.banner, text="以管理员身份重启", width=126, height=28, corner_radius=7,
            fg_color=c["warn"], hover_color="#B45309", text_color="#FFFFFF",
            font=theme.font(11, "bold"), command=self._elevate,
        )
        self.banner_btn2 = ctk.CTkButton(
            self.banner, text="安装内核", width=92, height=28, corner_radius=7,
            fg_color=c["danger"], hover_color="#B91C1C", text_color="#FFFFFF",
            font=theme.font(11, "bold"),
            command=lambda: self.app.show_page("settings"),
        )

        # 统计卡
        stats = ctk.CTkFrame(wrap, fg_color="transparent")
        stats.grid(row=1, column=0, sticky="ew")
        for i in range(4):
            stats.grid_columnconfigure(i, weight=1, uniform="stat")
        stats.grid_rowconfigure(0, weight=1)
        self._refs["online"] = self._stat(stats, 0, "节点状态")
        self._refs["nets"] = self._stat(stats, 1, "已加入网络", on_click=self._open_all_networks)
        self._refs["peers"] = self._stat(stats, 2, "在线对端", on_click=self._open_peers)
        self._refs["world"] = self._stat(stats, 3, "根节点世界 ID", small=True)

        # 中间两栏
        mid = ctk.CTkFrame(wrap, fg_color="transparent")
        mid.grid(row=2, column=0, sticky="ew", pady=(12, 0))
        mid.grid_columnconfigure(0, weight=3, uniform="mid")
        mid.grid_columnconfigure(1, weight=2, uniform="mid")

        info = Card(mid)
        info.grid(row=0, column=0, sticky="nsew", padx=(0, 6))
        head = info.title("节点信息", "ZeroTier One 服务")
        ctk.CTkButton(head, text="复制节点 ID", width=86, height=26, corner_radius=7,
                      fg_color=c["accent_soft"], hover_color=c["nav_hover"],
                      text_color=c["accent"], font=theme.font(11, "bold"),
                      command=self._copy_address).pack(side="right")
        self._refs["kv"] = {}
        for key in ("节点 ID", "客户端版本", "世界 ID", "根节点类型", "世界时间", "主端口", "TCP 回退中继", "本地服务"):
            _, val = kv_row(info.body, key)
            self._refs["kv"][key] = val

        actions = Card(mid)
        actions.grid(row=0, column=1, sticky="nsew", padx=(6, 0))
        actions.title("快捷操作")
        primary_button(actions.body, "加入新网络", lambda: self.app.show_page("networks")).pack(fill="x", pady=(0, 6))
        ghost_button(actions.body, "替换根节点（planet）", lambda: self.app.show_page("planet")).pack(fill="x", pady=3)
        ghost_button(actions.body, "MOON 节点管理", self._open_moon).pack(fill="x", pady=3)
        ghost_button(actions.body, "重启 ZeroTier 服务", self._restart_service).pack(fill="x", pady=3)
        ghost_button(actions.body, "打开 ZeroTier 配置目录",
                     lambda: syswin.open_path(config.ZT_HOME)).pack(fill="x", pady=3)
        ghost_button(actions.body, "隐藏到系统托盘", self.app.hide_to_tray).pack(fill="x", pady=3)
        ghost_button(actions.body, "彻底隐藏（无托盘图标）", self._hide_completely).pack(fill="x", pady=3)

        # 网络概览
        nets = Card(wrap)
        nets.grid(row=3, column=0, sticky="ew", pady=(12, 0))
        head = nets.title("网络概览")
        ctk.CTkButton(head, text="管理全部", width=76, height=26, corner_radius=7,
                      fg_color=c["accent_soft"], hover_color=c["nav_hover"],
                      text_color=c["accent"], font=theme.font(11, "bold"),
                      command=lambda: self.app.show_page("networks")).pack(side="right")
        self._refs["net_box"] = ctk.CTkFrame(nets.body, fg_color="transparent")
        self._refs["net_box"].pack(fill="x")

    def _stat(self, parent, col: int, title: str, small: bool = False, on_click=None) -> dict:
        c = theme.C()
        card = ctk.CTkFrame(parent, fg_color=c["card"], corner_radius=14,
                            border_width=1, border_color=c["border"], height=136)
        card.grid(row=0, column=col, sticky="nsew", padx=(0 if col == 0 else 6, 6 if col < 3 else 0))
        card.grid_propagate(False)   # 固定高度，四张卡严格等高
        inner = ctk.CTkFrame(card, fg_color="transparent")
        inner.pack(fill="both", expand=True, padx=16, pady=13)
        ctk.CTkLabel(inner, text=title, font=theme.font(11), text_color=c["text_muted"],
                     anchor="w").pack(anchor="w")
        val = ctk.CTkLabel(
            inner, text="—",
            font=ctk.CTkFont(family="Consolas", size=15, weight="bold") if small else theme.font(22, "bold"),
            text_color=c["text"], anchor="w",
        )
        val.pack(anchor="w", pady=(4, 0))
        sub = ctk.CTkLabel(inner, text="", font=theme.font(11), text_color=c["text_faint"], anchor="w")
        sub.pack(anchor="w")
        # 无论是否可点击都保留同一行，保证四张卡内部行数一致
        tip = ctk.CTkLabel(inner, text="点击查看详情 ›" if on_click else "",
                           font=theme.font(10), text_color=c["text_faint"], anchor="w")
        tip.pack(anchor="w", pady=(3, 0))
        if on_click is not None:
            self._clickable(card, on_click)
        return {"value": val, "sub": sub, "card": card}

    def _clickable(self, widget, callback) -> None:
        """让容器及其子控件整体可点击（含手型光标）。"""
        try:
            widget.configure(cursor="hand2")
        except Exception:
            pass
        widget.bind("<Button-1>", lambda e: callback())
        for child in widget.winfo_children():
            self._clickable(child, callback)

    # ------------------------------------------------------------------ #
    def refresh(self) -> None:
        c = theme.C()
        err = self.app.last_error
        data = self.app.summary
        if err:
            self.banner_label.configure(text=f"⚠  {err}")
            self.banner.grid(row=0, column=0, sticky="ew", pady=(0, 12))
            if not syswin.is_admin():
                self.banner_btn.pack(side="right", padx=10, pady=8)
            else:
                self.banner_btn.pack_forget()
            if not version.kernel_installed():
                self.banner_btn2.pack(side="right", padx=(10, 0), pady=8)
            else:
                self.banner_btn2.pack_forget()
        else:
            self.banner.grid_remove()

        if not data:
            for key in ("online", "nets", "peers", "world"):
                self._refs[key]["value"].configure(text="—")
                self._refs[key]["sub"].configure(text="")
            self._render_networks([])
            return

        st = data["status"]
        online = bool(st.get("online"))
        self._refs["online"]["value"].configure(text="在线" if online else "离线",
                                                text_color=c["success"] if online else c["warn"])
        from core import peers as _peers

        mode = _peers.mode_short(_peers.connection_mode(data.get("peers"),
                                                        str(st.get("address") or "").lower()))
        sub = f"v{st.get('version', '—')}"
        if mode:
            sub += f"  ·  {mode}"
        self._refs["online"]["sub"].configure(text=sub)

        nets = data["networks"]
        connected = [n for n in nets if (n.get("status") or "").upper() == "OK"]
        self._refs["nets"]["value"].configure(text=str(len(nets)), text_color=c["text"])
        self._refs["nets"]["sub"].configure(text=f"{len(connected)} 个已连通")

        self._refs["peers"]["value"].configure(text=str(data.get("online_peer_count", 0)),
                                              text_color=c["text"])
        self._refs["peers"]["sub"].configure(text=f"根节点 {data.get('root_count', 0)} 个")

        world_id = st.get("planetWorldId")
        world_text = f"{world_id:010x}" if isinstance(world_id, int) else "—"
        self._refs["world"]["value"].configure(text=world_text, text_color=c["text"])
        ts = st.get("planetWorldTimestamp")
        ts_text = ""
        if isinstance(ts, int) and ts > 0:
            try:
                ts_text = _dt.datetime.fromtimestamp(ts / 1000).strftime("%Y-%m-%d %H:%M")
            except Exception:
                ts_text = ""
        self._refs["world"]["sub"].configure(text=ts_text)

        kv = self._refs["kv"]
        kv["节点 ID"].configure(text=st.get("address", "—"))
        kv["客户端版本"].configure(text=st.get("version", "—"))
        kv["世界 ID"].configure(text=world_text)
        kind = planet.current_kind()
        kv["根节点类型"].configure(
            text=planet.kind_text(kind),
            text_color=c["success"] if kind == "official" else (
                c["text"] if kind == "custom" else c["danger"]),
        )
        kv["世界时间"].configure(text=ts_text or "—")
        port = (st.get("config") or {}).get("settings", {}).get("primaryPort", "—")
        kv["主端口"].configure(text=str(port))
        fallback = "已启用" if st.get("tcpFallbackActive") else "未启用"
        kv["TCP 回退中继"].configure(text=fallback)
        kv["本地服务"].configure(text=f"127.0.0.1:{self.app.api.port()}  ·  {syswin.service_state_text()}")

        self._render_networks(nets)

    def _render_networks(self, nets: list[dict]) -> None:
        c = theme.C()
        box = self._refs["net_box"]
        for w in box.winfo_children():
            w.destroy()
        if not nets:
            if self.app.last_error:
                empty_state(box, "无法读取网络列表",
                            "请以管理员身份运行，或确认 ZeroTier 服务正在运行").pack(fill="x")
            else:
                empty_state(box, "尚未加入任何网络", "在「网络管理」中输入 16 位网络 ID 加入").pack(fill="x")
            return
        for net in nets[:6]:
            nwid = (net.get("id") or net.get("nwid") or "").lower()
            meta = self.app.labels.get(nwid)
            row = ctk.CTkFrame(box, fg_color="transparent")
            row.pack(fill="x", pady=4)
            name = self.app.labels.display_name(net)
            self._clickable(row, lambda n=net: self._open_net_detail(n))
            chip_color = meta["color"]
            ctk.CTkFrame(row, width=3, height=30, fg_color=chip_color,
                         corner_radius=2).pack(side="left", padx=(0, 10))
            col = ctk.CTkFrame(row, fg_color="transparent")
            col.pack(side="left", fill="x", expand=True)
            title = ctk.CTkLabel(col, text=name, font=theme.font(13, "bold"),
                                 text_color=c["text"], anchor="w")
            title.pack(anchor="w")
            ips = ", ".join(net_ipv4(net) + net_ipv6(net)) or "无分配地址"
            ctk.CTkLabel(col, text=f"{nwid}  ·  {ips}", font=ctk.CTkFont(family="Consolas", size=11),
                         text_color=c["text_faint"], anchor="w").pack(anchor="w")
            text, fg, bg = theme.status_style(net.get("status", ""))
            Pill(row, text, fg=fg, bg=bg).pack(side="right", padx=(8, 0))
            if meta["group"]:
                Pill(row, meta["group"], fg=c["text_muted"], bg=c["card_alt"]).pack(side="right", padx=6)

    # ------------------------------------------------------------------ #
    def _copy_address(self) -> None:
        data = self.app.summary or {}
        addr = (data.get("status") or {}).get("address", "")
        if not addr:
            return
        self.clipboard_clear()
        self.clipboard_append(addr)
        self.app.toast(f"已复制节点 ID：{addr}", "ok")

    def _hide_completely(self) -> None:
        if not confirm(
            self.app, "彻底隐藏",
            f"托盘图标将被移除，程序仅在后台运行。\n\n"
            f"恢复方式：\n· 按 {config.HOTKEY_TEXT}\n· 或再次运行 ZTCenter.exe\n\n"
            "说明：进程仍会出现在任务管理器中，本功能只隐藏界面，不做任何反检测处理。",
            ok_text="彻底隐藏",
        ):
            return
        self.app.hide_completely()

    def _open_all_networks(self) -> None:
        from ui.pages.networks import NetworkDetailDialog

        if not (self.app.summary or {}).get("networks"):
            self.app.toast("尚未加入任何网络", "warn")
            return
        dlg = NetworkDetailDialog(self.app, self.app, None)
        self.app.wait_window(dlg)
        self.app.poll()

    def _open_peers(self) -> None:
        from ui.peers_dialog import PeersDialog

        dlg = PeersDialog(self.app)
        self.app.wait_window(dlg)

    def _open_net_detail(self, net: dict) -> None:
        from ui.pages.networks import NetworkDetailDialog

        dlg = NetworkDetailDialog(self.app, self.app, net)
        self.app.wait_window(dlg)
        self.app.poll()

    def _open_moon(self) -> None:
        from ui.moon_dialog import MoonDialog

        dlg = MoonDialog(self.app)
        self.app.wait_window(dlg)
        self.app.poll()

    def _elevate(self) -> None:
        if syswin.elevate():
            self.app.quit_app()
        else:
            self.app.toast("提权请求被取消", "warn")

    def _restart_service(self) -> None:
        self.app.restart_service()
