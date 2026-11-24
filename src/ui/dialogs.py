"""模态对话框：基础弹窗、确认框、标签编辑器。"""
from __future__ import annotations

import customtkinter as ctk

from core.labels import DEFAULT_COLOR, LABEL_COLORS
from ui import theme
from ui.widgets import ghost_button, primary_button


class Modal(ctk.CTkToplevel):
    def __init__(self, parent, title: str, width: int = 560, height: int = 560):
        c = theme.C()
        super().__init__(parent, fg_color=c["card"])
        self.parent = parent
        self.title(title)
        self.resizable(False, False)
        self.transient(parent)
        self.protocol("WM_DELETE_WINDOW", self.close)

        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", padx=22, pady=(18, 6))
        ctk.CTkLabel(header, text=title, font=theme.font(16, "bold"),
                     text_color=c["text"], anchor="w").pack(side="left")

        # 先固定底部按钮区，再让内容区占用剩余空间：
        # 否则内容区以 expand=True 先占满，窗口偏小时 footer 会被压成 0 高度（按钮消失）
        self.footer = ctk.CTkFrame(self, fg_color="transparent")
        self.footer.pack(side="bottom", fill="x", padx=22, pady=(6, 18))

        self.body = ctk.CTkScrollableFrame(self, fg_color="transparent",
                                           scrollbar_button_color=c["border"])
        self.body.pack(side="top", fill="both", expand=True, padx=14, pady=(0, 6))

        self.geometry(f"{width}x{height}")
        self.after(30, self._center)
        self.after(60, lambda: self.grab_set())

    def _center(self) -> None:
        try:
            self.update_idletasks()
            px, py = self.parent.winfo_rootx(), self.parent.winfo_rooty()
            pw, ph = self.parent.winfo_width(), self.parent.winfo_height()
            w, h = self.winfo_width(), self.winfo_height()
            self.geometry(f"+{px + (pw - w) // 2}+{py + (ph - h) // 3}")
        except Exception:
            pass

    def close(self) -> None:
        try:
            self.grab_release()
        except Exception:
            pass
        self.destroy()


class ConfirmDialog(Modal):
    def __init__(self, parent, title: str, message: str, ok_text: str = "确定",
                 danger: bool = False):
        import math

        c = theme.C()
        # 按文本行数自适应高度，避免内容被裁切或按钮被挤出
        lines = sum(max(1, math.ceil(len(part) / 30)) for part in (message or "").split("\n"))
        height = max(220, min(560, 150 + lines * 24))
        super().__init__(parent, title, width=480, height=height)
        ctk.CTkLabel(self.body, text=message, font=theme.font(13), text_color=c["text"],
                     anchor="w", justify="left", wraplength=400).pack(fill="x", padx=10, pady=14)
        self.result = False
        primary_button(self.footer, ok_text, self._ok, width=96,
                       fg_color=c["danger"] if danger else c["accent"],
                       hover_color="#B91C1C" if danger else c["accent_hover"]).pack(side="right", padx=(8, 0))
        ghost_button(self.footer, "取消", self.close, width=80).pack(side="right")

    def _ok(self) -> None:
        self.result = True
        self.close()


def confirm(parent, title: str, message: str, ok_text: str = "确定", danger: bool = False) -> bool:
    dlg = ConfirmDialog(parent, title, message, ok_text, danger)
    parent.wait_window(dlg)
    return dlg.result


class ColorPicker(ctk.CTkFrame):
    def __init__(self, master, initial: str = DEFAULT_COLOR):
        c = theme.C()
        super().__init__(master, fg_color="transparent")
        self.value = initial
        self._buttons: dict[str, ctk.CTkButton] = {}
        row = ctk.CTkFrame(self, fg_color="transparent")
        row.pack(anchor="w")
        for i, (name, hexv) in enumerate(LABEL_COLORS.items()):
            b = ctk.CTkButton(
                row, text="", width=26, height=26, corner_radius=13,
                fg_color=hexv, hover_color=hexv,
                border_width=2, border_color=c["card"] if hexv != initial else c["text"],
                command=lambda h=hexv: self.select(h),
            )
            b.pack(side="left", padx=3, pady=3)
            b.bind("<Enter>", lambda e, n=name: self.master.winfo_toplevel().title())
            self._buttons[hexv] = b
        self._name_label = ctk.CTkLabel(self, text=self._name_of(initial), font=theme.font(11),
                                        text_color=c["text_muted"])
        self._name_label.pack(anchor="w", padx=4, pady=(2, 0))

    @staticmethod
    def _name_of(hexv: str) -> str:
        for name, h in LABEL_COLORS.items():
            if h.lower() == hexv.lower():
                return name
        return hexv

    def select(self, hexv: str) -> None:
        c = theme.C()
        self.value = hexv
        for h, b in self._buttons.items():
            b.configure(border_color=c["text"] if h == hexv else c["card"])
        self._name_label.configure(text=self._name_of(hexv))


class LabelDialog(Modal):
    """编辑单个网络的标签：显示名称、颜色、分组、备注。"""

    def __init__(self, parent, app, net: dict):
        nwid = (net.get("id") or net.get("nwid") or "").lower()
        self.app = app
        self.nwid = nwid
        meta = app.labels.get(nwid)
        super().__init__(parent, "编辑网络标签", width=520, height=580)
        c = theme.C()

        ctk.CTkLabel(self.body, text=f"网络 ID：{nwid}", font=ctk.CTkFont(family="Consolas", size=12),
                     text_color=c["text_faint"], anchor="w").pack(fill="x", padx=10)
        ctk.CTkLabel(self.body, text=f"网络名称：{net.get('name') or '（无）'}",
                     font=theme.font(12), text_color=c["text_muted"], anchor="w").pack(fill="x", padx=10, pady=(2, 12))

        ctk.CTkLabel(self.body, text="显示名称", font=theme.font(12, "bold"),
                     text_color=c["text"], anchor="w").pack(fill="x", padx=10, pady=(4, 4))
        self.name_entry = ctk.CTkEntry(self.body, height=34, corner_radius=8,
                                       fg_color=c["input"], border_color=c["border"],
                                       placeholder_text="例如：公司内网 / 家庭 NAS",
                                       font=theme.font(13))
        self.name_entry.pack(fill="x", padx=10)
        if meta["label"]:
            self.name_entry.insert(0, meta["label"])

        ctk.CTkLabel(self.body, text="标签颜色", font=theme.font(12, "bold"),
                     text_color=c["text"], anchor="w").pack(fill="x", padx=10, pady=(14, 4))
        self.color = ColorPicker(self.body, meta["color"])
        self.color.pack(fill="x", padx=10)

        ctk.CTkLabel(self.body, text="分组", font=theme.font(12, "bold"),
                     text_color=c["text"], anchor="w").pack(fill="x", padx=10, pady=(14, 4))
        self.group_entry = ctk.CTkEntry(self.body, height=34, corner_radius=8,
                                        fg_color=c["input"], border_color=c["border"],
                                        placeholder_text="例如：办公 / 家庭 / 测试",
                                        font=theme.font(13))
        self.group_entry.pack(fill="x", padx=10)
        if meta["group"]:
            self.group_entry.insert(0, meta["group"])
        groups = app.labels.groups()
        if groups:
            chips = ctk.CTkFrame(self.body, fg_color="transparent")
            chips.pack(fill="x", padx=10, pady=(6, 0))
            ctk.CTkLabel(chips, text="已有分组：", font=theme.font(11),
                         text_color=c["text_faint"]).pack(side="left")
            for g in groups[:6]:
                ctk.CTkButton(chips, text=g, width=0, height=22, corner_radius=6,
                              fg_color=c["card_alt"], hover_color=c["nav_hover"],
                              text_color=c["text_muted"], font=theme.font(11),
                              command=lambda gg=g: self._fill_group(gg)).pack(side="left", padx=2)

        ctk.CTkLabel(self.body, text="备注", font=theme.font(12, "bold"),
                     text_color=c["text"], anchor="w").pack(fill="x", padx=10, pady=(14, 4))
        self.note_entry = ctk.CTkEntry(self.body, height=34, corner_radius=8,
                                       fg_color=c["input"], border_color=c["border"],
                                       placeholder_text="可选，记录用途或联系人",
                                       font=theme.font(13))
        self.note_entry.pack(fill="x", padx=10, pady=(0, 10))
        if meta["note"]:
            self.note_entry.insert(0, meta["note"])

        primary_button(self.footer, "保存", self._save, width=96).pack(side="right", padx=(8, 0))
        ghost_button(self.footer, "取消", self.close, width=80).pack(side="right")
        ghost_button(self.footer, "清除标签", self._clear, width=90).pack(side="left")

    def _fill_group(self, g: str) -> None:
        self.group_entry.delete(0, "end")
        self.group_entry.insert(0, g)

    def _save(self) -> None:
        self.app.labels.set(
            self.nwid,
            label=self.name_entry.get().strip(),
            color=self.color.value,
            group=self.group_entry.get().strip(),
            note=self.note_entry.get().strip(),
        )
        self.app.toast("标签已保存", "ok")
        self.close()
        page = self.app._pages.get(self.app._current_page)
        if page is not None:
            page.refresh()

    def _clear(self) -> None:
        self.app.labels.remove(self.nwid)
        self.app.toast("标签已清除", "ok")
        self.close()
        page = self.app._pages.get(self.app._current_page)
        if page is not None:
            page.refresh()

class PeerLabelDialog(Modal):
    """编辑单个对端的本地标签：名称、颜色、分组、备注。

    ZeroTier 协议不提供节点名称，这里用本地标签实现「知道是谁连上来了」。
    """

    def __init__(self, parent, app, peer: dict, on_saved=None):
        self.app = app
        self.peer = peer
        self.address = str(peer.get("address", "")).lower()
        self.on_saved = on_saved
        meta = app.peer_labels.get(self.address)
        super().__init__(parent, "编辑对端标签", width=520, height=610)
        c = theme.C()

        role = str(peer.get("role", "")).upper()
        role_text = {"PLANET": "根节点", "MOON": "卫星节点", "LEAF": "成员节点"}.get(role, role or "未知")
        ctk.CTkLabel(self.body, text=f"对端地址：{self.address}",
                     font=ctk.CTkFont(family="Consolas", size=12),
                     text_color=c["text_faint"], anchor="w").pack(fill="x", padx=10)
        ctk.CTkLabel(self.body, text=f"节点类型：{role_text}    ·    路径：{peer.get('paths') and peer['paths'][0].get('address') or '—'}",
                     font=theme.font(12), text_color=c["text_muted"], anchor="w").pack(
            fill="x", padx=10, pady=(2, 12))

        ctk.CTkLabel(self.body, text="显示名称", font=theme.font(12, "bold"),
                     text_color=c["text"], anchor="w").pack(fill="x", padx=10, pady=(4, 4))
        self.name_entry = ctk.CTkEntry(self.body, height=34, corner_radius=8,
                                       fg_color=c["input"], border_color=c["border"],
                                       placeholder_text="例如：家里的 NAS / 同事小明 / 机房跳板机",
                                       font=theme.font(13))
        self.name_entry.pack(fill="x", padx=10)
        if meta["label"]:
            self.name_entry.insert(0, meta["label"])

        ctk.CTkLabel(self.body, text="标签颜色", font=theme.font(12, "bold"),
                     text_color=c["text"], anchor="w").pack(fill="x", padx=10, pady=(14, 4))
        self.color = ColorPicker(self.body, meta["color"])
        self.color.pack(fill="x", padx=10)

        ctk.CTkLabel(self.body, text="分组", font=theme.font(12, "bold"),
                     text_color=c["text"], anchor="w").pack(fill="x", padx=10, pady=(14, 4))
        self.group_entry = ctk.CTkEntry(self.body, height=34, corner_radius=8,
                                        fg_color=c["input"], border_color=c["border"],
                                        placeholder_text="例如：家人 / 同事 / 服务器",
                                        font=theme.font(13))
        self.group_entry.pack(fill="x", padx=10)
        if meta["group"]:
            self.group_entry.insert(0, meta["group"])
        groups = app.peer_labels.groups()
        if groups:
            chips = ctk.CTkFrame(self.body, fg_color="transparent")
            chips.pack(fill="x", padx=10, pady=(6, 0))
            ctk.CTkLabel(chips, text="已有分组：", font=theme.font(11),
                         text_color=c["text_faint"]).pack(side="left")
            for g in groups[:6]:
                ctk.CTkButton(chips, text=g, width=0, height=22, corner_radius=6,
                              fg_color=c["card_alt"], hover_color=c["nav_hover"],
                              text_color=c["text_muted"], font=theme.font(11),
                              command=lambda gg=g: self._fill_group(gg)).pack(side="left", padx=2)

        ctk.CTkLabel(self.body, text="备注", font=theme.font(12, "bold"),
                     text_color=c["text"], anchor="w").pack(fill="x", padx=10, pady=(14, 4))
        self.note_entry = ctk.CTkEntry(self.body, height=34, corner_radius=8,
                                       fg_color=c["input"], border_color=c["border"],
                                       placeholder_text="可选，记录归属或联系方式",
                                       font=theme.font(13))
        self.note_entry.pack(fill="x", padx=10, pady=(0, 10))
        if meta["note"]:
            self.note_entry.insert(0, meta["note"])

        primary_button(self.footer, "保存", self._save, width=96).pack(side="right", padx=(8, 0))
        ghost_button(self.footer, "取消", self.close, width=80).pack(side="right")
        ghost_button(self.footer, "清除标签", self._clear, width=90).pack(side="left")

    def _fill_group(self, g: str) -> None:
        self.group_entry.delete(0, "end")
        self.group_entry.insert(0, g)

    def _save(self) -> None:
        self.app.peer_labels.set(
            self.address,
            label=self.name_entry.get().strip(),
            color=self.color.value,
            group=self.group_entry.get().strip(),
            note=self.note_entry.get().strip(),
        )
        self.app.toast("对端标签已保存", "ok")
        self.close()
        if self.on_saved:
            self.on_saved()

    def _clear(self) -> None:
        self.app.peer_labels.remove(self.address)
        self.app.toast("对端标签已清除", "ok")
        self.close()
        if self.on_saved:
            self.on_saved()
