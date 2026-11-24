"""网络标签存储：自定义显示名、颜色、分组、备注（本地持久化）。"""
from __future__ import annotations

import json
import threading
import time

from . import config

LABEL_COLORS = {
    "靛蓝": "#4F46E5",
    "天蓝": "#0284C7",
    "青色": "#0D9488",
    "绿色": "#16A34A",
    "琥珀": "#D97706",
    "橙红": "#EA580C",
    "玫红": "#DB2777",
    "紫色": "#7C3AED",
    "石板": "#475569",
    "灰色": "#6B7280",
}
DEFAULT_COLOR = "#4F46E5"


class LabelStore:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._data: dict = {"version": 1, "networks": {}}
        self.load()

    # ------------------------------ IO ------------------------------ #
    def load(self) -> None:
        with self._lock:
            try:
                if config.LABELS_FILE.exists():
                    raw = json.loads(config.LABELS_FILE.read_text(encoding="utf-8"))
                    if isinstance(raw, dict):
                        raw.setdefault("version", 1)
                        raw.setdefault("networks", {})
                        self._data = raw
            except Exception:
                self._data = {"version": 1, "networks": {}}

    def save(self) -> None:
        with self._lock:
            try:
                config.LABELS_FILE.write_text(
                    json.dumps(self._data, ensure_ascii=False, indent=2), encoding="utf-8"
                )
            except Exception:
                pass

    # ------------------------------ 读写 ------------------------------ #
    def get(self, nwid: str) -> dict:
        with self._lock:
            item = self._data["networks"].get(nwid.lower(), {})
            return {
                "label": item.get("label", ""),
                "color": item.get("color", DEFAULT_COLOR),
                "group": item.get("group", ""),
                "note": item.get("note", ""),
                "updated": item.get("updated", 0),
            }

    def set(self, nwid: str, label: str = "", color: str = DEFAULT_COLOR,
            group: str = "", note: str = "") -> None:
        with self._lock:
            key = nwid.lower()
            if not any([label.strip(), group.strip(), note.strip()]) and color == DEFAULT_COLOR:
                self._data["networks"].pop(key, None)
            else:
                self._data["networks"][key] = {
                    "label": label.strip(),
                    "color": color,
                    "group": group.strip(),
                    "note": note.strip(),
                    "updated": int(time.time()),
                }
            self.save()

    def remove(self, nwid: str) -> None:
        with self._lock:
            self._data["networks"].pop(nwid.lower(), None)
            self.save()

    def all(self) -> dict:
        with self._lock:
            return dict(self._data["networks"])

    def groups(self) -> list[str]:
        with self._lock:
            groups = {v.get("group", "").strip() for v in self._data["networks"].values()}
            return sorted(g for g in groups if g)

    def display_name(self, net: dict) -> str:
        """优先使用自定义标签，其次网络自身名称，最后短 ID。"""
        nwid = (net.get("id") or net.get("nwid") or "").lower()
        custom = self.get(nwid)["label"]
        if custom:
            return custom
        name = (net.get("name") or "").strip()
        if name:
            return name
        return nwid[:8] if nwid else "未命名网络"

    def color_of(self, nwid: str) -> str:
        return self.get(nwid)["color"]
