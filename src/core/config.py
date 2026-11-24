"""全局配置、路径与设置持久化。"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

APP_NAME = "ZeroTier 控制台"
APP_NAME_EN = "ZTCenter"
APP_VERSION = "1.11.0"
APP_AUTHOR = "ZTCenter"

SERVICE_NAME = "ZeroTierOneService"
IPC_PORT = int(os.environ.get("ZTCENTER_IPC_PORT", "39271"))
# 仅用于并行测试：给单实例互斥体加后缀，避免与本机正在运行的实例冲突
INSTANCE_SUFFIX = os.environ.get("ZTCENTER_INSTANCE_SUFFIX", "")
MUTEX_NAME = "Local\\ZTCenter_SingleInstance_Mutex" + INSTANCE_SUFFIX
HOTKEY_TEXT = "Ctrl + Alt + Z"


def _base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[2]


BASE_DIR = _base_dir()


def data_dir() -> Path:
    base = os.environ.get("APPDATA") or str(Path.home())
    p = Path(base) / APP_NAME_EN
    p.mkdir(parents=True, exist_ok=True)
    return p


DATA_DIR = data_dir()
SETTINGS_FILE = DATA_DIR / "settings.json"
LABELS_FILE = DATA_DIR / "labels.json"
PEER_LABELS_FILE = DATA_DIR / "peer_labels.json"
PEER_ORDER_FILE = DATA_DIR / "peer_order.json"
NET_ORDER_FILE = DATA_DIR / "net_order.json"
BACKUP_DIR = DATA_DIR / "planet-backup"
LOG_FILE = DATA_DIR / "ztcenter.log"


def zt_home() -> Path:
    """ZeroTier One 数据目录（planet / authtoken.secret 所在处）。"""
    env = os.environ.get("ZT_HOME")
    if env and Path(env).is_dir():
        return Path(env)
    candidates = [
        Path(os.environ.get("ProgramData", r"C:\ProgramData")) / "ZeroTier" / "One",
        Path(r"C:\ProgramData\ZeroTier\One"),
        Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")) / "ZeroTier" / "One",
    ]
    for c in candidates:
        if (c / "authtoken.secret").exists() or (c / "zerotier-one_x64.exe").exists():
            return c
    return candidates[0]


ZT_HOME = zt_home()
PLANET_FILE = ZT_HOME / "planet"
AUTHTOKEN_FILE = ZT_HOME / "authtoken.secret"
PORT_FILE = ZT_HOME / "zerotier-one.port"
NETWORKS_D_DIR = ZT_HOME / "networks.d"
PEERS_D_DIR = ZT_HOME / "peers.d"

DEFAULT_SETTINGS: dict = {
    "autostart": False,
    "start_minimized": False,
    "close_to_tray": True,
    "hotkey_enabled": True,
    "hide_mode": "tray",          # tray = 隐藏到托盘；none = 彻底隐藏（无托盘图标）
    "kill_official_ui": True,     # 自动结束官方 ZeroTier 托盘 UI
    "ui_scale": "auto",          # auto = 跟随系统 DPI；也可为 1.0/1.25/1.5/1.75/2.0
    "theme": "light",
    "refresh_interval": 0,        # 0 = 关闭自动刷新（默认，避免频繁重绘刺眼）
    "last_page": "overview",
    "hide_tray_hint": False,
}


def load_settings() -> dict:
    data = dict(DEFAULT_SETTINGS)
    try:
        if SETTINGS_FILE.exists():
            raw = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                data.update({k: v for k, v in raw.items() if k in DEFAULT_SETTINGS})
    except Exception:
        pass
    return data


def save_settings(settings: dict) -> None:
    try:
        SETTINGS_FILE.write_text(
            json.dumps(settings, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    except Exception:
        pass
