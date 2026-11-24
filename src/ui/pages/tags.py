"""标签管理页：集中为所有网络命名、着色、分组。"""
from __future__ import annotations

import customtkinter as ctk

from ui import theme
from ui.dialogs import LabelDialog, confirm
from ui.widgets import Card, Pill, empty_state, ghost_button, primary_button


class TagsPage(ctk.CTkFrame):
    def __init__(self, master, app):
        super().__init__(master, fg_color="transparent")
        self.app = app
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        c = theme.C()
        head = Card(self, padding=16)
        head.grid(row=0, column=0, sticky="ew", padx=6, pady=(4, 6))
        head.title("网络标签", "标签仅保存在本机，用于界面显示与分组，不影响网络配置")
        row = ctk.CTkFrame(head.body, fg_color="transparent")
        row.pack(fill="x")
        self.stat = ctk.CTkLabel(row, text="", font=theme.font(12), text_color=c["text_muted"])
        self.stat.pack(side="left")
        ghost_button(row, "清理失效标签", self._cleanup, width=110, height=30).pack(side="right", padx=4)
        ghost_button(row, "按网络名批量初始化", self._autofill, width=150, height=30).pack(side="right", padx=4)

        listcard = Card(self, padding=16)
        listcard.grid(row=1, column=0, sticky="nsew", padx=6, pady=(0, 6))
        listcard.title("标签列表")
        self.list_box = ctk.CTkScrollableFrame(listcard.body, fg_color="transparent",
                                               scrollbar_button_color=c["border"])
        self.list_box.pack(fill="both", expand=True)

    # ------------------------------------------------------------------ #
    def refresh(self) -> None:
        c = theme.C()
        for w in self.list_box.winfo_children():
            w.destroy()
        data = self.app.summary
        if not data:
            empty_state(self.list_box, "正在读取网络列表…").pack(fill="x")
            return
        nets = data.get("networks", [])
        if not nets:
            empty_state(self.list_box, "尚未加入任何网络",
                        "先到「网络管理」加入网络，再回来设置标签").pack(fill="x")
            return

        labelled = sum(1 for n in nets if self.app.labels.get((n.get("id") or "").lower())["label"])
        self.stat.configure(text=f"共 {len(nets)} 个网络，其中 {labelled} 个已自定义名称")

        groups: dict[str, list[dict]] = {}
        for n in nets:
            meta = self.app.labels.get((n.get("id") or "").lower())
            groups.setdefault(meta["group"] or "未分组", []).append(n)

        for group in sorted(groups, key=lambda g: (g == "未分组", g)):
            ctk.CTkLabel(self.list_box, text=f"{group}  ({len(groups[group])})",
                         font=theme.font(12, "bold"), text_color=c["text_muted"],
                         anchor="w").pack(fill="x", padx=6, pady=(10, 2))
            for net in groups[group]:
                self._row(net)

    def _row(self, net: dict) -> None:
        c = theme.C()
        nwid = (net.get("id") or net.get("nwid") or "").lower()
        meta = self.app.labels.get(nwid)
        card = ctk.CTkFrame(self.list_box, fg_color=c["card_alt"], corner_radius=10,
                            border_width=1, border_color=c["border"])
        card.pack(fill="x", pady=3, padx=4)
        inner = ctk.CTkFrame(card, fg_color="transparent")
        inner.pack(fill="x", padx=12, pady=10)

        ctk.CTkFrame(inner, width=10, height=10, fg_color=meta["color"],
                     corner_radius=5).pack(side="left", padx=(0, 10))
        col = ctk.CTkFrame(inner, fg_color="transparent")
        col.pack(side="left", fill="x", expand=True)
        name = meta["label"] or net.get("name") or "（未命名）"
        ctk.CTkLabel(col, text=name, font=theme.font(13, "bold"),
                     text_color=c["text"], anchor="w").pack(anchor="w")
        sub = nwid + (f"   ·   {meta['note']}" if meta["note"] else "")
        ctk.CTkLabel(col, text=sub, font=ctk.CTkFont(family="Consolas", size=11),
                     text_color=c["text_faint"], anchor="w").pack(anchor="w")

        text, fg, bg = theme.status_style(net.get("status", ""))
        Pill(inner, text, fg=fg, bg=bg).pack(side="right", padx=(6, 0))
        ghost_button(inner, "编辑标签", lambda n=net: LabelDialog(self.app, self.app, n),
                     width=84, height=30).pack(side="right", padx=6)

    # ------------------------------------------------------------------ #
    def _cleanup(self) -> None:
        data = self.app.summary or {}
        active = {(n.get("id") or "").lower() for n in data.get("networks", [])}
        stale = [k for k in self.app.labels.all() if k not in active]
        if not stale:
            self.app.toast("没有失效标签", "ok")
            return
        if not confirm(self.app, "清理失效标签",
                       f"检测到 {len(stale)} 个标签对应的网络已退出，是否删除这些标签记录？",
                       ok_text="删除", danger=True):
            return
        for k in stale:
            self.app.labels.remove(k)
        self.app.toast(f"已清理 {len(stale)} 条失效标签", "ok")
        self.refresh()

    def _autofill(self) -> None:
        data = self.app.summary or {}
        nets = data.get("networks", [])
        count = 0
        for net in nets:
            nwid = (net.get("id") or "").lower()
            meta = self.app.labels.get(nwid)
            if meta["label"]:
                continue
            name = (net.get("name") or "").strip()
            if name:
                self.app.labels.set(nwid, label=name, color=meta["color"],
                                    group=meta["group"], note=meta["note"])
                count += 1
        self.app.toast(f"已按网络名初始化 {count} 个标签" if count else "无需初始化", "ok")
        self.refresh()
