"""ZeroTier 内核（官方服务端二进制）版本检测与安装包辅助。"""
from __future__ import annotations

import subprocess
import urllib.request
import winreg
from pathlib import Path

from . import config

# 本客户端验证过的官方版本
TARGET_VERSION = "1.16.2"
DOWNLOAD_URL = "https://download.zerotier.com/dist/ZeroTier%20One.msi"
UNINSTALL_KEYS = [
    (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall", winreg.KEY_WOW64_64KEY),
    (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall", winreg.KEY_WOW64_32KEY),
]


def kernel_installed() -> bool:
    """官方内核是否已安装（以服务端可执行文件为准）。"""
    return (config.ZT_HOME / "zerotier-one_x64.exe").exists()


def _is_official_entry(display_name: str, uninstall_string: str = "") -> bool:
    """判定卸载项是否为官方 ZeroTier One 内核。

    必须严格区分本控制台（DisplayName 为「ZeroTier 中文控制台」）：
    官方内核的 DisplayName 恰为 "ZeroTier One"；含「控制台 / 中文 / ZTCenter」的一律排除。
    """
    name = (display_name or "").strip().lower()
    if not name.startswith("zerotier"):
        return False
    for bad in ("控制台", "中文", "ztcenter", "console", "客户端"):
        if bad in name:
            return False
    if name == "zerotier one" or name.startswith("zerotier one "):
        return True
    # 其他命名（如 "ZeroTier One 1.16.2"）需由 MSI 卸载命令确认
    return "msiexec" in (uninstall_string or "").lower()


def installed_version() -> str:
    """从注册表卸载项读取官方内核版本（绝不返回本控制台版本），失败返回空串。"""
    for hive, path, flag in UNINSTALL_KEYS:
        try:
            with winreg.OpenKey(hive, path, 0, winreg.KEY_READ | flag) as root:
                idx = 0
                while True:
                    try:
                        sub = winreg.EnumKey(root, idx)
                    except OSError:
                        break
                    idx += 1
                    try:
                        with winreg.OpenKey(root, sub) as k:
                            try:
                                name = str(winreg.QueryValueEx(k, "DisplayName")[0])
                            except OSError:
                                continue
                            try:
                                uninst = str(winreg.QueryValueEx(k, "UninstallString")[0])
                            except OSError:
                                uninst = ""
                            if not _is_official_entry(name, uninst):
                                continue
                            try:
                                return str(winreg.QueryValueEx(k, "DisplayVersion")[0])
                            except OSError:
                                continue
                    except OSError:
                        continue
        except OSError:
            continue
    return ""


def _parse(v: str) -> tuple[int, ...]:
    parts = []
    for seg in (v or "").split("."):
        num = "".join(ch for ch in seg if ch.isdigit())
        parts.append(int(num) if num else 0)
    while len(parts) < 3:
        parts.append(0)
    return tuple(parts[:4])


def status() -> dict:
    """控制台与内核的版本信息（两者严格分开）。"""
    kernel = installed_version()
    present = kernel_installed()
    outdated = False
    if kernel:
        try:
            outdated = _parse(kernel) < _parse(TARGET_VERSION)
        except Exception:
            outdated = False
    return {
        # 控制台
        "control": config.APP_VERSION,
        "control_latest": config.APP_VERSION,   # 离线分发，无在线更新源
        # 内核
        "kernel": kernel if kernel else ("未知" if present else "未安装"),
        "kernel_installed": present,
        "target": TARGET_VERSION,
        "outdated": outdated,
        "up_to_date": bool(kernel) and not outdated,
        # 兼容旧字段
        "current": kernel if kernel else ("未知" if present else "未安装"),
    }


def installer_path() -> Path | None:
    """查找本地已存在的官方安装包（安装目录、upgrade 子目录、下载目录均会搜索）。"""
    names = [
        f"ZeroTierOne-{TARGET_VERSION}.msi",
        "ZeroTierOne.msi",
        "ZeroTier One.msi",
    ]
    dirs = [
        config.DATA_DIR / "downloads",
        config.BASE_DIR / "upgrade",
        config.BASE_DIR.parent / "upgrade",
        config.BASE_DIR,
    ]
    for d in dirs:
        for n in names:
            p = d / n
            if p.exists() and p.stat().st_size > 1_000_000:
                return p
    # 兜底：目录内任意 ZeroTier 命名的 msi
    for d in dirs:
        if not d.is_dir():
            continue
        try:
            for p in sorted(d.glob("*.msi")):
                if "zerotier" in p.name.lower() and p.stat().st_size > 1_000_000:
                    return p
        except Exception:
            continue
    return None


def is_installer_file(path: str | Path) -> bool:
    """粗略校验是否为可用的 MSI（存在、体积合理、OLE 复合文档头）。"""
    p = Path(path)
    if not p.exists() or p.stat().st_size < 1_000_000:
        return False
    try:
        with open(p, "rb") as f:
            head = f.read(8)
        return head == b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"
    except Exception:
        return False


def download_installer(progress=None) -> Path:
    """下载官方安装包到数据目录，返回文件路径。"""
    dest_dir = config.DATA_DIR / "downloads"
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / f"ZeroTierOne-{TARGET_VERSION}.msi"
    tmp = dest.with_suffix(".part")
    req = urllib.request.Request(DOWNLOAD_URL, headers={"User-Agent": "ZTCenter"})
    with urllib.request.urlopen(req, timeout=60) as resp, open(tmp, "wb") as f:
        total = int(resp.headers.get("Content-Length") or 0)
        done = 0
        while True:
            chunk = resp.read(64 * 1024)
            if not chunk:
                break
            f.write(chunk)
            done += len(chunk)
            if progress and total:
                progress(done / total)
    tmp.replace(dest)
    return dest


def run_installer(path: str | Path) -> None:
    """启动官方 MSI 安装向导（本程序已提权，安装过程无需二次确认）。"""
    subprocess.Popen(["msiexec", "/i", str(path)], close_fds=True)
