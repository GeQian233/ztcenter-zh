"""MOON（自定义卫星根节点）管理。

- 本地 MOON 文件位于 `C:\\ProgramData\\ZeroTier\\One\\moons.d\\<moonid>.moon`
- 文件格式与 planet 相同（World 序列化）：类型 2 = MOON
- 生效方式：`zerotier-one_x64.exe -q orbit <id> <id>`（无 CLI 时重启服务亦可）
- 移除：`-q deorbit <id>` 后删除文件
"""
from __future__ import annotations

import base64
import binascii
import datetime as _dt
import shutil
import time
from pathlib import Path

from . import config, syswin

MOON_TYPE = 2


class MoonError(Exception):
    pass


def moon_dir() -> Path:
    return config.ZT_HOME / "moons.d"


def backup_dir() -> Path:
    p = config.DATA_DIR / "moon-backup"
    p.mkdir(parents=True, exist_ok=True)
    return p


def _cli_exe() -> Path:
    return config.ZT_HOME / "zerotier-one_x64.exe"


# --------------------------------------------------------------------------- #
# 解析与列表
# --------------------------------------------------------------------------- #
def parse_moon(data: bytes) -> dict:
    if len(data) < 32:
        raise MoonError(f"文件过小（{len(data)} 字节），不是有效的 moon 文件")
    wtype = data[0]
    if wtype != MOON_TYPE:
        raise MoonError(
            "类型字节为 %d，不是 MOON（应为 2）。planet 根节点请到「根节点」页替换。" % wtype
        )
    moon_id = int.from_bytes(data[1:9], "big")
    ts = int.from_bytes(data[9:17], "big")
    if not (0 < moon_id <= 0xFFFFFFFFFF):
        raise MoonError("MOON 世界 ID 非法，文件可能已损坏")
    if not (1262304000000 <= ts <= 4102444800000):
        raise MoonError("时间戳异常，文件可能已损坏")
    return {
        "id": f"{moon_id:010x}",
        "id_dec": moon_id,
        "timestamp": ts,
        "timestamp_text": _dt.datetime.fromtimestamp(ts / 1000).strftime("%Y-%m-%d %H:%M:%S"),
        "size": len(data),
        "sha256_prefix": __import__("hashlib").sha256(data).hexdigest()[:16],
    }


def list_local() -> list[dict]:
    """列出 moons.d 中的 MOON 文件。"""
    d = moon_dir()
    out: list[dict] = []
    if not d.exists():
        return out
    for f in sorted(d.glob("*.moon")):
        try:
            data = f.read_bytes()
            info = parse_moon(data)
        except Exception as exc:
            out.append({
                "id": f.stem.lower(), "timestamp_text": "-", "size": f.stat().st_size,
                "path": f, "name": f.name, "error": str(exc), "mtime": "",
            })
            continue
        st = f.stat()
        info.update({
            "path": f,
            "name": f.name,
            "mtime": _dt.datetime.fromtimestamp(st.st_mtime).strftime("%Y-%m-%d %H:%M"),
        })
        out.append(info)
    return out


def runtime_ids(peers: list[dict] | None) -> set[str]:
    """从 /peer 结果中提取当前已生效的 MOON 节点 ID。"""
    ids: set[str] = set()
    for p in peers or []:
        if str(p.get("role", "")).upper() == "MOON":
            addr = p.get("address")
            if addr:
                ids.add(str(addr).lower())
    return ids


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def _run_cli(args: list[str]) -> tuple[bool, str]:
    exe = _cli_exe()
    if not exe.exists():
        return False, f"未找到 ZeroTier 可执行文件：{exe}"
    code, out = syswin.run_hidden([str(exe), "-q", *args], timeout=15)
    ok = code == 0 and "200" in out
    return ok, (out.strip() or f"退出码 {code}")


def listmoons() -> tuple[bool, str]:
    return _run_cli(["listmoons"])


# --------------------------------------------------------------------------- #
# 增删
# --------------------------------------------------------------------------- #
def _write_moon(mid: str, data: bytes) -> Path:
    d = moon_dir()
    d.mkdir(parents=True, exist_ok=True)
    dest = d / f"{mid}.moon"
    if dest.exists():
        stamp = time.strftime("%Y%m%d-%H%M%S")
        shutil.copy2(dest, backup_dir() / f"moon-{mid}-{stamp}.moon")
    dest.write_bytes(data)
    return dest


def add_bytes(data: bytes, source: str = "") -> str:
    """校验 → 写入 moons.d → orbit 使其立即生效。"""
    if not syswin.is_admin():
        raise MoonError("添加 MOON 需要管理员权限")
    info = parse_moon(data)
    mid = info["id"]
    _write_moon(mid, data)
    ok, out = _run_cli(["orbit", mid, mid])
    if ok:
        return f"已添加 MOON {mid}（{info['timestamp_text']}），已生效"
    # CLI 不可用时退回重启服务
    rok, rmsg = syswin.service_restart()
    if rok:
        return f"已添加 MOON {mid}，已通过重启服务生效"
    raise MoonError(f"MOON 文件已写入，但无法生效：{out}；重启服务失败：{rmsg}")


def add_file(path: str | Path) -> str:
    p = Path(path)
    if not p.exists():
        raise MoonError("文件不存在")
    if p.suffix.lower() != ".moon":
        # 仍然尝试按内容校验，仅提示
        pass
    return add_bytes(p.read_bytes(), source=str(p))


def decode_payload(text: str) -> bytes:
    """支持十六进制、Base64、或带空白/换行的文本。"""
    s = "".join(text.split())
    if not s:
        raise MoonError("内容为空")
    # 十六进制
    if all(c in "0123456789abcdefABCDEF" for c in s) and len(s) % 2 == 0 and len(s) >= 64:
        try:
            return binascii.unhexlify(s)
        except Exception:
            pass
    # Base64
    try:
        pad = "=" * (-len(s) % 4)
        return base64.b64decode(s + pad, validate=False)
    except Exception as exc:
        raise MoonError(f"无法识别的内容格式：{exc}")


def remove(mid: str) -> str:
    """deorbit → 备份并删除文件。"""
    if not syswin.is_admin():
        raise MoonError("移除 MOON 需要管理员权限")
    mid = mid.strip().lower()
    f = moon_dir() / f"{mid}.moon"
    ok, out = _run_cli(["deorbit", mid])
    note = "" if ok else f"（deorbit 返回：{out}）"
    if f.exists():
        try:
            stamp = time.strftime("%Y%m%d-%H%M%S")
            shutil.copy2(f, backup_dir() / f"moon-{mid}-removed-{stamp}.moon")
        except Exception:
            pass
        try:
            f.unlink()
        except Exception as exc:
            raise MoonError(f"删除文件失败：{exc}")
    return f"已移除 MOON {mid}{note}"


def clear_all_file_only() -> int:
    """仅清理文件（用于排错），返回删除数量。"""
    n = 0
    for f in moon_dir().glob("*.moon"):
        try:
            _run_cli(["deorbit", f.stem.lower()])
            f.unlink()
            n += 1
        except Exception:
            pass
    return n
