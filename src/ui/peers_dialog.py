"""在线对端：角色、路径、P2P/中继、延迟、虚拟 IP，以及本地标签（名称/分组）。"""
from __future__ import annotations

import customtkinter as ctk

import threading

from core import netprobe, peer_order
from core import peers as peerlib
from ui import theme
from ui.dialogs import Modal, PeerLabelDialog
from ui.widgets import Pill, empty_state, ghost_button


class PeersDialog(Modal):
    def __init__(self, app):
        self.app = app
        self._filter = "all"
        self._query = ""
        self._lat_pills: dict[str, object] = {}
        self._rows: list[dict] = []
        self._drag: dict | None = None
        self._probe_targets: list[tuple[str, str]] = []
        self._probe_token = 0
        super().__init__(app, "在线对端", width=800, height=700)
        c = theme.C()

        head = ctk.CTkFrame(self.body, fg_color="transparent")
        head.pack(fill="x", padx=8, pady=(2, 6))
        self.summary = ctk.CTkLabel(head, text="", font=theme.font(12),
                                    text_color=c["text_muted"], anchor="w", justify="left",
                                    wraplength=520)
        self.summary.pack(side="left")

        seg = ctk.CTkFrame(head, fg_color=c["card_alt"], corner_radius=9,
                           border_width=1, border_color=c["border"])
        seg.pack(side="right")
        self._filter_btns: dict[str, ctk.CTkButton] = {}
        for key, label in (("all", "全部"), ("leaf", "成员"), ("roots", "根节点")):
            active = key == self._filter
            btn = ctk.CTkButton(
                seg, text=label, width=58, height=26, corner_radius=7,
                fg_color=c["accent"] if active else "transparent",
                hover_color=c["accent_hover"] if active else c["nav_hover"],
                text_color="#FFFFFF" if active else c["text_muted"],
                font=theme.font(12, "bold" if active else "normal"),
                command=lambda k=key: self._set_filter(k),
            )
            btn.pack(side="left", padx=2, pady=2)
            self._filter_btns[key] = btn

        search_row = ctk.CTkFrame(self.body, fg_color="transparent")
        search_row.pack(fill="x", padx=8, pady=(0, 8))
        self.search = ctk.CTkEntry(search_row, height=30, corner_radius=8,
                                   fg_color=c["input"], border_color=c["border"],
                                   placeholder_text="搜索标签名 / 分组 / 备注 / 地址",
                                   font=theme.font(12))
        self.search.pack(side="left", fill="x", expand=True)
        self.search.bind("<KeyRelease>", self._on_search)
        ghost_button(search_row, "刷新", self._reload, width=64, height=30).pack(side="left", padx=(6, 0))
        ctk.CTkLabel(search_row, text="拖动左侧 ≡ 调整成员顺序（根节点固定置顶）",
                     font=theme.font(10), text_color=c["text_faint"]).pack(side="left", padx=(8, 0))

        ghost_button(self.footer, "关闭", self.close, width=80).pack(side="right")
        ghost_button(self.footer, "复制全部", self._copy_all).pack(side="left")
        ctk.CTkLabel(self.footer,
                     text="延迟为内核上报值；显示「约 xx ms」是本机 ping 探测（内核未上报时自动测量）",
                     font=theme.font(10), text_color=c["text_faint"]).pack(side="left", padx=10)

        self.list_box = ctk.CTkFrame(self.body, fg_color="transparent")
        self.list_box.pack(fill="both", expand=True, padx=4, pady=(0, 8))
        self.list_box.grid_columnconfigure(0, weight=1)
        self._reload()

    # ------------------------------------------------------------------ #
    def _self_address(self) -> str:
        return str(((self.app.summary or {}).get("status") or {}).get("address") or "").lower()

    def _all_peers(self) -> list[dict]:
        """根节点置顶（固定）、成员按自定义顺序、本机置底。"""
        peers = list((self.app.summary or {}).get("peers") or [])
        return peer_order.sort_peers(peers, self._self_address(),
                                     self.app.peer_order.order())

    def _on_search(self, _evt=None) -> None:
        self._query = self.search.get().strip().lower()
        self._reload()

    def _set_filter(self, key: str) -> None:
        self._filter = key
        c = theme.C()
        for name, btn in self._filter_btns.items():
            active = name == key
            try:
                btn.configure(
                    fg_color=c["accent"] if active else "transparent",
                    hover_color=c["accent_hover"] if active else c["nav_hover"],
                    text_color="#FFFFFF" if active else c["text_muted"],
                    font=theme.font(12, "bold" if active else "normal"),
                )
            except Exception:
                pass
        self._reload()

    def _reload(self) -> None:
        for w in self.list_box.winfo_children():
            w.destroy()
        allp = self._all_peers()
        me = self._self_address()
        stat = peerlib.summarize(allp, me)
        mode = peerlib.mode_short(stat["mode"]) or "—"
        labeled = sum(1 for p in allp
                      if self.app.peer_labels.get(str(p.get("address", "")).lower())["label"])
        self.summary.configure(
            text=f"共 {stat['total']} 个对端 · 成员 {stat['leaf']}（P2P {stat['direct']} / 中继 {stat['relayed']}）"
                 f" · 根节点 {stat['roots']} · 已标注 {labeled} · 本机 {mode}"
        )

        self._lat_pills = {}
        self._rows = []
        self._probe_targets = []
        table = peerlib.neighbor_table()
        shown = 0
        for peer in allp:
            role = str(peer.get("role", "")).upper()
            is_me = str(peer.get("address", "")).lower() == me
            if self._filter == "leaf" and (role != "LEAF" or is_me):
                continue
            if self._filter == "roots" and role not in ("PLANET", "MOON"):
                continue
            if self._query and not self._match(peer):
                continue
            self._render_row(peer, is_me, table)
            shown += 1

        if shown == 0:
            empty_state(self.list_box, "没有匹配的对端",
                        "换个关键词，或等待对端连接后再看").pack(fill="x")
        else:
            self._start_probe()

    def _match(self, peer: dict) -> bool:
        addr = str(peer.get("address", "")).lower()
        meta = self.app.peer_labels.get(addr)
        hay = " ".join([addr, meta["label"], meta["group"], meta["note"],
                        peerlib.role_name(peer)]).lower()
        return self._query in hay

    def _render_row(self, peer: dict, is_me: bool, table: dict[str, str]) -> None:
        c = theme.C()
        role = str(peer.get("role", "")).upper()
        addr = str(peer.get("address", ""))
        meta = self.app.peer_labels.get(addr.lower())
        labeled = bool(meta["label"])
        vip = peerlib.virtual_ip(peer, table) if not is_me else ""

        if labeled:
            bar = meta["color"]
        else:
            bar = {"PLANET": c["accent"], "MOON": c["warn"]}.get(
                role, c["success"] if not peerlib.is_relayed(peer) else c["text_faint"])

        card = ctk.CTkFrame(self.list_box, fg_color=c["card_alt"], corner_radius=10,
                            border_width=1, border_color=c["border"])
        card.grid(row=len(self._rows), column=0, sticky="ew", pady=4, padx=4)
        row_ref = {"addr": addr.lower(), "card": card,
                   "root": role in peer_order.ROOT_ROLES, "me": is_me}
        self._rows.append(row_ref)
        body = ctk.CTkFrame(card, fg_color="transparent")
        body.pack(fill="x", padx=12, pady=10)

        # 右侧操作先占位，避免被长文本挤压
        right = ctk.CTkFrame(body, fg_color="transparent")
        right.pack(side="right", padx=(8, 0))
        if is_me:
            Pill(right, "本机", fg=c["accent"], bg=c["accent_soft"]).pack(side="right")
        else:
            link = peerlib.link_text(peer)
            fg, bg = (c["success"], c["success_soft"]) if link.startswith("P2P") else (
                (c["warn"], c["warn_soft"]) if link == "中继" else (c["text_muted"], c["card"]))
            Pill(right, link, fg=fg, bg=bg).pack(side="right")
            lat = peerlib.latency_text(peer)
            measured = lat.endswith("ms")
            lat_pill = Pill(right, f"延迟 {lat}" if measured else lat,
                            fg=c["text_muted"] if measured else c["text_faint"],
                            bg=c["card"] if measured else c["card_alt"])
            lat_pill.pack(side="right", padx=6)
            if not measured:
                # 内核未上报：稍后用本机 ping 补一个参考值
                host = netprobe.endpoint_host(peerlib.endpoint(peer)) or vip
                self._lat_pills[str(peer.get("address", "")).lower()] = lat_pill
                if host:
                    self._probe_targets.append((str(peer.get("address", "")).lower(), host))
            ghost_button(right, "标签", lambda p=peer: self._edit_label(p), width=52,
                         height=26).pack(side="right", padx=(6, 0))
            ghost_button(right, "复制", lambda p=peer: self._copy_peer(p), width=50,
                         height=26).pack(side="right", padx=(6, 0))

        left = ctk.CTkFrame(body, fg_color="transparent")
        left.pack(side="left", fill="x", expand=True)
        line1 = ctk.CTkFrame(left, fg_color="transparent")
        line1.pack(fill="x")
        draggable = not (row_ref["root"] or is_me)
        handle = ctk.CTkLabel(line1, text="≡", width=18,
                              font=theme.font(13, "bold"),
                              text_color=c["text_muted"] if draggable else c["border"])
        handle.pack(side="left", padx=(0, 6))
        row_ref["handle"] = handle
        row_ref["draggable"] = draggable
        if draggable:
            self._bind_drag(handle, row_ref)
        ctk.CTkFrame(line1, width=4, height=16, fg_color=bar, corner_radius=2).pack(
            side="left", padx=(0, 8))
        if labeled:
            ctk.CTkLabel(line1, text=meta["label"], font=theme.font(14, "bold"),
                         text_color=c["text"]).pack(side="left")
            ctk.CTkLabel(line1, text=addr, font=ctk.CTkFont(family="Consolas", size=11),
                         text_color=c["text_faint"]).pack(side="left", padx=(8, 0))
        else:
            ctk.CTkLabel(line1, text=addr,
                         font=ctk.CTkFont(family="Consolas", size=13, weight="bold"),
                         text_color=c["text"]).pack(side="left")
        if meta["group"]:
            Pill(line1, meta["group"], fg=c["accent"], bg=c["accent_soft"]).pack(
                side="left", padx=8)
        ctk.CTkLabel(line1, text=peerlib.role_name(peer), font=theme.font(11),
                     text_color=c["text_muted"]).pack(side="left", padx=(8, 0))

        seg = []
        ep = peerlib.endpoint(peer)
        seg.append("路径 " + (ep if ep else ("本机" if is_me else "—")))
        if vip:
            seg.append("虚拟 IP " + vip)
        seg.append("版本 " + str(peer.get("version") or "—"))
        seg.append(peerlib.last_seen_text(peer))
        ctk.CTkLabel(left, text="   ·   ".join(seg),
                     font=ctk.CTkFont(family="Consolas", size=11),
                     text_color=c["text_faint"], anchor="w").pack(anchor="w", pady=(4, 0))

        if meta["note"]:
            ctk.CTkLabel(left, text="备注：" + meta["note"], font=theme.font(11),
                         text_color=c["text_muted"], anchor="w").pack(anchor="w", pady=(3, 0))
        elif not is_me and role == "LEAF" and not vip:
            ctk.CTkLabel(left, text="虚拟 IP：本机尚未与该节点二层通信，ARP 表暂无记录",
                         font=theme.font(10), text_color=c["text_faint"], anchor="w").pack(
                anchor="w", pady=(2, 0))

    # ------------------------------------------------------------------ #
    # 拖拽排序（根节点与本机不可拖，仅在成员之间调整）
    # ------------------------------------------------------------------ #
    def _bind_drag(self, handle, row: dict) -> None:
        try:
            handle.configure(cursor="fleur")
        except Exception:
            pass
        handle.bind("<Button-1>", lambda e, r=row: self._drag_start(r))
        handle.bind("<B1-Motion>", self._drag_move)
        handle.bind("<ButtonRelease-1>", self._drag_end)

    def _drag_start(self, row: dict) -> None:
        self._drag = {"addr": row["addr"], "moved": False, "row": row}
        try:
            row["card"].configure(border_color=theme.C()["accent"])
        except Exception:
            pass

    def _drop_index(self, y_root: int) -> int:
        for i, row in enumerate(self._rows):
            card = row["card"]
            try:
                top, height = card.winfo_rooty(), card.winfo_height()
            except Exception:
                continue
            if y_root < top + height / 2:
                return i
        return len(self._rows)

    def _member_range(self) -> tuple[int, int]:
        """可拖拽区间的 [最小索引, 最大索引]。"""
        first = sum(1 for r in self._rows if r["root"])
        last = len(self._rows) - 1 - sum(1 for r in self._rows if r["me"])
        return first, max(first, last)

    def _drag_move(self, event) -> None:
        if not self._drag:
            return
        addr = self._drag["addr"]
        current = next((i for i, r in enumerate(self._rows) if r["addr"] == addr), None)
        if current is None:
            return
        target = self._drop_index(event.y_root)
        lo, hi = self._member_range()
        target = max(lo, min(target, hi))
        if target == current:
            return
        row = self._rows.pop(current)
        self._rows.insert(target, row)
        self._drag["moved"] = True
        self._relayout()

    def _drag_end(self, _event=None) -> None:
        if not self._drag:
            return
        moved = bool(self._drag["moved"])
        row = self._drag.get("row")
        self._drag = None
        if row is not None:
            try:
                row["card"].configure(border_color=theme.C()["border"])
            except Exception:
                pass
        if moved:
            self._persist_order()
            self.app.toast("对端显示顺序已保存", "ok")

    def _relayout(self) -> None:
        for i, row in enumerate(self._rows):
            try:
                row["card"].grid_configure(row=i)
            except Exception:
                pass

    def _persist_order(self) -> None:
        addresses = [r["addr"] for r in self._rows if not r["root"] and not r["me"]]
        self.app.peer_order.set_order(addresses)

    # ------------------------------------------------------------------ #
    def _start_probe(self) -> None:
        """内核未上报延迟时，后台用 ping 补测（本机参考值）。"""
        targets = list(self._probe_targets)
        self._probe_token += 1
        token = self._probe_token
        if not targets:
            return
        c = theme.C()

        def worker() -> None:
            for address, host in targets:
                if token != self._probe_token:
                    return
                value = netprobe.ping_latency(host)
                if value is None:
                    continue
                text = netprobe.latency_hint(value)
                self.app.dispatch.call(
                    lambda a=address, t=text: self._apply_probe(a, t, token))

        threading.Thread(target=worker, daemon=True, name="latency-probe").start()

    def _apply_probe(self, address: str, text: str, token: int) -> None:
        if token != self._probe_token:
            return
        pill = self._lat_pills.get(address)
        if pill is None:
            return
        c = theme.C()
        try:
            pill.restyle(text, c["text_muted"], c["card"])
        except Exception:
            pass

    # ------------------------------------------------------------------ #
    def _edit_label(self, peer: dict) -> None:
        PeerLabelDialog(self.app, self.app, peer, on_saved=self._reload)

    def _copy_peer(self, peer: dict) -> None:
        vip = peerlib.virtual_ip(peer)
        meta = self.app.peer_labels.get(str(peer.get("address", "")).lower())
        text = peerlib.peer_info_text(peer, vip)
        if meta["label"]:
            text = f"名称：{meta['label']}\n" + text
        if meta["group"]:
            text += f"\n分组：{meta['group']}"
        self.clipboard_clear()
        self.clipboard_append(text)
        self.app.toast(f"已复制对端 {peer.get('address')} 信息", "ok")

    def _copy_all(self) -> None:
        me = self._self_address()
        rows = []
        for p in self._all_peers():
            if str(p.get("address", "")).lower() == me:
                continue
            meta = self.app.peer_labels.get(str(p.get("address", "")).lower())
            text = peerlib.peer_info_text(p, peerlib.virtual_ip(p))
            if meta["label"]:
                text = f"名称：{meta['label']}\n" + text
            if meta["group"]:
                text += f"\n分组：{meta['group']}"
            if meta["note"]:
                text += f"\n备注：{meta['note']}"
            rows.append(text)
        if not rows:
            self.app.toast("没有可复制的对端信息", "warn")
            return
        self.clipboard_clear()
        self.clipboard_append("\n\n".join(rows))
        self.app.toast("已复制全部对端信息", "ok")
