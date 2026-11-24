"""通用界面组件。"""
from __future__ import annotations

import customtkinter as ctk

from . import theme


class Card(ctk.CTkFrame):
    def __init__(self, master, padding: int = 18, **kwargs):
        c = theme.C()
        kwargs.setdefault("fg_color", c["card"])
        kwargs.setdefault("corner_radius", 14)
        kwargs.setdefault("border_width", 1)
        kwargs.setdefault("border_color", c["border"])
        super().__init__(master, **kwargs)
        self._pad = padding
        self.body = ctk.CTkFrame(self, fg_color="transparent")
        self.body.pack(fill="both", expand=True, padx=padding, pady=padding)

    def title(self, text: str, sub: str = "") -> ctk.CTkFrame:
        c = theme.C()
        row = ctk.CTkFrame(self.body, fg_color="transparent")
        row.pack(fill="x", pady=(0, 10))
        ctk.CTkLabel(row, text=text, font=theme.font(14, "bold"),
                     text_color=c["text"], anchor="w").pack(side="left")
        if sub:
            ctk.CTkLabel(row, text=sub, font=theme.font(12),
                         text_color=c["text_muted"], anchor="w").pack(side="left", padx=(10, 0))
        return row


class Pill(ctk.CTkLabel):
    """圆角状态标签。"""

    def __init__(self, master, text: str, fg: str = "#4F46E5", bg: str = "#EEF0FF", **kwargs):
        super().__init__(
            master,
            text=text,
            fg_color=bg,
            text_color=fg,
            corner_radius=10,
            height=22,
            font=theme.font(11, "bold"),
            **kwargs,
        )
        self._pill_font = theme.font(11, "bold")

    def restyle(self, text: str, fg: str, bg: str) -> None:
        self.configure(text=text, text_color=fg, fg_color=bg)


class Dot(ctk.CTkCanvas):
    def __init__(self, master, color: str = "#16A34A", size: int = 8):
        c = theme.C()
        super().__init__(master, width=size, height=size, highlightthickness=0,
                         bg=c["card"], bd=0)
        self._size = size
        self._id = self.create_oval(0, 0, size, size, fill=color, outline=color)

    def set_color(self, color: str) -> None:
        self.itemconfigure(self._id, fill=color, outline=color)


def hline(master, pady: int = 10) -> ctk.CTkFrame:
    c = theme.C()
    line = ctk.CTkFrame(master, height=1, fg_color=c["border"])
    line.pack(fill="x", pady=pady)
    return line


def kv_row(master, key: str, value: str = "", mono: bool = False) -> tuple[ctk.CTkFrame, ctk.CTkLabel]:
    """左侧键名、右侧值的行，返回 (行, 值Label) 便于刷新。"""
    c = theme.C()
    row = ctk.CTkFrame(master, fg_color="transparent")
    row.pack(fill="x", pady=3)
    ctk.CTkLabel(row, text=key, font=theme.font(12), text_color=c["text_muted"],
                 width=118, anchor="w").pack(side="left")
    val = ctk.CTkLabel(
        row,
        text=value or "-",
        font=theme.font(12, "normal") if not mono else ctk.CTkFont(family="Consolas", size=12),
        text_color=c["text"],
        anchor="w",
        justify="left",
    )
    val.pack(side="left", fill="x", expand=True)
    return row, val


def section_label(master, text: str, pady: tuple[int, int] = (14, 6)) -> ctk.CTkLabel:
    c = theme.C()
    lb = ctk.CTkLabel(master, text=text, font=theme.font(12, "bold"),
                      text_color=c["text_muted"], anchor="w")
    lb.pack(fill="x", pady=pady)
    return lb


def primary_button(master, text: str, command, width: int = 0, **kwargs) -> ctk.CTkButton:
    c = theme.C()
    kwargs.setdefault("height", 34)
    kwargs.setdefault("corner_radius", 8)
    kwargs.setdefault("fg_color", c["accent"])
    kwargs.setdefault("hover_color", c["accent_hover"])
    kwargs.setdefault("text_color", "#FFFFFF")
    kwargs.setdefault("font", theme.font(13, "bold"))
    return ctk.CTkButton(master, text=text, command=command, width=width, **kwargs)


def ghost_button(master, text: str, command, width: int = 0, danger: bool = False, **kwargs) -> ctk.CTkButton:
    c = theme.C()
    kwargs.setdefault("height", 34)
    kwargs.setdefault("corner_radius", 8)
    kwargs.setdefault("fg_color", "transparent")
    kwargs.setdefault("hover_color", c["danger_soft"] if danger else c["nav_hover"])
    kwargs.setdefault("text_color", c["danger"] if danger else c["text_muted"])
    kwargs.setdefault("border_width", 1)
    kwargs.setdefault("border_color", c["border"])
    kwargs.setdefault("font", theme.font(12))
    return ctk.CTkButton(master, text=text, command=command, width=width, **kwargs)


def empty_state(master, title: str, hint: str = "") -> ctk.CTkFrame:
    c = theme.C()
    box = ctk.CTkFrame(master, fg_color="transparent")
    ctk.CTkLabel(box, text=title, font=theme.font(13, "bold"),
                 text_color=c["text_muted"]).pack(pady=(18, 4))
    if hint:
        ctk.CTkLabel(box, text=hint, font=theme.font(12),
                     text_color=c["text_faint"]).pack(pady=(0, 18))
    return box
