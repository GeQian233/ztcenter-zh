"""ZeroTier One 本地服务 API 客户端（127.0.0.1:9993）。

官方服务在本地暴露 JSON API，鉴权头为 X-ZT1-Auth，值取自
C:\\ProgramData\\ZeroTier\\One\\authtoken.secret（仅管理员可读）。
"""
from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from pathlib import Path

from . import config

NWID_RE = re.compile(r"^[0-9a-fA-F]{16}$")


class ZTError(Exception):
    def __init__(self, message: str, code: str = "ERR"):
        super().__init__(message)
        self.code = code


class ZTApi:
    """与官方 ZeroTier 服务通信。"""

    def __init__(self) -> None:
        self.home: Path = config.ZT_HOME
        self._token_cache: tuple[float, str] | None = None

    # ---------------------------- 基础信息 ---------------------------- #
    @property
    def token_path(self) -> Path:
        return self.home / "authtoken.secret"

    def token(self) -> str:
        if not (self.home / "zerotier-one_x64.exe").exists():
            raise ZTError("未检测到 ZeroTier 内核，请先在「设置 → ZeroTier 内核」中安装", "NO_KERNEL")
        path = self.token_path
        if not path.exists():
            raise ZTError(f"未找到鉴权文件：{path}", "NO_TOKEN_FILE")
        try:
            mtime = path.stat().st_mtime
            if self._token_cache and self._token_cache[0] == mtime:
                return self._token_cache[1]
            value = path.read_text(encoding="utf-8", errors="ignore").strip()
            if not value:
                raise ZTError("鉴权文件内容为空", "NO_TOKEN")
            self._token_cache = (mtime, value)
            return value
        except PermissionError:
            raise ZTError(
                "读取 ZeroTier 鉴权文件被拒绝，请以管理员身份运行本程序", "NO_PERMISSION"
            )
        except OSError as exc:
            raise ZTError(f"读取鉴权文件失败：{exc}", "NO_TOKEN")

    def port(self) -> int:
        pf = self.home / "zerotier-one.port"
        try:
            if pf.exists():
                v = int(pf.read_text(encoding="utf-8", errors="ignore").strip() or "9993")
                if 1 <= v <= 65535:
                    return v
        except Exception:
            pass
        return 9993

    # ---------------------------- HTTP ---------------------------- #
    def _request(self, method: str, path: str, body: dict | None = None, timeout: float = 5.0):
        url = f"http://127.0.0.1:{self.port()}{path}"
        data = None
        headers = {"X-ZT1-Auth": self.token(), "Accept": "application/json"}
        if body is not None:
            data = json.dumps(body).encode("utf-8")
            headers["Content-Type"] = "application/json"
        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                raw = resp.read().decode("utf-8", errors="ignore")
                return json.loads(raw) if raw.strip() else {}
        except urllib.error.HTTPError as exc:
            if exc.code == 401:
                raise ZTError("鉴权失败：本地服务拒绝了请求（令牌不匹配）", "AUTH")
            detail = ""
            try:
                detail = exc.read().decode("utf-8", errors="ignore")[:200]
            except Exception:
                pass
            raise ZTError(f"接口返回 {exc.code}：{detail}", "HTTP")
        except urllib.error.URLError as exc:
            raise ZTError(f"无法连接 ZeroTier 本地服务（{exc.reason}），请确认服务已启动", "OFFLINE")
        except TimeoutError:
            raise ZTError("连接 ZeroTier 本地服务超时", "TIMEOUT")

    # ---------------------------- 业务接口 ---------------------------- #
    def status(self) -> dict:
        return self._request("GET", "/status")

    def networks(self) -> list[dict]:
        data = self._request("GET", "/network")
        return data if isinstance(data, list) else []

    def network(self, nwid: str) -> dict:
        return self._request("GET", f"/network/{nwid}")

    def join(self, nwid: str) -> dict:
        nwid = nwid.strip().lower()
        if not NWID_RE.match(nwid):
            raise ZTError("网络 ID 必须是 16 位十六进制字符", "BAD_NWID")
        return self._request("POST", f"/network/{nwid}", {})

    def leave(self, nwid: str) -> dict:
        return self._request("DELETE", f"/network/{nwid}")

    def update(self, nwid: str, payload: dict) -> dict:
        return self._request("POST", f"/network/{nwid}", payload)

    def peers(self) -> list[dict]:
        data = self._request("GET", "/peer")
        return data if isinstance(data, list) else []

    # ---------------------------- 便捷方法 ---------------------------- #
    def summary(self) -> dict:
        """汇总概览所需信息，单次刷新使用。"""
        st = self.status()
        nets = self.networks()
        try:
            peers = self.peers()
        except ZTError:
            peers = []
        self_addr = str(st.get("address") or "").lower()
        online_peers = [
            p for p in peers
            if isinstance(p.get("latency"), (int, float)) and p["latency"] >= 0
            and str(p.get("address", "")).lower() != self_addr   # 不含本机自己
        ]
        roots = [p for p in peers if p.get("role", "").upper() in ("PLANET", "MOON")]
        return {
            "status": st,
            "networks": nets,
            "peers": peers,
            "online_peer_count": len(online_peers),
            "root_count": len(roots),
        }


# --------------------------------------------------------------------------- #
# 演示数据（--demo，用于无管理员权限时预览界面）
# --------------------------------------------------------------------------- #
class DemoZTApi(ZTApi):
    def __init__(self) -> None:  # noqa: D107
        super().__init__()
        self._nets = [
            {
                "id": "8767f3abba18a28c",
                "nwid": "8767f3abba18a28c",
                "name": "office-lan",
                "status": "OK",
                "type": "PRIVATE",
                "mac": "62:11:22:33:44:55",
                "mtu": 2800,
                "dhcp": True,
                "bridge": False,
                "broadcastEnabled": True,
                "portDeviceName": "zta2b3c4d5e6",
                "assignedAddresses": ["10.60.222.248/24", "fd00:dead:beef::1/64"],
                "routes": [{"target": "10.60.222.0/24", "via": None, "flags": 0, "metric": 0}],
                "allowManaged": True,
                "allowGlobal": False,
                "allowDefault": False,
                "allowDNS": False,
                "dns": {"servers": [], "domain": "", "search": []},
                "netconfRevision": 12,
            },
            {
                "id": "1d71939404111111",
                "nwid": "1d71939404111111",
                "name": "home-nas",
                "status": "REQUESTING_CONFIGURATION",
                "type": "PRIVATE",
                "mac": "62:aa:bb:cc:dd:ee",
                "mtu": 2800,
                "dhcp": True,
                "bridge": False,
                "broadcastEnabled": True,
                "portDeviceName": "zta99887766",
                "assignedAddresses": [],
                "routes": [],
                "allowManaged": True,
                "allowGlobal": False,
                "allowDefault": False,
                "allowDNS": False,
                "dns": {"servers": [], "domain": "", "search": []},
                "netconfRevision": 0,
            },
        ]

    def token(self) -> str:
        return "demo"

    def status(self) -> dict:
        return {
            "address": "a09acf0233",
            "online": True,
            "version": "1.16.2",
            "publicIdentity": "a09acf0233:0:...",
            "planetWorldId": 0x00C0FFEE00,   # 演示用中性值（00c0ffee00），避免暴露真实自建 planet 世界 ID
            "planetWorldTimestamp": 1794197643615,
            "tcpFallbackActive": False,
            "config": {"settings": {"primaryPort": 9993, "allowTcpFallbackRelay": True}},
        }

    def networks(self) -> list[dict]:
        return [dict(n) for n in self._nets]

    def peers(self) -> list[dict]:
        import time as _t

        now = int(_t.time() * 1000)

        def path(addr: str, last: int, preferred: bool = True) -> dict:
            return {"address": addr, "lastSend": last, "lastReceive": last,
                    "active": True, "expired": False, "preferred": preferred, "trustedPathId": 0}

        return [
            # 本机自己（role LEAF，latency 0）
            {"address": "a09acf0233", "role": "LEAF", "latency": 0, "version": "1.16.2",
             "versionMajor": 1, "tunneled": False, "paths": [], "lastSend": now, "lastReceive": now},
            # 官方根节点
            {"address": "62f865ae71", "role": "PLANET", "latency": 42, "version": "1.16.2",
             "versionMajor": 1, "tunneled": False,
             "paths": [path("192.0.2.66/9993", now), path("198.51.100.44/9993", now, False)],
             "lastSend": now, "lastReceive": now},
            {"address": "778cde7190", "role": "PLANET", "latency": 88, "version": "1.16.2",
             "versionMajor": 1, "tunneled": False,
             "paths": [path("198.51.100.44/9993", now)], "lastSend": now, "lastReceive": now},
            # 直连的成员节点
            {"address": "9f77aa6b31", "role": "LEAF", "latency": 15, "version": "1.16.2",
             "versionMajor": 1, "tunneled": False,
             "paths": [path("203.0.113.7/53211", now)], "lastSend": now, "lastReceive": now},
            # 旧版本成员节点：不上报延迟（latency = 0 表示未测量）
            {"address": "80cd6f11d3", "role": "LEAF", "latency": 0, "version": "1.12.2",
             "versionMajor": 1, "tunneled": False,
             "paths": [path("192.0.2.97/9993", now)], "lastSend": now, "lastReceive": now},
            # 经中继的成员节点
            {"address": "c857b404e4", "role": "LEAF", "latency": 133, "version": "1.16.2",
             "versionMajor": 1, "tunneled": True,
             "paths": [path("62f865ae71/9993", now)], "lastSend": now,
             "lastReceive": now - 42000},
        ]

    def update(self, nwid: str, payload: dict) -> dict:
        for n in self._nets:
            if n["id"] == nwid:
                n.update(payload)
                return dict(n)
        raise ZTError("网络不存在", "NOT_FOUND")

    def join(self, nwid: str) -> dict:
        nwid = nwid.strip().lower()
        if not NWID_RE.match(nwid):
            raise ZTError("网络 ID 必须是 16 位十六进制字符", "BAD_NWID")
        new = {
            "id": nwid, "nwid": nwid, "name": "", "status": "REQUESTING_CONFIGURATION",
            "type": "PRIVATE", "mac": "62:00:00:00:00:01", "mtu": 2800, "dhcp": True,
            "bridge": False, "broadcastEnabled": True, "portDeviceName": "zta00000000",
            "assignedAddresses": [], "routes": [], "allowManaged": True,
            "allowGlobal": False, "allowDefault": False, "allowDNS": False,
            "dns": {"servers": [], "domain": "", "search": []}, "netconfRevision": 0,
        }
        self._nets.append(new)
        return new

    def leave(self, nwid: str) -> dict:
        self._nets = [n for n in self._nets if n["id"] != nwid]
        return {}

# --------------------------------------------------------------------------- #
# 字段解析辅助（兼容官方 API 的真实结构与历史结构）
#   官方 /network 的 assignedAddresses 是字符串数组，例如 ["10.0.0.2/24"]
#   早期演示数据用的是对象数组 [{"address": "10.0.0.2/24"}]，两种都要能读
# --------------------------------------------------------------------------- #
def net_id(net: dict) -> str:
    return str(net.get("id") or net.get("nwid") or "").strip().lower()


def net_addresses(net: dict) -> list[str]:
    out: list[str] = []
    for item in net.get("assignedAddresses") or []:
        if isinstance(item, str):
            addr = item
        elif isinstance(item, dict):
            addr = item.get("address") or ""
        else:
            addr = ""
        addr = str(addr).strip()
        if addr:
            out.append(addr)
    return out


def net_ipv4(net: dict) -> list[str]:
    return [a for a in net_addresses(net) if ":" not in a]


def net_ipv6(net: dict) -> list[str]:
    return [a for a in net_addresses(net) if ":" in a]


def net_dns_servers(net: dict) -> list[str]:
    dns = net.get("dns")
    if isinstance(dns, dict):
        servers = dns.get("servers") or []
    elif isinstance(dns, list):
        servers = dns
    else:
        servers = []
    return [str(s).strip() for s in servers if str(s).strip()]


def net_routes(net: dict) -> list[tuple[str, str | None]]:
    out: list[tuple[str, str | None]] = []
    for r in net.get("routes") or []:
        if isinstance(r, dict):
            target = str(r.get("target") or "").strip()
            via = r.get("via")
            if target:
                out.append((target, str(via) if via else None))
        elif isinstance(r, str) and r.strip():
            out.append((r.strip(), None))
    return out


def net_flags(net: dict) -> list[str]:
    """返回已开启的网络选项（用于列表行内简述）。"""
    labels = (
        ("allowManaged", "托管"),
        ("allowGlobal", "全局"),
        ("allowDefault", "默认路由"),
        ("allowDNS", "DNS"),
    )
    return [name for key, name in labels if net.get(key)]


def net_info_text(net: dict) -> str:
    """生成便于粘贴排障的纯文本。"""
    v4 = ", ".join(net_ipv4(net)) or "无"
    v6 = ", ".join(net_ipv6(net)) or "无"
    lines = [
        f"网络 ID：{net_id(net)}",
        f"网络名称：{net.get('name') or '（无）'}",
        f"状态：{net.get('status') or '—'}",
        f"类型：{net.get('type') or '—'}",
        f"IPv4：{v4}",
        f"IPv6：{v6}",
        f"虚拟网卡：{net.get('portDeviceName') or '—'}",
        f"MAC：{net.get('mac') or '—'}",
        f"MTU：{net.get('mtu') or '—'}",
        f"DHCP：{'开' if net.get('dhcp') else '关'}",
        f"选项：{', '.join(net_flags(net)) or '无'}",
    ]
    routes = net_routes(net)
    if routes:
        lines.append("路由：" + "; ".join(t + (f" via {v}" if v else "") for t, v in routes))
    dns = net_dns_servers(net)
    if dns:
        lines.append("DNS：" + ", ".join(dns))
    return "\n".join(lines)
