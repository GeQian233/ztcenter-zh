"""对端（peer）标签存储：自定义名称、分组、备注、颜色（本地持久化）。

对端的唯一标识是 10 位 ZeroTier 地址；协议不提供节点名称，
因此这里用本地标签实现「知道是谁连上来了」。
"""
from __future__ import annotations

import json
import threading
import time

from . import config
from .labels import DEFAULT_COLOR


class PeerLabelStore:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._data: dict = {"version": 1, "peers": {}}
        self.load()

    # ------------------------------ IO ------------------------------ #
    def load(self) -> None:
        with self._lock:
            try:
                path = config.PEER_LABELS_FILE
                if path.exists():
                    raw = json.loads(path.read_text(encoding="utf-8"))
                    if isinstance(raw, dict):
                        raw.setdefault("version", 1)
                        raw.setdefault("peers", {})
                        self._data = raw
            except Exception:
                self._data = {"version": 1, "peers": {}}

    def save(self) -> None:
        with self._lock:
            try:
                config.PEER_LABELS_FILE.write_text(
                    json.dumps(self._data, ensure_ascii=False, indent=2), encoding="utf-8"
                )
            except Exception:
                pass

    # ------------------------------ 读写 ------------------------------ #
    def get(self, address: str) -> dict:
        with self._lock:
            item = self._data["peers"].get(str(address).lower(), {})
            return {
                "label": item.get("label", ""),
                "color": item.get("color", DEFAULT_COLOR),
                "group": item.get("group", ""),
                "note": item.get("note", ""),
            }

    def set(self, address: str, label: str = "", color: str = DEFAULT_COLOR,
            group: str = "", note: str = "") -> None:
        with self._lock:
            key = str(address).lower()
            if not key:
                return
            if not any([label.strip(), group.strip(), note.strip()]) and color == DEFAULT_COLOR:
                self._data["peers"].pop(key, None)
            else:
                self._data["peers"][key] = {
                    "label": label.strip(),
                    "color": color,
                    "group": group.strip(),
                    "note": note.strip(),
                    "updated": int(time.time()),
                }
            self.save()

    def remove(self, address: str) -> None:
        with self._lock:
            self._data["peers"].pop(str(address).lower(), None)
            self.save()

    def all(self) -> dict:
        with self._lock:
            return dict(self._data["peers"])

    def groups(self) -> list[str]:
        with self._lock:
            groups = {v.get("group", "").strip() for v in self._data["peers"].values()}
            return sorted(g for g in groups if g)

    def display_name(self, peer: dict) -> str:
        address = str(peer.get("address", "")).lower()
        custom = self.get(address)["label"]
        return custom or address

    def color_of(self, peer: dict) -> str:
        return self.get(str(peer.get("address", "")).lower())["color"]
