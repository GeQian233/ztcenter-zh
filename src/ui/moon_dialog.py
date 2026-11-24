"""MOON 节点管理弹窗：添加（导入文件 / 粘贴内容）、查看、删除。"""
from __future__ import annotations

import threading
from tkinter import filedialog

import customtkinter as ctk

from core import config, moon, syswin
from ui import theme
from ui.dialogs import Modal, confirm
from ui.widgets import Pill, empty_state, ghost_button, primary_button


class MoonDialog(Modal):
    def __init__(self, app):
        self.app = app
        super().__init__(app, "MOON 节点管理", width=740, height=700)
        c = theme.C()

        ctk.CTkLabel(
            self.body,
            text="MOON 是自建的卫星根节点，用于加速或绕开官方根节点；可同时配置多个，与 planet 不冲突。",
            font=theme.font(12), text_color=c["text_muted"], anchor="w", justify="left",
            wraplength=620,
        ).pack(fill="x", padx=12, pady=(4, 10))

        # ---------------- 添加区 ---------------- #
        add = ctk.CTkFrame(self.body, fg_color=c["card_alt"], corner_radius=10)
        add.pack(fill="x", padx=8, pady=(0, 10))
        inner = ctk.CTkFrame(add, fg_color="transparent")
        inner.pack(fill="x", padx=14, pady=12)

        ctk.CTkLabel(inner, text="导入 .moon 文件", font=theme.font(12, "bold"),
                     text_color=c["text"], anchor="w").pack(fill="x")
        row1 = ctk.CTkFrame(inner, fg_color="transparent")
        row1.pack(fill="x", pady=(6, 0))
        self.path_entry = ctk.CTkEntry(row1, height=32, corner_radius=8, fg_color=c["input"],
                                       border_color=c["border"], placeholder_text="选择或粘贴 .moon 文件路径",
                                       font=theme.font(12))
        self.path_entry.pack(side="left", fill="x", expand=True, padx=(0, 6))
        ghost_button(row1, "浏览…", self._browse, width=70, height=32).pack(side="left", padx=(0, 6))
        primary_button(row1, "添加", self._add_path, width=70, height=32).pack(side="left")

        ctk.CTkLabel(inner, text="或粘贴内容（十六进制 / Base64）", font=theme.font(12, "bold"),
                     text_color=c["text"], anchor="w").pack(fill="x", pady=(12, 0))
        row2 = ctk.CTkFrame(inner, fg_color="transparent")
        row2.pack(fill="x", pady=(6, 0))
        self.text_entry = ctk.CTkEntry(row2, height=32, corner_radius=8, fg_color=c["input"],
                                       border_color=c["border"], placeholder_text="粘贴 moon 文件内容",
                                       font=theme.font(11))
        self.text_entry.pack(side="left", fill="x", expand=True, padx=(0, 6))
        ghost_button(row2, "从文本添加", self._add_text, width=100, height=32).pack(side="left")

        # ---------------- 列表区 ---------------- #
        head = ctk.CTkFrame(self.body, fg_color="transparent")
        head.pack(fill="x", padx=12, pady=(6, 4))
        ctk.CTkLabel(head, text="已配置的 MOON", font=theme.font(13, "bold"),
                     text_color=c["text"], anchor="w").pack(side="left")
        self.count_pill = Pill(head, "0", fg=c["accent"], bg=c["accent_soft"])
        self.count_pill.pack(side="left", padx=8)
        ghost_button(head, "刷新", self._reload, width=60, height=26).pack(side="right")
        ghost_button(head, "打开 moons.d", self._open_dir, width=104, height=26).pack(side="right", padx=6)

        self.list_box = ctk.CTkFrame(self.body, fg_color="transparent")
        self.list_box.pack(fill="both", expand=True, padx=8, pady=(0, 8))

        ghost_button(self.footer, "关闭", self.close, width=80).pack(side="right")
        self._reload()

    # ------------------------------------------------------------------ #
    def _open_dir(self) -> None:
        d = moon.moon_dir()
        d.mkdir(parents=True, exist_ok=True)
        syswin.open_path(d)

    def _browse(self) -> None:
        path = filedialog.askopenfilename(
            parent=self, title="选择 moon 文件",
            filetypes=[("moon 文件", "*.moon"), ("所有文件", "*.*")],
        )
        if path:
            self.path_entry.delete(0, "end")
            self.path_entry.insert(0, path)

    def _add_path(self) -> None:
        path = self.path_entry.get().strip().strip('"')
        if not path:
            self.app.toast("请先选择 .moon 文件", "warn")
            return
        self._run(lambda: moon.add_file(path), "添加 MOON")

    def _add_text(self) -> None:
        text = self.text_entry.get().strip()
        if not text:
            self.app.toast("请先粘贴 moon 内容", "warn")
            return

        def op():
            data = moon.decode_payload(text)
            return moon.add_bytes(data)

        self._run(op, "添加 MOON")

    def _delete(self, mid: str) -> None:
        if not confirm(self.app, "移除 MOON",
                       f"确定移除 MOON {mid} 吗？\n\n将从 moons.d 删除该文件并执行 deorbit（自动备份到本程序数据目录）。",
                       ok_text="移除", danger=True):
            return
        self._run(lambda: moon.remove(mid), "移除 MOON")

    # ------------------------------------------------------------------ #
    def _run(self, fn, label: str) -> None:
        if not syswin.is_admin():
            self.app.toast(f"{label}需要管理员权限", "err")
            return
        self.app.toast(f"{label}处理中…")

        def worker() -> None:
            try:
                msg = fn()
                self.app.dispatch.call(lambda: self._done(msg, None))
            except Exception as exc:
                self.app.dispatch.call(lambda e=exc: self._done("", e))

        threading.Thread(target=worker, daemon=True, name="moon-op").start()

    def _done(self, msg: str, err) -> None:
        if err is not None:
            self.app.toast(f"失败：{err}", "err")
        else:
            self.app.toast(msg, "ok")
            self.path_entry.delete(0, "end")
            self.text_entry.delete(0, "end")
        self.app.poll()
        self.after(400, self._reload)

    # ------------------------------------------------------------------ #
    def _reload(self) -> None:
        c = theme.C()
        for w in self.list_box.winfo_children():
            w.destroy()
        items = moon.list_local()
        peers = (self.app.summary or {}).get("peers") if self.app.summary else []
        active = moon.runtime_ids(peers)
        self.count_pill.configure(text=str(len(items)))

        if not items:
            empty_state(self.list_box, "尚未配置 MOON",
                        "导入官方 moon 文件（需在 moon 服务器上生成）后点击「添加」").pack(fill="x")
            return

        for it in items:
            card = ctk.CTkFrame(self.list_box, fg_color=c["card_alt"], corner_radius=10,
                                border_width=1, border_color=c["border"])
            card.pack(fill="x", pady=4, padx=4)
            inner = ctk.CTkFrame(card, fg_color="transparent")
            inner.pack(fill="x", padx=12, pady=10)

            left = ctk.CTkFrame(inner, fg_color="transparent")
            left.pack(side="left", fill="x", expand=True)
            line = ctk.CTkFrame(left, fg_color="transparent")
            line.pack(fill="x")
            ctk.CTkLabel(line, text=it["id"], font=ctk.CTkFont(family="Consolas", size=13, weight="bold"),
                         text_color=c["text"]).pack(side="left")
            mid = it["id"].lower()
            if it.get("error"):
                Pill(line, "文件异常", fg=c["danger"], bg=c["danger_soft"]).pack(side="left", padx=8)
            elif mid in active:
                Pill(line, "已生效", fg=c["success"], bg=c["success_soft"]).pack(side="left", padx=8)
            else:
                Pill(line, "待生效", fg=c["text_muted"], bg=c["card"]).pack(side="left", padx=8)

            if it.get("error"):
                sub = it["error"]
            else:
                sub = f"世界时间 {it['timestamp_text']}   ·   {it['size']} 字节   ·   {it.get('mtime', '')}"
            ctk.CTkLabel(left, text=sub, font=ctk.CTkFont(family="Consolas", size=11),
                         text_color=c["text_faint"], anchor="w").pack(anchor="w", pady=(4, 0))

            ghost_button(inner, "删除", lambda m=mid: self._delete(m), width=60, height=28,
                         danger=True).pack(side="right")
