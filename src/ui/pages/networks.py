"""网络管理页：加入 / 查看详情 / 快速切换选项 / 退出网络。"""
from __future__ import annotations

import re
import tkinter as tk

import customtkinter as ctk

from core import network_order
from core.ztapi import (
    ZTError,
    net_dns_servers,
    net_flags,
    net_id,
    net_info_text,
    net_ipv4,
    net_ipv6,
    net_routes,
)
from ui import theme
from ui.dialogs import LabelDialog, Modal, confirm
from ui.widgets import Card, Pill, empty_state, ghost_button, kv_row, primary_button

NWID_RE = re.compile(r"^[0-9a-fA-F]{16}$")

OPTION_LABELS = (
    ("allowManaged", "允许托管配置（IP / 路由 / DNS）"),
    ("allowGlobal", "允许全局 IP"),
    ("allowDefault", "允许默认路由（全部流量走此网络）"),
    ("allowDNS", "使用网络 DNS"),
)


class NetworksPage(ctk.CTkFrame):
    def __init__(self, master, app):
        super().__init__(master, fg_color="transparent")
        self.app = app
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)
        self._filter = ""
        self._rows: list[dict] = []
        self._drag: dict | None = None
        self._build()

    # ------------------------------------------------------------------ #
    def _build(self) -> None:
        c = theme.C()
        top = Card(self)
        top.grid(row=0, column=0, sticky="ew", padx=6, pady=(4, 6))
        top.title("加入网络", "输入 16 位十六进制网络 ID")
        self.entry = ctk.CTkEntry(
            top.body, height=36, corner_radius=8, fg_color=c["input"],
            border_color=c["border"], placeholder_text="例如 8767f3abba18a28c",
            font=ctk.CTkFont(family="Consolas", size=13),
        )
        self.entry.pack(side="left", fill="x", expand=True, padx=(0, 8))
        self.entry.bind("<Return>", lambda e: self._join())
        primary_button(top.body, "加入", self._join, width=88).pack(side="left")
        ctk.CTkLabel(top.body, text="加入后需在控制器中授权本节点", font=theme.font(11),
                     text_color=c["text_faint"], anchor="w").pack(side="left", padx=(12, 0))

        listcard = Card(self, padding=16)
        listcard.grid(row=1, column=0, sticky="nsew", padx=6, pady=(0, 6))
        head = listcard.title("已加入网络")
        self.count_pill = Pill(head, "0", fg=c["accent"], bg=c["accent_soft"])
        self.count_pill.pack(side="left", padx=8)

        tools = ctk.CTkFrame(head, fg_color="transparent")
        tools.pack(side="right")
        ctk.CTkLabel(tools, text="拖动左侧 ≡ 调整顺序", font=theme.font(10),
                     text_color=c["text_faint"]).pack(side="left", padx=(0, 8))
        self.search = ctk.CTkEntry(tools, width=210, height=28, corner_radius=7,
                                   fg_color=c["input"], border_color=c["border"],
                                   placeholder_text="搜索名称 / ID / 分组", font=theme.font(11))
        self.search.pack(side="left", padx=(0, 6))
        self.search.bind("<KeyRelease>", self._on_search)
        ghost_button(tools, "全部详情", self._open_all, width=76, height=28).pack(side="left")

        self.list_box = ctk.CTkScrollableFrame(listcard.body, fg_color="transparent",
                                               scrollbar_button_color=c["border"])
        self.list_box.pack(fill="both", expand=True)
        self.list_box.grid_columnconfigure(0, weight=1)

    def _on_search(self, _evt=None) -> None:
        self._filter = self.search.get().strip().lower()
        self._render(self.app.summary)

    # ------------------------------------------------------------------ #
    def refresh(self) -> None:
        self._render(self.app.summary)

    def _nets(self) -> list[dict]:
        """按用户拖拽顺序显示；默认即内核返回顺序（近似加入顺序）。"""
        data = self.app.summary or {}
        nets = list(data.get("networks") or [])
        return network_order.sort_networks(nets, self.app.net_order.order())

    def _render(self, data) -> None:
        for w in self.list_box.winfo_children():
            w.destroy()
        err = self.app.last_error
        if err and not data:
            empty_state(self.list_box, "无法读取网络列表", err).pack(fill="x")
            return
        if not data:
            empty_state(self.list_box, "正在读取…").pack(fill="x")
            return

        nets = self._nets()
        self.count_pill.configure(text=str(len(nets)))
        self._rows = []
        draggable = len(nets) > 1
        shown = 0
        for net in nets:
            nwid = net_id(net)
            meta = self.app.labels.get(nwid)
            name = self.app.labels.display_name(net)
            haystack = " ".join([name, nwid, meta["group"], meta["note"],
                                 str(net.get("name") or ""), " ".join(net_flags(net))]).lower()
            if self._filter and self._filter not in haystack:
                continue
            try:
                self._render_row(net, nwid, name, meta, draggable)
            except Exception as exc:  # 单行渲染失败不影响其它网络
                self.app.log(f"渲染网络 {nwid} 失败：{exc}")
                row = ctk.CTkFrame(self.list_box, fg_color=theme.C()["danger_soft"], corner_radius=10)
                row.pack(fill="x", pady=5, padx=2)
                ctk.CTkLabel(row, text=f"{nwid}  渲染异常：{exc}", font=theme.font(11),
                             text_color=theme.C()["danger"], anchor="w").pack(fill="x", padx=12, pady=8)
            shown += 1
        if shown == 0:
            if nets:
                empty_state(self.list_box, "没有匹配的网络", "换个关键词试试").pack(fill="x")
            else:
                empty_state(self.list_box, "尚未加入任何网络",
                            "在上方输入网络 ID 并点击「加入」").pack(fill="x")

    # ------------------------------------------------------------------ #
    def _render_row(self, net: dict, nwid: str, name: str, meta: dict,
                    draggable: bool = True) -> None:
        c = theme.C()
        card = ctk.CTkFrame(self.list_box, fg_color=c["card_alt"], corner_radius=12,
                            border_width=1, border_color=c["border"])
        card.grid(row=len(self._rows), column=0, sticky="ew", pady=5, padx=2)
        row_ref = {"nwid": nwid, "card": card, "draggable": draggable}
        self._rows.append(row_ref)
        body = ctk.CTkFrame(card, fg_color="transparent")
        body.pack(fill="x", padx=14, pady=10)

        # 右侧按钮先布局，避免被长文本挤压
        right = ctk.CTkFrame(body, fg_color="transparent")
        right.pack(side="right", padx=(10, 0))
        primary_button(right, "详情", lambda n=net: self._open_detail(n), width=58,
                       height=30).pack(side="left", padx=3)
        ghost_button(right, "标签", lambda n=net: LabelDialog(self.app, self.app, n),
                     width=54, height=30).pack(side="left", padx=3)
        ghost_button(right, "离开", lambda n=nwid, nm=name: self._leave(n, nm),
                     width=54, height=30, danger=True).pack(side="left", padx=3)

        left = ctk.CTkFrame(body, fg_color="transparent")
        left.pack(side="left", fill="x", expand=True)

        # 第一行：色条 + 名称 + 标签分组 + 状态 + 类型 + 控制器网络名
        line1 = ctk.CTkFrame(left, fg_color="transparent")
        line1.pack(fill="x")
        handle = ctk.CTkLabel(line1, text="≡", width=18, font=theme.font(13, "bold"),
                              text_color=c["text_muted"] if draggable else c["border"])
        handle.pack(side="left", padx=(0, 6))
        row_ref["handle"] = handle
        if draggable:
            self._bind_drag(handle, row_ref)
        ctk.CTkFrame(line1, width=4, height=18, fg_color=meta["color"],
                     corner_radius=2).pack(side="left", padx=(0, 8))
        ctk.CTkLabel(line1, text=name, font=theme.font(14, "bold"),
                     text_color=c["text"], anchor="w").pack(side="left")
        if meta["group"]:
            Pill(line1, meta["group"], fg=c["text_muted"], bg=c["card"]).pack(side="left", padx=8)
        text, fg, bg = theme.status_style(net.get("status", ""))
        Pill(line1, text, fg=fg, bg=bg).pack(side="left", padx=4)
        if net.get("type"):
            Pill(line1, "私有" if net.get("type") == "PRIVATE" else "公开",
                 fg=c["text_muted"], bg=c["card"]).pack(side="left", padx=4)
        ctrl_name = str(net.get("name") or "").strip()
        if ctrl_name and ctrl_name != name:
            ctk.CTkLabel(line1, text=ctrl_name, font=theme.font(11),
                         text_color=c["text_faint"]).pack(side="left", padx=(6, 0))

        # 第二行：16 位网络 ID + IPv4 + IPv6
        v4 = net_ipv4(net)
        v6 = net_ipv6(net)
        seg = [nwid]
        seg.append("IPv4 " + ", ".join(v4) if v4 else "IPv4 未分配")
        if v6:
            seg.append("IPv6 " + ", ".join(v6))
        ctk.CTkLabel(left, text="   ·   ".join(seg),
                     font=ctk.CTkFont(family="Consolas", size=12),
                     text_color=c["text_muted"], anchor="w").pack(anchor="w", pady=(5, 0))
        if not v4 and not v6:
            hint = ("等待控制器授权后下发地址"
                    if net.get("status") != "OK" else "未启用托管或控制器未分配地址")
            ctk.CTkLabel(left, text=hint, font=theme.font(11),
                         text_color=c["text_faint"], anchor="w").pack(anchor="w", pady=(1, 0))

        # 第三行：网卡 / MTU / 已开启选项 / 备注
        extra: list[str] = []
        if net.get("portDeviceName"):
            extra.append(f"网卡 {net['portDeviceName']}")
        if net.get("mtu"):
            extra.append(f"MTU {net['mtu']}")
        flags = net_flags(net)
        extra.append("选项 " + ("/".join(flags) if flags else "无"))
        if meta["note"]:
            extra.append(meta["note"])
        ctk.CTkLabel(left, text="   ·   ".join(extra), font=theme.font(11),
                     text_color=c["text_faint"], anchor="w").pack(anchor="w", pady=(3, 0))

        self._bind_row(card, net)

    # ------------------------------------------------------------------ #
    # 拖拽排序
    # ------------------------------------------------------------------ #
    def _bind_drag(self, handle, row: dict) -> None:
        try:
            handle.configure(cursor="fleur")
        except Exception:
            pass
        handle.bind("<Button-1>", lambda e, r=row: self._drag_start(r))
        handle.bind("<B1-Motion>", self._drag_move)
        handle.bind("<ButtonRelease-1>", self._drag_end)

    def _drag_start(self, row: dict) -> None:
        self._drag = {"nwid": row["nwid"], "moved": False, "row": row}
        try:
            row["card"].configure(border_color=theme.C()["accent"])
        except Exception:
            pass

    def _drop_index(self, y_root: int) -> int:
        for i, row in enumerate(self._rows):
            card = row["card"]
            try:
                top, height = card.winfo_rooty(), card.winfo_height()
            except Exception:
                continue
            if y_root < top + height / 2:
                return i
        return len(self._rows)

    def _drag_move(self, event) -> None:
        if not self._drag:
            return
        nwid = self._drag["nwid"]
        current = next((i for i, r in enumerate(self._rows) if r["nwid"] == nwid), None)
        if current is None:
            return
        target = max(0, min(self._drop_index(event.y_root), len(self._rows) - 1))
        if target == current:
            return
        row = self._rows.pop(current)
        self._rows.insert(target, row)
        self._drag["moved"] = True
        self._relayout()

    def _drag_end(self, _event=None) -> None:
        if not self._drag:
            return
        moved = bool(self._drag["moved"])
        row = self._drag.get("row")
        self._drag = None
        if row is not None:
            try:
                row["card"].configure(border_color=theme.C()["border"])
            except Exception:
                pass
        if moved:
            self.app.net_order.set_order([r["nwid"] for r in self._rows])
            self.app.toast("网络显示顺序已保存", "ok")

    def _relayout(self) -> None:
        for i, row in enumerate(self._rows):
            try:
                row["card"].grid_configure(row=i)
            except Exception:
                pass

    # ------------------------------------------------------------------ #
    def _bind_row(self, widget, net: dict) -> None:
        """整行支持右键菜单与双击打开详情。"""
        if isinstance(widget, ctk.CTkButton):
            return
        widget.bind("<Button-3>", lambda e, n=net: self._popup(e, n))
        widget.bind("<Double-Button-1>", lambda e, n=net: self._open_detail(n))
        for child in widget.winfo_children():
            self._bind_row(child, net)

    def _build_menu(self, net: dict) -> tk.Menu:
        """构建右键菜单（独立出来便于单测，不弹出）。"""
        c = theme.C()
        nwid = net_id(net)
        name = self.app.labels.display_name(net)
        kw = dict(tearoff=0, bg=c["card"], fg=c["text"], bd=0, relief="flat",
                  activebackground=c["accent"], activeforeground="#FFFFFF",
                  font=("Microsoft YaHei UI", 9))
        menu = tk.Menu(self, **kw)

        menu.add_command(label=f"查看详细信息（{name}）", command=lambda: self._open_detail(net))
        menu.add_command(label="复制网络 ID", command=lambda: self._copy(nwid, "网络 ID"))
        v4, v6 = net_ipv4(net), net_ipv6(net)
        if v4:
            menu.add_command(label=f"复制 IPv4：{v4[0]}",
                             command=lambda a=v4[0]: self._copy(a, "IPv4 地址"))
        if v6:
            menu.add_command(label=f"复制 IPv6：{v6[0]}",
                             command=lambda a=v6[0]: self._copy(a, "IPv6 地址"))
        menu.add_command(label="复制全部信息", command=lambda: self._copy_info(net))

        menu.add_separator()
        sub = tk.Menu(menu, **kw)
        for key, label in OPTION_LABELS:
            var = tk.BooleanVar(value=bool(net.get(key)))
            sub.add_checkbutton(label=label, variable=var,
                                command=lambda k=key, v=var, n=net: self._toggle_option(n, k, v.get()))
        menu.add_cascade(label="快速切换网络选项", menu=sub)

        menu.add_separator()
        menu.add_command(label="编辑标签…", command=lambda: LabelDialog(self.app, self.app, net))
        menu.add_command(label="刷新此网络", command=lambda: self._refresh_net(net))
        menu.add_command(label="退出网络", command=lambda: self._leave(nwid, name))
        return menu

    def _popup(self, event, net: dict) -> None:
        menu = self._build_menu(net)
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()

    def _copy(self, text: str, what: str = "") -> None:
        if not text:
            return
        self.clipboard_clear()
        self.clipboard_append(text)
        self.app.toast(f"已复制{what}：{text}", "ok")

    def _copy_info(self, net: dict) -> None:
        self._copy(net_info_text(net), "网络信息")

    def _toggle_option(self, net: dict, key: str, value: bool) -> None:
        nwid = net_id(net)
        try:
            self.app.api.update(nwid, {key: value})
        except ZTError as exc:
            self.app.toast(str(exc), "err")
            return
        label = dict(OPTION_LABELS).get(key, key)
        self.app.toast(f"{label}：已{'开启' if value else '关闭'}", "ok")
        self.app.poll()
        self.after(600, self.refresh)

    def _refresh_net(self, net: dict) -> None:
        nwid = net_id(net)
        try:
            self.app.api.network(nwid)
        except ZTError as exc:
            self.app.toast(str(exc), "err")
            return
        self.app.toast(f"已刷新 {nwid}", "ok")
        self.app.poll()

    # ------------------------------------------------------------------ #
    def _join(self) -> None:
        nwid = self.entry.get().strip()
        if not nwid:
            self.app.toast("请输入网络 ID", "warn")
            return
        if not NWID_RE.match(nwid):
            self.app.toast("网络 ID 必须是 16 位十六进制字符，例如 8767f3abba18a28c", "err")
            return
        try:
            self.app.api.join(nwid.lower())
        except ZTError as exc:
            self.app.toast(str(exc), "err")
            return
        self.entry.delete(0, "end")
        self.app.toast(f"已加入网络 {nwid.lower()}，等待控制器授权", "ok")
        self.app.poll()
        self.after(1200, self.refresh)

    def _leave(self, nwid: str, name: str) -> None:
        if not confirm(self.app, "离开网络",
                       f"确定要退出网络「{name}」吗？\n\n网络 ID：{nwid}\n退出后该网络的地址与路由会立即失效。",
                       ok_text="退出网络", danger=True):
            return
        try:
            self.app.api.leave(nwid)
        except ZTError as exc:
            self.app.toast(str(exc), "err")
            return
        self.app.toast(f"已退出网络 {nwid}", "ok")
        self.app.poll()
        self.after(1200, self.refresh)

    def _open_detail(self, net: dict) -> None:
        NetworkDetailDialog(self.app, self.app, net)

    def _open_all(self) -> None:
        if not self._nets():
            self.app.toast("尚未加入任何网络", "warn")
            return
        NetworkDetailDialog(self.app, self.app, None)


class NetworkDetailDialog(Modal):
    """单个网络的详细配置；net 为 None 时展示全部网络的汇总。"""

    def __init__(self, parent, app, net: dict | None):
        self.app = app
        self.net = net or {}
        self.show_all = net is None
        self.nwid = net_id(self.net)
        title = "全部网络信息" if self.show_all else f"网络详情 · {app.labels.display_name(self.net)}"
        super().__init__(parent, title, width=620, height=720)
        if self.show_all:
            self._build_all()
        else:
            self._build_one()

        if self.show_all:
            primary_button(self.footer, "关闭", self.close, width=90).pack(side="right")
        else:
            primary_button(self.footer, "保存配置", self._save, width=100).pack(side="right", padx=(8, 0))
            ghost_button(self.footer, "关闭", self.close, width=76).pack(side="right")
        ghost_button(self.footer, "复制信息", self._copy_info).pack(side="left")
        if not self.show_all:
            ghost_button(self.footer, "编辑标签", lambda: self._edit_label()).pack(side="left", padx=6)

    # ------------------------------------------------------------------ #
    def _build_one(self) -> None:
        c = theme.C()
        net = self.net
        ctk.CTkLabel(self.body, text="基本信息", font=theme.font(12, "bold"),
                     text_color=c["text_muted"], anchor="w").pack(fill="x", padx=10, pady=(6, 4))
        info = ctk.CTkFrame(self.body, fg_color=c["card_alt"], corner_radius=10)
        info.pack(fill="x", padx=6)
        inner = ctk.CTkFrame(info, fg_color="transparent")
        inner.pack(fill="x", padx=12, pady=10)

        status_text, _fg, _bg = theme.status_style(net.get("status", ""))
        v4, v6 = net_ipv4(net), net_ipv6(net)
        rows = [
            ("网络 ID", self.nwid),
            ("控制器名称", net.get("name") or "（无）"),
            ("本机标签", self.app.labels.display_name(net)),
            ("连接状态", status_text),
            ("网络类型", "私有（需授权）" if net.get("type") == "PRIVATE" else "公开"),
            ("IPv4 地址", "\n".join(v4) if v4 else "未分配"),
            ("IPv6 地址", "\n".join(v6) if v6 else "未分配"),
            ("虚拟网卡", net.get("portDeviceName") or "—"),
            ("MAC 地址", net.get("mac") or "—"),
            ("MTU", str(net.get("mtu") or "—")),
            ("DHCP", "已启用" if net.get("dhcp") else "未启用"),
            ("广播", "已启用" if net.get("broadcastEnabled") else "未启用"),
            ("配置版本", str(net.get("netconfRevision", "—"))),
        ]
        for k, v in rows:
            _, val = kv_row(inner, k)
            val.configure(text=str(v))

        # 网络选项
        ctk.CTkLabel(self.body, text="网络选项（可快速切换）", font=theme.font(12, "bold"),
                     text_color=c["text_muted"], anchor="w").pack(fill="x", padx=10, pady=(16, 6))
        self.vars: dict[str, ctk.BooleanVar] = {}
        options = [
            ("allowManaged", "允许托管配置", "由网络控制器下发 IP、路由与 DNS"),
            ("allowGlobal", "允许全局 IP", "接受控制器分配的全局（公网）地址"),
            ("allowDefault", "允许默认路由", "允许接管系统默认路由（全部流量经此网络）"),
            ("allowDNS", "使用网络 DNS", "采用控制器下发的 DNS 服务器"),
        ]
        for key, label, hint in options:
            row = ctk.CTkFrame(self.body, fg_color="transparent")
            row.pack(fill="x", padx=10, pady=3)
            var = ctk.BooleanVar(value=bool(net.get(key, False)))
            self.vars[key] = var
            ctk.CTkSwitch(row, text="", variable=var, onvalue=True, offvalue=False,
                          progress_color=c["accent"], width=44).pack(side="left")
            ctk.CTkLabel(row, text=label, font=theme.font(13),
                         text_color=c["text"]).pack(side="left", padx=(6, 0))
            ctk.CTkLabel(row, text=hint, font=theme.font(11),
                         text_color=c["text_faint"]).pack(side="left", padx=(10, 0))

        # DNS
        ctk.CTkLabel(self.body, text="DNS 服务器", font=theme.font(12, "bold"),
                     text_color=c["text_muted"], anchor="w").pack(fill="x", padx=10, pady=(14, 4))
        self.dns_entry = ctk.CTkEntry(self.body, height=32, corner_radius=8,
                                      fg_color=c["input"], border_color=c["border"],
                                      placeholder_text="多个用英文逗号分隔，例如 10.60.222.1, 1.1.1.1",
                                      font=theme.font(12))
        self.dns_entry.pack(fill="x", padx=10)
        servers = net_dns_servers(net)
        if servers:
            self.dns_entry.insert(0, ", ".join(servers))

        # 路由
        routes = net_routes(net)
        if routes:
            ctk.CTkLabel(self.body, text="下发的路由", font=theme.font(12, "bold"),
                         text_color=c["text_muted"], anchor="w").pack(fill="x", padx=10, pady=(16, 4))
            for target, via in routes[:16]:
                ctk.CTkLabel(self.body, text=f"  {target}" + (f"  via {via}" if via else ""),
                             font=ctk.CTkFont(family="Consolas", size=11),
                             text_color=c["text_muted"], anchor="w").pack(fill="x", padx=10)

    def _build_all(self) -> None:
        c = theme.C()
        nets = (self.app.summary or {}).get("networks") or []
        ctk.CTkLabel(self.body, text=f"共 {len(nets)} 个网络",
                     font=theme.font(11), text_color=c["text_faint"], anchor="w").pack(
            fill="x", padx=10, pady=(6, 6))
        for net in nets:
            card = ctk.CTkFrame(self.body, fg_color=c["card_alt"], corner_radius=10)
            card.pack(fill="x", padx=6, pady=4)
            inner = ctk.CTkFrame(card, fg_color="transparent")
            inner.pack(fill="x", padx=12, pady=10)
            status_text, _fg, _bg = theme.status_style(net.get("status", ""))
            v4, v6 = net_ipv4(net), net_ipv6(net)
            ctk.CTkLabel(inner, text=f"{self.app.labels.display_name(net)}   ·   {status_text}",
                         font=theme.font(13, "bold"), text_color=c["text"], anchor="w").pack(fill="x")
            ctk.CTkLabel(inner, text=f"{net_id(net)}   ·   " + (", ".join(v4 + v6) or "未分配地址"),
                         font=ctk.CTkFont(family="Consolas", size=11),
                         text_color=c["text_muted"], anchor="w").pack(fill="x", pady=(3, 0))
            ctk.CTkLabel(inner, text=f"网卡 {net.get('portDeviceName') or '—'}   ·   MTU {net.get('mtu') or '—'}"
                                     f"   ·   选项 {'/'.join(net_flags(net)) or '无'}",
                         font=theme.font(11), text_color=c["text_faint"], anchor="w").pack(fill="x", pady=(2, 0))

    # ------------------------------------------------------------------ #
    def _copy_info(self) -> None:
        if self.show_all:
            text = "\n\n".join(net_info_text(n) for n in (self.app.summary or {}).get("networks") or [])
        else:
            text = net_info_text(self.net)
        self.clipboard_clear()
        self.clipboard_append(text)
        self.app.toast("网络信息已复制到剪贴板", "ok")

    def _edit_label(self) -> None:
        self.close()
        LabelDialog(self.app, self.app, self.net)

    def _save(self) -> None:
        payload: dict = {k: bool(v.get()) for k, v in self.vars.items()}
        raw = self.dns_entry.get().strip()
        servers = [s.strip() for s in raw.replace("，", ",").split(",") if s.strip()]
        payload["dns"] = {"servers": servers, "domain": "", "search": []}
        try:
            self.app.api.update(self.nwid, payload)
        except ZTError as exc:
            self.app.toast(str(exc), "err")
            return
        self.app.toast("网络配置已保存", "ok")
        self.close()
        self.app.poll()
