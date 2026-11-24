"""对端显示顺序：根节点固定置顶，其余支持自定义拖拽顺序并持久化。

- 根节点（PLANET / MOON）永远排在最前，顺序固定为内核返回顺序；
- 本机固定在最后，作为参照；
- 成员节点按用户拖拽后的顺序排列；未出现在保存顺序里的新对端追加到末尾；
- 默认（无自定义顺序时）即内核 /peer 返回顺序，近似「加入顺序」。
"""
from __future__ import annotations

import json
import threading

from . import config

ROOT_ROLES = ("PLANET", "MOON")


class PeerOrderStore:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._order: list[str] = []
        self.load()

    # ------------------------------ IO ------------------------------ #
    def load(self) -> None:
        with self._lock:
            try:
                path = config.PEER_ORDER_FILE
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
                config.PEER_ORDER_FILE.write_text(
                    json.dumps({"version": 1, "order": self._order}, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
            except Exception:
                pass

    # ------------------------------ 读写 ------------------------------ #
    def order(self) -> list[str]:
        with self._lock:
            return list(self._order)

    def set_order(self, addresses: list[str]) -> None:
        with self._lock:
            self._order = [str(a).lower() for a in addresses if a]
            self.save()

    def reset(self) -> None:
        with self._lock:
            self._order = []
            self.save()


def _addr(peer: dict) -> str:
    return str(peer.get("address", "")).lower()


def _is_root(peer: dict) -> bool:
    return str(peer.get("role", "")).upper() in ROOT_ROLES


def sort_peers(peers: list[dict], self_addr: str = "", saved: list[str] | None = None) -> list[dict]:
    """根节点置顶 → 成员按自定义顺序（新节点追加）→ 本机置底。"""
    self_addr = (self_addr or "").lower()
    saved = [str(a).lower() for a in (saved or [])]

    roots = [p for p in peers if _is_root(p)]
    me = [p for p in peers if _addr(p) == self_addr and not _is_root(p)]
    members = [p for p in peers
               if not _is_root(p) and _addr(p) != self_addr]

    by_addr = {_addr(p): p for p in members}
    ordered = [by_addr[a] for a in saved if a in by_addr]
    seen = {id(p) for p in ordered}
    ordered += [p for p in members if id(p) not in seen]  # 未记录的新对端保持内核顺序，追加在后
    return roots + ordered + me


def member_addresses(peers: list[dict], self_addr: str = "") -> list[str]:
    """可拖拽（成员）节点的地址列表，按当前显示顺序。"""
    self_addr = (self_addr or "").lower()
    return [_addr(p) for p in peers
            if not _is_root(p) and _addr(p) != self_addr]
