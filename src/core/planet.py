"""planet（根节点）管理：解析、备份、替换、恢复。

planet 文件是 ZeroTier 的 World 序列化数据：
  [0]        类型（1 = PLANET，2 = MOON）
  [1:9]      世界 ID（大端 uint64，有效值为低 40 位）
  [9:17]     时间戳（大端 uint64，毫秒）
替换 planet 后必须重启 ZeroTier 服务才会生效。
"""
from __future__ import annotations

import datetime as _dt
import hashlib
import os
import shutil
import time
from pathlib import Path

from . import config, syswin

PLANET_TYPE = {1: "PLANET（根节点）", 2: "MOON（自定义卫星节点）"}

# 官方地球世界 ID（ZeroTier 源码 ZT_WORLD_ID_EARTH）
OFFICIAL_WORLD_ID = 149604618
# 官方四个根服务器地址（用于兜底判定：文件内出现任一即视为官方 planet）
OFFICIAL_ROOT_ADDRESSES = ("62f865ae71", "778cde7190", "992fcf1db7", "cae7faf58a")


class PlanetError(Exception):
    pass


def planet_path() -> Path:
    return config.ZT_HOME / "planet"


def parse_planet(data: bytes) -> dict:
    if len(data) < 32:
        raise PlanetError(f"文件过小（{len(data)} 字节），不是有效的 planet 文件")
    wtype = data[0]
    if wtype not in (1, 2):
        raise PlanetError(f"类型字节非法（0x{wtype:02x}），不是有效的 planet 文件")
    world_id = int.from_bytes(data[1:9], "big")
    ts = int.from_bytes(data[9:17], "big")
    if not (0 < world_id <= 0xFFFFFFFFFF):
        raise PlanetError("世界 ID 非法，文件可能已损坏")
    # 时间戳合理性校验（2010-01-01 ~ 2100-01-01）
    if not (1262304000000 <= ts <= 4102444800000):
        raise PlanetError("时间戳异常，文件可能已损坏")
    return {
        "type": wtype,
        "type_text": PLANET_TYPE.get(wtype, f"未知({wtype})"),
        "world_id": f"{world_id:010x}",
        "world_id_dec": world_id,
        "timestamp": ts,
        "timestamp_text": _dt.datetime.fromtimestamp(ts / 1000).strftime("%Y-%m-%d %H:%M:%S"),
        "size": len(data),
        "sha256": hashlib.sha256(data).hexdigest()[:16],
    }


def classify(data: bytes) -> str:
    """判定 planet 归属：official（官方地球）/ custom（自建）。"""
    info = parse_planet(data)
    if info["world_id_dec"] == OFFICIAL_WORLD_ID:
        return "official"
    for addr in OFFICIAL_ROOT_ADDRESSES:
        try:
            if bytes.fromhex(addr) in data:
                return "official"
        except Exception:
            continue
    return "custom"


def current_kind() -> str:
    """当前 planet 归属：official / custom / missing / invalid。"""
    p = planet_path()
    if not p.exists():
        return "missing"
    try:
        return classify(p.read_bytes())
    except Exception:
        return "invalid"


def kind_text(kind: str) -> str:
    return {
        "official": "官方根节点",
        "custom": "自定义根节点",
        "missing": "根节点缺失",
        "invalid": "根节点异常",
    }.get(kind, "未知")


def current_info() -> dict | None:
    p = planet_path()
    if not p.exists():
        return None
    try:
        info = parse_planet(p.read_bytes())
    except Exception as exc:
        return {"error": str(exc), "size": p.stat().st_size}
    st = p.stat()
    info["mtime"] = _dt.datetime.fromtimestamp(st.st_mtime).strftime("%Y-%m-%d %H:%M:%S")
    info["path"] = str(p)
    return info


def _backup_dir() -> Path:
    config.BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    return config.BACKUP_DIR


def backup_current(tag: str = "manual") -> Path:
    p = planet_path()
    if not p.exists():
        raise PlanetError("当前不存在 planet 文件，无法备份")
    stamp = time.strftime("%Y%m%d-%H%M%S")
    dest = _backup_dir() / f"planet-{tag}-{stamp}.bin"
    shutil.copy2(p, dest)
    _prune()
    return dest


def ensure_initial_backup() -> Path | None:
    """首次运行时保存一份原始 planet，便于随时"恢复出厂根节点"。"""
    marker = _backup_dir() / "planet-initial.bin"
    if marker.exists():
        return None
    p = planet_path()
    if not p.exists():
        return None
    try:
        shutil.copy2(p, marker)
        return marker
    except Exception:
        return None


def list_backups() -> list[dict]:
    out: list[dict] = []
    d = _backup_dir()
    for f in sorted(d.glob("planet-*.bin"), reverse=True):
        try:
            st = f.stat()
            try:
                info = parse_planet(f.read_bytes())
                world = info["world_id"]
                ts_text = info["timestamp_text"]
            except Exception:
                world, ts_text = "-", "-"
            out.append({
                "path": f,
                "name": f.name,
                "size": st.st_size,
                "mtime": _dt.datetime.fromtimestamp(st.st_mtime).strftime("%Y-%m-%d %H:%M:%S"),
                "world_id": world,
                "timestamp_text": ts_text,
            })
        except Exception:
            continue
    return out


def _prune(keep: int = 20) -> None:
    files = sorted(_backup_dir().glob("planet-*.bin"), key=lambda f: f.stat().st_mtime, reverse=True)
    for f in files[keep:]:
        if f.name == "planet-initial.bin":
            continue
        try:
            f.unlink()
        except Exception:
            pass


def _write_planet(data: bytes) -> None:
    p = planet_path()
    tmp = p.with_suffix(".new")
    tmp.write_bytes(data)
    os.replace(tmp, p)


def apply_planet(data: bytes, restart: bool = True) -> str:
    """校验 → 备份 → 替换 → 重启服务。返回说明文字。"""
    if not syswin.is_admin():
        raise PlanetError("替换根节点需要管理员权限")
    info = parse_planet(data)  # 校验失败直接抛出
    ensure_initial_backup()
    backup_current(tag="before-replace")

    was_running = syswin.service_state() == syswin.SERVICE_RUNNING
    if restart:
        ok, msg = syswin.service_stop()
        if not ok:
            raise PlanetError(f"停止 ZeroTier 服务失败：{msg}")
    try:
        _write_planet(data)
    except Exception as exc:
        if restart and was_running:
            syswin.service_start()
        raise PlanetError(f"写入 planet 文件失败：{exc}")
    if restart:
        ok, msg = syswin.service_start()
        if not ok:
            raise PlanetError(f"planet 已替换，但服务启动失败：{msg}")
    return (
        f"已替换根节点：世界 ID {info['world_id']}（{info['timestamp_text']}），"
        + ("服务已重启，配置已生效。" if restart else "重启服务后生效。")
    )


def restore_backup(path: str | Path, restart: bool = True) -> str:
    p = Path(path)
    if not p.exists():
        raise PlanetError("备份文件不存在")
    return apply_planet(p.read_bytes(), restart=restart)


def moons() -> list[dict]:
    """兼容旧接口：MOON 管理已迁移到 core.moon（moons.d 目录）。"""
    from . import moon as _moon

    return _moon.list_local()
