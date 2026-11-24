"""界面缩放：跟随系统 DPI 或手动指定 100%~200%。"""
from __future__ import annotations

import ctypes

import customtkinter as ctk

OPTIONS: dict[str, str] = {
    "跟随系统": "auto",
    "100%": "1.0",
    "125%": "1.25",
    "150%": "1.5",
    "175%": "1.75",
    "200%": "2.0",
}
LABELS: dict[str, str] = {v: k for k, v in OPTIONS.items()}


def system_scale() -> float:
    """系统 DPI 缩放（1.0 = 100%）。"""
    try:
        return float(ctypes.windll.shcore.GetScaleFactorForDevice(0)) / 100.0
    except Exception:
        pass
    try:
        dc = ctypes.windll.user32.GetDC(0)
        dpi = ctypes.windll.gdi32.GetDeviceCaps(dc, 88)  # LOGPIXELSX
        ctypes.windll.user32.ReleaseDC(0, dc)
        return max(1.0, dpi / 96.0)
    except Exception:
        return 1.0


def target_factor(settings: dict) -> float:
    mode = str(settings.get("ui_scale", "auto"))
    if mode in ("auto", "", "None"):
        return max(1.0, min(2.0, system_scale()))
    try:
        return max(1.0, min(2.0, float(mode)))
    except Exception:
        return max(1.0, min(2.0, system_scale()))


def apply(settings: dict) -> float:
    """应用缩放，返回实际使用的倍数。

    customtkinter 的 set_*_scaling 是在「系统 DPI 缩放」之上再乘算的，
    因此这里传入相对系数 factor / system，最终生效倍数恰为 factor。
    """
    factor = target_factor(settings)
    base = system_scale() or 1.0
    rel = max(0.5, min(3.0, factor / base))
    try:
        ctk.set_widget_scaling(rel)
        ctk.set_window_scaling(rel)
    except Exception:
        pass
    return factor
