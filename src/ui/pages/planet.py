"""根节点（planet）管理页：查看、导入替换、备份与恢复。"""
from __future__ import annotations

import threading
from tkinter import filedialog

import customtkinter as ctk

from core import config, moon, planet, syswin
from ui import theme
from ui.dialogs import confirm
from ui.moon_dialog import MoonDialog
from ui.widgets import Card, Pill, empty_state, ghost_button, kv_row, primary_button


class PlanetPage(ctk.CTkFrame):
    def __init__(self, master, app):
        super().__init__(master, fg_color="transparent")
        self.app = app
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)
        self.scroll = ctk.CTkScrollableFrame(self, fg_color="transparent",
                                             scrollbar_button_color=theme.C()["border"])
        self.scroll.grid(row=0, column=0, sticky="nsew", padx=2, pady=2)
        self.scroll.grid_columnconfigure(0, weight=1)
        self._built = False

    # ------------------------------------------------------------------ #
    def refresh(self) -> None:
        for w in self.scroll.winfo_children():
            w.destroy()
        c = theme.C()
        wrap = ctk.CTkFrame(self.scroll, fg_color="transparent")
        wrap.grid(row=0, column=0, sticky="nsew", padx=4, pady=(2, 12))
        wrap.grid_columnconfigure(0, weight=1)

        # ---------------- 当前根节点 ---------------- #
        card = Card(wrap)
        card.grid(row=0, column=0, sticky="ew")
        head = card.title("当前根节点（planet）", "决定节点加入哪一个 ZeroTier 世界")
        info = planet.current_info()
        running = (self.app.summary or {}).get("status", {}) if self.app.summary else {}
        if info and "error" in info:
            Pill(head, "文件异常", fg=c["danger"], bg=c["danger_soft"]).pack(side="left", padx=8)
        elif info:
            Pill(head, "已就绪", fg=c["success"], bg=c["success_soft"]).pack(side="left", padx=8)

        if not info:
            empty_state(card.body, "未找到 planet 文件",
                        f"预期路径：{config.ZT_HOME / 'planet'}").pack(fill="x")
        elif "error" in info:
            ctk.CTkLabel(card.body, text=f"⚠  {info['error']}", font=theme.font(12),
                         text_color=c["danger"], anchor="w").pack(fill="x")
        else:
            rows = {
                "文件类型": info["type_text"],
                "世界 ID": info["world_id"],
                "世界时间戳": info["timestamp_text"],
                "文件大小": f"{info['size']} 字节",
                "SHA256 前缀": info["sha256"],
                "文件修改时间": info.get("mtime", "—"),
                "文件路径": str(planet.planet_path()),
            }
            for k, v in rows.items():
                _, val = kv_row(card.body, k)
                val.configure(text=str(v))
                if k in ("世界 ID", "SHA256 前缀", "文件路径"):
                    val.configure(font=ctk.CTkFont(family="Consolas", size=12))

            run_world = running.get("planetWorldId")
            if isinstance(run_world, int):
                run_hex = f"{run_world:010x}"
                same = run_hex == info["world_id"]
                tip = ctk.CTkLabel(
                    card.body,
                    text=("✓ 与运行中的服务一致，配置已生效" if same
                          else f"⚠ 文件世界 ID 为 {info['world_id']}，运行中的服务为 {run_hex}，重启服务后生效"),
                    font=theme.font(11), text_color=c["success"] if same else c["warn"], anchor="w",
                )
                tip.pack(fill="x", pady=(6, 0))

        btns = ctk.CTkFrame(card.body, fg_color="transparent")
        btns.pack(fill="x", pady=(14, 0))
        primary_button(btns, "导入 planet 并替换", self._import, width=150).pack(side="left", padx=(0, 6))
        ghost_button(btns, "备份当前", self._backup, width=88).pack(side="left", padx=3)
        ghost_button(btns, "恢复出厂根节点", self._restore_initial, width=120).pack(side="left", padx=3)
        ghost_button(btns, "重启服务", self._restart, width=88).pack(side="left", padx=3)
        ghost_button(btns, "打开配置目录", lambda: syswin.open_path(config.ZT_HOME),
                     width=110).pack(side="left", padx=3)

        # ---------------- 备份列表 ---------------- #
        bcard = Card(wrap)
        bcard.grid(row=1, column=0, sticky="ew", pady=(12, 0))
        bcard.title("planet 备份", "每次替换前自动备份，可随时回滚")
        backups = planet.list_backups()
        if not backups:
            empty_state(bcard.body, "暂无备份", "执行替换或点击「备份当前」后生成").pack(fill="x")
        else:
            for b in backups:
                row = ctk.CTkFrame(bcard.body, fg_color=c["card_alt"], corner_radius=9)
                row.pack(fill="x", pady=3)
                inner = ctk.CTkFrame(row, fg_color="transparent")
                inner.pack(fill="x", padx=12, pady=8)
                col = ctk.CTkFrame(inner, fg_color="transparent")
                col.pack(side="left", fill="x", expand=True)
                label = "出厂备份" if b["name"] == "planet-initial.bin" else b["name"]
                ctk.CTkLabel(col, text=label, font=theme.font(12, "bold"),
                             text_color=c["text"], anchor="w").pack(anchor="w")
                ctk.CTkLabel(col, text=f"世界 ID {b['world_id']}   ·   {b['mtime']}   ·   {b['size']} 字节",
                             font=ctk.CTkFont(family="Consolas", size=11),
                             text_color=c["text_faint"], anchor="w").pack(anchor="w")
                ghost_button(inner, "恢复此备份", lambda p=b["path"], n=label: self._restore(p, n),
                             width=96, height=28).pack(side="right")

        # ---------------- 说明 ---------------- #
        tip_card = Card(wrap)
        tip_card.grid(row=2, column=0, sticky="ew", pady=(12, 0))
        tip_card.title("说明与注意事项")
        tips = [
            "planet 决定节点的「根节点」：替换为自建 planet 后，节点不再连接官方根，可实现完全私有化组网。",
            "替换过程会自动停止服务 → 写入 planet → 启动服务，期间已连接的网络会短暂中断（约 2–5 秒）。",
            "planet 必须与网络控制器（controller）的世界 ID 一致，否则节点会一直处于离线状态。",
            "首次运行本程序时会自动保存一份「出厂备份」，可一键恢复到初始根节点。",
            "若只想加入额外的根节点而不替换官方 planet，可改用 MOON：点击下方「管理 MOON」导入 .moon 文件，或手动放入 moons.d 目录。",
        ]
        for t in tips:
            ctk.CTkLabel(tip_card.body, text="·  " + t, font=theme.font(12), text_color=c["text_muted"],
                         anchor="w", justify="left", wraplength=760).pack(fill="x", pady=2)

        # ---------------- MOON ---------------- #
        mcard = Card(wrap)
        mcard.grid(row=3, column=0, sticky="ew", pady=(12, 0))
        mhead = mcard.title("MOON 节点（moons.d）", "自定义卫星根节点，可与官方 planet 共存")
        moons = moon.list_local()
        active = moon.runtime_ids((self.app.summary or {}).get("peers"))
        ctk.CTkButton(mhead, text="管理 MOON", width=86, height=26, corner_radius=7,
                      fg_color=c["accent_soft"], hover_color=c["nav_hover"],
                      text_color=c["accent"], font=theme.font(11, "bold"),
                      command=self._open_moon).pack(side="right")
        if not moons:
            empty_state(mcard.body, "尚未配置 MOON",
                        "导入 moon 文件后可加速中转，点击右上角「管理 MOON」添加").pack(fill="x")
        else:
            for m in moons[:4]:
                row = ctk.CTkFrame(mcard.body, fg_color="transparent")
                row.pack(fill="x", pady=2)
                ctk.CTkLabel(row, text=m["id"], font=ctk.CTkFont(family="Consolas", size=12),
                             text_color=c["text"], width=112, anchor="w").pack(side="left")
                sub = m.get("error") or f"{m['timestamp_text']}   ·   {m['size']} 字节"
                ctk.CTkLabel(row, text=sub, font=ctk.CTkFont(family="Consolas", size=11),
                             text_color=c["text_faint"], anchor="w").pack(side="left", padx=(6, 0))
                if not m.get("error"):
                    state = ("已生效", c["success"], c["success_soft"]) if m["id"].lower() in active \
                        else ("待生效", c["text_muted"], c["card_alt"])
                    Pill(row, state[0], fg=state[1], bg=state[2]).pack(side="right")
            if len(moons) > 4:
                ctk.CTkLabel(mcard.body, text=f"另有 {len(moons) - 4} 个 MOON，点击「管理 MOON」查看",
                             font=theme.font(11), text_color=c["text_faint"], anchor="w").pack(fill="x", pady=(4, 0))

    # ------------------------------------------------------------------ #
    def _import(self) -> None:
        path = filedialog.askopenfilename(
            parent=self.app,
            title="选择 planet 文件",
            filetypes=[("planet 文件", "*.planet *.bin *.world"), ("所有文件", "*.*")],
        )
        if not path:
            return
        try:
            with open(path, "rb") as f:
                data = f.read()
            info = planet.parse_planet(data)
        except Exception as exc:
            self.app.toast(f"文件校验失败：{exc}", "err")
            return
        msg = (
            f"即将替换根节点：\n\n"
            f"类型：{info['type_text']}\n"
            f"世界 ID：{info['world_id']}\n"
            f"世界时间：{info['timestamp_text']}\n"
            f"大小：{info['size']} 字节\n\n"
            f"替换会重启 ZeroTier 服务，现有连接将短暂中断。是否继续？"
        )
        if not confirm(self.app, "确认替换根节点", msg, ok_text="替换并重启"):
            return
        self._run(planet.apply_planet, data, ok_prefix="根节点已替换")

    def _backup(self) -> None:
        try:
            dest = planet.backup_current(tag="manual")
            self.app.toast(f"已备份到 {dest.name}", "ok")
        except Exception as exc:
            self.app.toast(str(exc), "err")
        self.refresh()

    def _restore_initial(self) -> None:
        p = config.BACKUP_DIR / "planet-initial.bin"
        if not p.exists():
            self.app.toast("尚未生成出厂备份（首次运行时会自动创建）", "warn")
            return
        self._restore(p, "出厂备份")

    def _restore(self, path, name: str) -> None:
        if not confirm(self.app, "恢复 planet 备份",
                       f"确定用「{name}」覆盖当前 planet 吗？\n\n恢复后 ZeroTier 服务将重启。",
                       ok_text="恢复并重启"):
            return
        self._run(planet.restore_backup, path, ok_prefix="已恢复备份")

    def _open_moon(self) -> None:
        dlg = MoonDialog(self.app)
        self.app.wait_window(dlg)
        self.refresh()

    def _restart(self) -> None:
        self.app.restart_service()
        self.after(1500, self.refresh)

    def _run(self, fn, *args, ok_prefix: str = "操作完成") -> None:
        if not syswin.is_admin():
            self.app.toast("该操作需要管理员权限，请以管理员身份运行本程序", "err")
            return
        self.app.toast("正在处理，服务重启中…")
        self.app.update_idletasks()

        def worker() -> None:
            try:
                msg = fn(*args)
                self.app.after(0, lambda: self._done(ok_prefix, msg, None))
            except Exception as exc:
                self.app.after(0, lambda e=exc: self._done(ok_prefix, "", e))

        threading.Thread(target=worker, daemon=True, name="planet-op").start()

    def _done(self, prefix: str, msg: str, err) -> None:
        if err is not None:
            self.app.toast(f"失败：{err}", "err")
        else:
            self.app.toast(msg or prefix, "ok")
        self.app.poll()
        self.after(800, self.refresh)
