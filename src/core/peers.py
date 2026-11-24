"""对端（peer）解析：角色、路径、P2P/中继、延迟，以及虚拟 IP 反查。

说明：ZeroTier 的 `/peer` 不提供对端名称，也不提供对端在其网络中的虚拟 IP。
本模块用两个可验证的手段补充信息：
  - 名称：用角色（根节点 / 卫星节点 / 成员节点）标识；
  - 虚拟 IP：ZeroTier 虚拟网卡 MAC 由节点地址派生（末 5 字节 = 地址），
    因此可用本机 ARP/邻居表把 MAC 反查成 IP（仅在最近有过通信时存在）。
"""
from __future__ import annotations

import re
import time

from . import syswin

ROLE_NAMES = {
    "PLANET": "根节点",
    "MOON": "卫星节点",
    "LEAF": "成员节点",
}

_ARP_CACHE: dict = {"ts": 0.0, "table": {}}
_ARP_TTL = 10.0
_ARP_LINE = re.compile(
    r"^\s*(\d{1,3}(?:\.\d{1,3}){3})\s+([0-9a-fA-F]{2}(?:[:-][0-9a-fA-F]{2}){5})\s+",
    re.MULTILINE,
)


def role_name(peer: dict) -> str:
    return ROLE_NAMES.get(str(peer.get("role", "")).upper(), str(peer.get("role") or "未知"))


def address_bytes(address: str) -> bytes:
    try:
        return int(str(address), 16).to_bytes(5, "big")
    except Exception:
        return b""


def address_mac(address: str) -> str:
    raw = address_bytes(address)
    if not raw:
        return ""
    return "62:" + ":".join(f"{b:02x}" for b in raw)


def paths(peer: dict) -> list[dict]:
    out = []
    for p in peer.get("paths") or []:
        if isinstance(p, dict) and p.get("address"):
            out.append(p)
        elif isinstance(p, str):
            out.append({"address": p, "active": True})
    return out


def active_path(peer: dict) -> dict | None:
    active = [p for p in paths(peer) if p.get("active")]
    if not active:
        return None
    preferred = [p for p in active if p.get("preferred")]
    return (preferred or active)[0]


def endpoint(peer: dict) -> str:
    p = active_path(peer)
    return str(p.get("address", "")) if p else ""


def is_relayed(peer: dict) -> bool:
    if peer.get("tunneled"):
        return True
    return active_path(peer) is None


def link_text(peer: dict) -> str:
    if peer.get("tunneled"):
        return "中继"
    if active_path(peer) is None:
        return "未直连"
    return "P2P 直连"


def latency_text(peer: dict) -> str:
    """延迟文本。ZeroTier 用 0 表示「尚未测量」，缺失同理，不当作 0ms。"""
    lat = peer.get("latency")
    if isinstance(lat, bool):
        return "未测量"
    if isinstance(lat, (int, float)) and lat > 0:
        return f"{int(round(lat))} ms"
    return "未测量"


def last_seen_text(peer: dict) -> str:
    for key in ("lastReceive", "lastSend"):
        ts = peer.get(key)
        if not isinstance(ts, (int, float)) or ts <= 0:
            continue
        sec = ts / 1000 if ts > 1e12 else ts
        delta = max(0, int(time.time() - sec))
        if delta < 60:
            return f"{delta} 秒前"
        if delta < 3600:
            return f"{delta // 60} 分钟前"
        return f"{delta // 3600} 小时前"
    return "—"


# --------------------------------------------------------------------------- #
# 虚拟 IP 反查（ARP / 邻居表）
# --------------------------------------------------------------------------- #
def neighbor_table(refresh: bool = False) -> dict[str, str]:
    """返回 {mac(小写冒号形式): ip}，10 秒缓存。失败返回空表。"""
    now = time.time()
    if not refresh and _ARP_CACHE["table"] and now - _ARP_CACHE["ts"] < _ARP_TTL:
        return _ARP_CACHE["table"]
    table: dict[str, str] = {}
    try:
        _code, out = syswin.run_hidden(["arp", "-a"], timeout=6)
        for ip, mac in _ARP_LINE.findall(out or ""):
            table[mac.lower().replace("-", ":")] = ip
    except Exception:
        table = {}
    _ARP_CACHE.update({"ts": now, "table": table})
    return table


def virtual_ip(peer: dict, table: dict[str, str] | None = None) -> str:
    raw = address_bytes(peer.get("address", ""))
    if not raw:
        return ""
    table = neighbor_table() if table is None else table
    suffix = ":".join(f"{b:02x}" for b in raw)
    for mac, ip in table.items():
        # 兼容首字节差异，只比对末 5 字节（= 节点地址）
        if mac.endswith(suffix):
            return ip
    return ""


# --------------------------------------------------------------------------- #
# 汇总
# --------------------------------------------------------------------------- #
def _not_self(peer: dict, self_addr: str) -> bool:
    return not self_addr or str(peer.get("address", "")).lower() != self_addr


def connection_mode(peers: list[dict] | None, self_addr: str = "") -> str:
    """本机与成员节点的联机方式：P2P / 中继 / P2P+中继 / 无对端。"""
    leafs = [p for p in peers or []
             if str(p.get("role", "")).upper() == "LEAF" and _not_self(p, self_addr)]
    if not leafs:
        return "无对端"
    direct = sum(1 for p in leafs if not is_relayed(p))
    relayed = len(leafs) - direct
    if direct and relayed:
        return "P2P+中继"
    return "P2P" if direct else "中继"


def mode_short(mode: str) -> str:
    return {"P2P+中继": "P2P/中继", "无对端": ""}.get(mode, mode)


def summarize(peers: list[dict] | None, self_addr: str = "") -> dict:
    peers = [p for p in (peers or []) if _not_self(p, self_addr)]
    leafs = [p for p in peers if str(p.get("role", "")).upper() == "LEAF"]
    roots = [p for p in peers if str(p.get("role", "")).upper() in ("PLANET", "MOON")]
    direct = [p for p in leafs if not is_relayed(p)]
    return {
        "total": len(peers),
        "leaf": len(leafs),
        "roots": len(roots),
        "direct": len(direct),
        "relayed": len(leafs) - len(direct),
        "mode": connection_mode(peers, self_addr),
    }


def peer_info_text(peer: dict, vip: str = "") -> str:
    lines = [
        f"地址：{peer.get('address', '')}",
        f"类型：{role_name(peer)}",
        f"连接：{link_text(peer)}",
        f"延迟：{latency_text(peer)}",
        f"路径：{endpoint(peer) or '—'}",
        f"版本：{peer.get('version') or '—'}",
    ]
    if vip:
        lines.append(f"虚拟 IP：{vip}")
    return "\n".join(lines)
