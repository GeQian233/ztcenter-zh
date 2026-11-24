"""已加入网络的显示顺序（拖拽自定义，持久化）。

默认顺序为内核 /network 返回顺序（近似「加入顺序」）；
未出现在保存顺序里的新网络追加到末尾。
"""
from __future__ import annotations

import json
import threading

from . import config


class NetworkOrderStore:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._order: list[str] = []
        self.load()

    # ------------------------------ IO ------------------------------ #
    def load(self) -> None:
        with self._lock:
            try:
                path = config.NET_ORDER_FILE
                if path.exists():
                    raw = json.loads(path.read_text(encoding="utf-8"))
                    if isinstance(raw, dict):
                        order = raw.get("order") or []
                        if isinstance(order, list):
                            self._order = [str(a).lower() for a in order if a]
            except Exception:
                self._order = []

    def save(self) -> None:
        with self._lock:
            try:
                config.NET_ORDER_FILE.write_text(
                    json.dumps({"version": 1, "order": self._order}, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
            except Exception:
                pass

    # ------------------------------ 读写 ------------------------------ #
    def order(self) -> list[str]:
        with self._lock:
            return list(self._order)

    def set_order(self, nwids: list[str]) -> None:
        with self._lock:
            self._order = [str(a).lower() for a in nwids if a]
            self.save()

    def reset(self) -> None:
        with self._lock:
            self._order = []
            self.save()


def _nwid(net: dict) -> str:
    return str(net.get("id") or net.get("nwid") or "").strip().lower()


def sort_networks(nets: list[dict], saved: list[str] | None = None) -> list[dict]:
    """按保存顺序排列；未记录的网络保持内核顺序并追加在后。"""
    saved = [str(a).lower() for a in (saved or [])]
    by_id = {_nwid(n): n for n in nets if _nwid(n)}
    ordered = [by_id[a] for a in saved if a in by_id]
    seen = {id(n) for n in ordered}
    ordered += [n for n in nets if id(n) not in seen]
    return ordered
