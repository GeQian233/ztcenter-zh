"""延迟探测：内核未上报 latency 时，用本机 ping 粗略测量。

ZeroTier 的 /peer 只有在完成 VL1 延迟测量后才给出 latency，旧版本节点
（如 v1.12.x）甚至不上报。这里对「有可用公网路径 / 虚拟 IP」且内核未给出
延迟的对端做一次 ICMP 探测，作为参考值展示（界面会明确标注「约」）。
"""
from __future__ import annotations

import re
import threading
import time

from . import syswin

_CACHE: dict[str, tuple[float, int | None]] = {}
_TTL = 30.0
_LOCK = threading.RLock()

_AVG = re.compile(r"(?:平均|Average)\s*=\s*(\d+)\s*ms", re.IGNORECASE)
_SAMPLES = re.compile(r"(?:时间|time)\s*[=<]\s*(\d+)\s*ms", re.IGNORECASE)
_HOST_PORT = re.compile(r"^\[?([0-9a-fA-F:.]+?)\]?(?:[/:]\d+)?$")


def parse_ping_output(text: str) -> int | None:
    """从 ping 输出解析平均往返时间（毫秒）。无法解析返回 None。"""
    if not text:
        return None
    m = _AVG.search(text)
    if m:
        return int(m.group(1))
    samples = [int(x) for x in _SAMPLES.findall(text)]
    if samples:
        return int(round(sum(samples) / len(samples)))
    # 全部超时
    if re.search(r"(100%\s*(?:丢失|loss))|(请求超时|Request timed out|无法访问目标主机)", text, re.IGNORECASE):
        return None
    return None


def endpoint_host(endpoint: str) -> str:
    """从 '39.78.9.97/9993' 或 '1.2.3.4:9993' 中取出主机部分。"""
    if not endpoint:
        return ""
    value = endpoint.strip().split(" ")[0]
    m = _HOST_PORT.match(value)
    host = m.group(1) if m else ""
    # 只接受 IP 形态（路径里也可能是对端地址，如 "62f865ae71/9993"）
    return host if ("." in host or ":" in host) else ""


def ping_latency(host: str, timeout_ms: int = 900) -> int | None:
    """对主机做 ICMP 探测，返回平均 RTT（毫秒）；失败返回 None。30 秒缓存。"""
    host = (host or "").strip()
    if not host:
        return None
    now = time.time()
    with _LOCK:
        cached = _CACHE.get(host)
        if cached and now - cached[0] < _TTL:
            return cached[1]

    try:
        _code, out = syswin.run_hidden(
            ["ping", "-n", "2", "-w", str(int(timeout_ms)), host], timeout=8
        )
        value = parse_ping_output(out or "")
    except Exception:
        value = None

    with _LOCK:
        _CACHE[host] = (now, value)
    return value


def latency_hint(value: int | None) -> str:
    if value is None:
        return "未测量"
    if value <= 0:
        return "约 <1 ms"
    return f"约 {value} ms"
