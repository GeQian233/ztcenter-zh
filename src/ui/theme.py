"""界面主题：配色与字体。"""
from __future__ import annotations

import customtkinter as ctk

FONT_FAMILY = "Microsoft YaHei UI"

LIGHT = {
    "bg": "#F3F4F8",
    "sidebar": "#FFFFFF",
    "card": "#FFFFFF",
    "card_alt": "#F8F9FC",
    "border": "#E5E7EF",
    "text": "#1B2030",
    "text_muted": "#6B7280",
    "text_faint": "#9AA1AE",
    "accent": "#4F46E5",
    "accent_hover": "#4338CA",
    "accent_soft": "#EEF0FF",
    "success": "#16A34A",
    "success_soft": "#E8F7EE",
    "warn": "#D97706",
    "warn_soft": "#FDF3E3",
    "danger": "#DC2626",
    "danger_soft": "#FDECEC",
    "nav_hover": "#F1F2F7",
    "nav_active": "#EEF0FF",
    "input": "#F7F8FB",
    "shadow": "#E8EAF2",
}

DARK = {
    "bg": "#14161C",
    "sidebar": "#191C24",
    "card": "#1E222B",
    "card_alt": "#232833",
    "border": "#2C323E",
    "text": "#EDEFF4",
    "text_muted": "#9BA3B2",
    "text_faint": "#6E7686",
    "accent": "#7C83FF",
    "accent_hover": "#6E75F5",
    "accent_soft": "#252A44",
    "success": "#34D399",
    "success_soft": "#17301F",
    "warn": "#FBBF24",
    "warn_soft": "#33280F",
    "danger": "#F87171",
    "danger_soft": "#3A1D1D",
    "nav_hover": "#222732",
    "nav_active": "#252A44",
    "input": "#232833",
    "shadow": "#0F1116",
}

_current = "light"


def set_mode(mode: str) -> None:
    global _current
    _current = "dark" if mode == "dark" else "light"
    ctk.set_appearance_mode(_current)


def C() -> dict:
    return DARK if _current == "dark" else LIGHT


def font(size: int = 13, weight: str = "normal") -> ctk.CTkFont:
    return ctk.CTkFont(family=FONT_FAMILY, size=size, weight=weight)


def status_style(status: str) -> tuple[str, str, str]:
    """网络状态 → (文字, 前景色, 背景色)。"""
    c = C()
    s = (status or "").upper()
    if s == "OK":
        return "已连接", c["success"], c["success_soft"]
    if s in ("REQUESTING_CONFIGURATION", "REQUESTING_ACCESS"):
        return "等待授权", c["warn"], c["warn_soft"]
    if s in ("ACCESS_DENIED",):
        return "拒绝访问", c["danger"], c["danger_soft"]
    if s in ("NOT_FOUND",):
        return "网络不存在", c["danger"], c["danger_soft"]
    if s in ("PORT_ERROR",):
        return "端口错误", c["danger"], c["danger_soft"]
    if s in ("CLIENT_TOO_OLD",):
        return "客户端过旧", c["warn"], c["warn_soft"]
    if not s:
        return "未知", c["text_muted"], c["card_alt"]
    return status, c["text_muted"], c["card_alt"]
