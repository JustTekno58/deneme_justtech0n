'''
Selsil Pro V6 - Ana Ekran (UI)
Bu dosya operatör ekranını içerir ve diğer modülleri orkestre eder.
'''
from __future__ import annotations
import tkinter as tk
from tkinter import ttk, messagebox
import tkinter.font as tkfont
from datetime import datetime
from collections import deque
import time
import unicodedata
import os
import sys
import subprocess
import socket
import threading
import json
import code_parser
import arama_penceresi
from veri_yonetimi import VeriYonetimi
from kolonlar_penceresi import KolonlarPenceresi
from donanim_servisleri import DonanimServisleri
from yetkili_paneli import YetkiliPaneli
class AnaEkran:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("Selsil Pro V6 - Endüstriyel Modüler Yapı")
        self.root.geometry("1200x900")
        self.root.configure(bg="#f0f0f0")
        self._kaydet_win = None
        # Veri
        self.work_list: list[dict] = []
        self.box_label_list: list[str] = []
        self.verified_count = 0
        self._scan_times = deque(maxlen=600)
        self._last_eta_update = 0.0
        # Gauge animasyon değerleri
        self._g_fill_val = 0.0
        self._g_fill_target = 0.0
        self._g_speed_val = 0.0
        self._g_speed_target = 0.0
        self.items_per_box = 0
        self.current_file = "YeniIs"
        # Job sistemi (kaldığın yerden devam)
        self.current_job_id = None
        try:
            self.job_manager = JobYonetimi()
        except Exception:
            self.job_manager = None
        self.next_print_info = {"box_num": 1, "label": "-"}
        self.var_short_code = tk.IntVar(value=0)
        # Yazdırma aktif/pasif
        self.var_printer_enabled = tk.IntVar(value=1)
        # Reject (kullanıcı aç/kapat)
        self.var_reject_enabled = tk.IntVar(value=1)
        # Üretim tarihi (opsiyonel/zorunlu)
        self.var_date_required = tk.IntVar(value=0)
        self.var_prod_date = tk.StringVar(value="")
        # Son okuma gösterimi (önceki / son)
        self.prev_scan_text = ""
        self.last_scan_text = ""
        # Scanner raporu (tekrar / listede yok / okunamadı)
        # Her kayıt: dict(ts, type, barcode, row_id, box, message)
        self.scan_report: list[dict] = []

        # Yazıcı bağlantı kontrol cache (UI rozetleri için)
        # None: bilinmiyor, True: bağlı, False: bağlı değil
        self._printer_state = {"box": None, "prod": None, "prod2": None}
        self._printer_check_inflight = False
        # Servisler
        self.veri = VeriYonetimi(app=self)
        self.donanim = DonanimServisleri(app=self)
        # Kullanıcı reject kontrolü (checkbox)
        try:
            self.donanim.reject_user_enabled = bool(self.var_reject_enabled.get())
        except Exception:
            pass
        self.yetkili = YetkiliPaneli(app=self)
        # UI
        self.style = ttk.Style()
        self.style.theme_use("clam")
        self._setup_ui()
        # DB + ayar yükle
        self.veri.init_db()
        self.veri.load_settings()
        self.var_short_code.set(self.veri.settings.get("short_code", 0))
        self.var_date_required.set(int(self.veri.settings.get("date_required", 0)))
        self.var_prod_date.set(self.veri.settings.get("production_date", ""))
        self.var_printer_enabled.set(int(self.veri.settings.get("printer_enabled", 1)))
        self._sync_date_ui()
        self.apply_tree_settings()
        # Dizayn / Tema / Font / Dashboard yerleşimi
        try:
            self.apply_design_from_settings()
        except Exception:
            pass
        # Reject + son iş
        self.donanim.init_rejector()
        try:
            self.update_ui()
        except Exception:
            pass
        self.veri.load_last_job()
        # Scanner thread
        self.donanim.start_scanner_listener()

        # Yazıcı rozetleri: gerçek bağlantı kontrolünü periyodik yap
        # (IP yazılmış olsa bile kablo yoksa kırmızı gösterir.)
        self._start_device_badge_loop()
        # Reject uyarısı (sadece kullanıcı REJECT'i açık bıraktıysa ve gerçekten aktif değilse)
        try:
            enabled = bool(self.var_reject_enabled.get())
            active = bool(getattr(self.donanim, "reject_is_active", False))
            rejector = getattr(self.donanim, "rejector", None)
            if enabled and (not active):
                reason = getattr(rejector, "last_error", None) if rejector else None
                ports = []
                try:
                    if rejector and hasattr(rejector, "available_ports"):
                        ports = rejector.available_ports()
                except Exception:
                    ports = []
                if reason == "PYSerialMissing":
                    msg = "Reject sistemi devre dışı: pyserial bulunamadı.\n(Reject olmadan devam edilecek.)"
                elif reason == "PORT_NOT_FOUND":
                    msg = f"Reject Portu bulunamadı: {getattr(rejector, 'port_name', 'COM?')}\nMevcut portlar: {', '.join(ports) if ports else '-'}\n(Reject olmadan devam edilecek.)"
                else:
                    msg = f"Reject Portu açılamadı: {getattr(rejector, 'port_name', 'COM?')}\nMevcut portlar: {', '.join(ports) if ports else '-'}\n(Reject olmadan devam edilecek.)"
                self.root.after(1000, lambda m=msg: messagebox.showwarning("Sistem", m))
        except Exception:
            pass
    # ---------------- UI ----------------
    def _setup_ui(self):
        # Root layout
        self.root.configure(bg="#f2f2f2")
        self.root.rowconfigure(0, weight=1)
        self.root.columnconfigure(0, weight=1)

        self.main_frame = tk.Frame(self.root, bg="#f2f2f2")
        self.main_frame.grid(row=0, column=0, sticky="nsew")
        # rows: 0 command, 1 summary, 2 upload, 3 files, 4 content
        self.main_frame.rowconfigure(4, weight=1)
        self.main_frame.columnconfigure(0, weight=1)

        # =========================
        # 1) ÜST KOMUT ŞERİDİ (Excel tasarımına yakın)
        # =========================
        self.command_bar = tk.Frame(self.main_frame, bg="#0b2e4a", height=46)
        self.command_bar.grid(row=0, column=0, sticky="ew")
        self.command_bar.grid_propagate(False)

        # Grid columns: left buttons, center title, right dot
        for c in range(12):
            self.command_bar.columnconfigure(c, weight=0)
        self.command_bar.columnconfigure(10, weight=1)

        # MENÜ (sol)
        self.menu_btn = tk.Label(
            self.command_bar,
            text="☰  MENÜ",
            fg="white",
            bg="#0b2e4a",
            font=("Segoe UI", 11, "bold"),
            cursor="hand2",
            padx=10,
            pady=8,
        )
        self.menu_btn.grid(row=0, column=0, sticky="w")
        # Sol üst MENÜ: popup menü (sağ tık benzeri)
        self.menu_btn.bind("<Button-1>", self.toggle_menu)

        # ---- POPUP MENÜ (MENÜ butonu) ----
        self._popup_menu = tk.Menu(self.root, tearoff=0)
        self._popup_menu.add_command(label="İşlemler", state="disabled")
        self._popup_menu.add_command(label="  💾 Kaydet", command=self.open_kaydet_window)
        self._popup_menu.add_command(label="  🔎 Arama", command=self.open_search_window)
        self._popup_menu.add_command(label="  🧩 Kolonlar", command=self.open_columns_window)
        self._popup_menu.add_separator()
        self._popup_menu.add_command(label="Kurulum", state="disabled")
        self._popup_menu.add_command(label="  🧰 Ayarlar", command=self.open_settings)
        self._popup_menu.add_command(label="  👤 Yönetici", command=self.open_admin_panel)
        self._popup_menu.add_command(label="  🟣 Ön Hazırlık", command=self.open_on_hazirlik)
        self._popup_menu.add_separator()
        self._popup_menu.add_command(label="Sistem", state="disabled")
        self._popup_menu.add_command(label="  🚪 Çıkış", command=self.on_exit)

        # DURUM BUTONLARI (kısa isim + sadece renk)
        # Renkler: Yeşil=Bağlı, Sarı=Aranıyor, Kırmızı=Bağlı Değil, Mavi=Yenileniyor
        self._hw_colors = {
            "connected": "#198754",
            "searching": "#f1c40f",
            "disconnected": "#dc3545",
            "refresh": "#0d6efd",
            "disabled": "#7f8c8d",
        }

        def _mk_status_btn(text: str):
            return tk.Button(
                self.command_bar,
                text=text,
                bg=self._hw_colors["disconnected"],
                fg="white",
                relief="raised",
                bd=2,
                padx=10,
                pady=6,
                font=("Segoe UI", 8, "bold"),
                cursor="hand2",
            )

        self.btn_scanner_status = _mk_status_btn("Scanner")
        self.btn_scanner_status.grid(row=0, column=1, padx=(6, 0), pady=6)

        self.btn_reject_status = _mk_status_btn("Rej-(COM2)")
        self.btn_reject_status.grid(row=0, column=2, padx=6, pady=6)

        # Reject AKTİF checkbox (sadece kutu)
        self.reject_chk = tk.Checkbutton(
            self.command_bar,
            text="",
            variable=self.var_reject_enabled,
            command=self._on_reject_toggle,
            bg="#0b2e4a",
            fg="white",
            activebackground="#0b2e4a",
            activeforeground="white",
            selectcolor="#0b2e4a",
            font=("Segoe UI", 9, "bold"),
            width=2,
        )
        self.reject_chk.grid(row=0, column=3, padx=(0, 6))

        self.btn_zd230 = _mk_status_btn("Z-ZD230")
        self.btn_zd230.grid(row=0, column=4, padx=6, pady=6)

        self.btn_zt411_01 = _mk_status_btn("Z-1-ZT411")
        self.btn_zt411_01.grid(row=0, column=5, padx=6, pady=6)

        self.btn_zt411_02 = _mk_status_btn("Z-2-ZT411")
        self.btn_zt411_02.grid(row=0, column=6, padx=6, pady=6)

        # Donanım servisleri uyumluluğu (eski isimler)
        self.lbl_scanner_status = self.btn_scanner_status
        self.lbl_reject_status = self.btn_reject_status
        self.badge_zd230 = self.btn_zd230
        self.badge_zt411_01 = self.btn_zt411_01
        self.badge_zt411_02 = self.btn_zt411_02

        # Çift tık ile yenileme (mavi 1.2sn)
        self.btn_scanner_status.bind("<Double-Button-1>", lambda e: self.refresh_device("scanner"))
        self.btn_reject_status.bind("<Double-Button-1>", lambda e: self.refresh_device("reject"))
        self.btn_zd230.bind("<Double-Button-1>", lambda e: self.refresh_device("box"))
        self.btn_zt411_01.bind("<Double-Button-1>", lambda e: self.refresh_device("prod"))
        self.btn_zt411_02.bind("<Double-Button-1>", lambda e: self.refresh_device("prod2"))

        # Başlık (ortada)
        self.title_label = tk.Label(
            self.command_bar,
            text="SELSIL PRO (V6)",
            fg="white",
            bg="#0b2e4a",
            font=("Segoe UI", 12, "bold"),
        )
        self.title_label.grid(row=0, column=10)

        # Sağda küçük durum noktası
        self.right_dot = tk.Label(self.command_bar, text="●", fg="white", bg="#0b2e4a")
        self.right_dot.grid(row=0, column=11, sticky="e", padx=10)




        # =========================
        # 2) ÖZET ŞERİDİ (Kompakt): | Sistem | ÜRÜN | BOX | Palet |
        # =========================
        self.summary_row = tk.Frame(self.main_frame, bg="#f2f2f2")
        self.summary_row.grid(row=1, column=0, sticky="ew", padx=10, pady=(10, 4))

        # Üst özet: daralt/genişlet (Sistem / Ürün / Box / Palet)
        self.summary_pane = ttk.Panedwindow(self.summary_row, orient="horizontal")
        self.summary_pane.pack(fill="x", expand=True)
        try:
            self.summary_pane.bind("<ButtonRelease-1>", lambda _e: self._save_layout_sashes())
        except Exception:
            pass

        def _mini_block(parent, title: str):
            f = tk.LabelFrame(parent, text=title, bg="#f2f2f2", font=("Segoe UI", 8, "bold"))
            return f

        # Sistem
        self.sys_panel = _mini_block(self.summary_pane, "Sistem Hazır")
        self.lbl_sys_state = tk.Label(self.sys_panel, text="HAZIR", bg="#f2f2f2", fg="#198754", font=("Segoe UI", 10, "bold"))
        self.lbl_sys_state.pack(side="left", padx=8, pady=6)
        self.lbl_sys_koli = tk.Label(self.sys_panel, text="Koli: 0/0", bg="#f2f2f2", fg="#111", font=("Segoe UI", 8, "bold"))
        self.lbl_sys_koli.pack(side="left", padx=8, pady=6)

        # ÜRÜN
        self.urun_panel = _mini_block(self.summary_pane, "ÜRÜN")
        for c in range(4):
            self.urun_panel.columnconfigure(c, weight=1)
        card1, self.lbl_total = self._create_stat_card(self.urun_panel, "Toplam", "0")
        card2, self.lbl_ok = self._create_stat_card(self.urun_panel, "Yapılan", "0")
        card3, self.lbl_next = self._create_stat_card(self.urun_panel, "Sonraki", "-")
        card4, self.lbl_remaining = self._create_stat_card(self.urun_panel, "Kalan", "0")
        for idx, card in enumerate((card1, card2, card3, card4)):
            card.grid(row=0, column=idx, sticky="ew", padx=4, pady=4)

        # BOX
        self.box_panel = _mini_block(self.summary_pane, "BOX")
        for c in range(4):
            self.box_panel.columnconfigure(c, weight=1)
        b1, self.lbl_box_goal = self._create_stat_card(self.box_panel, "Toplam", "0")
        b2, self.lbl_box_done = self._create_stat_card(self.box_panel, "Yapılan", "0")
        b3, self.lbl_box_next = self._create_stat_card(self.box_panel, "Sonraki", "-")
        b4, self.lbl_box_left = self._create_stat_card(self.box_panel, "Kalan", "0")
        for idx, card in enumerate((b1, b2, b3, b4)):
            card.grid(row=0, column=idx, sticky="ew", padx=4, pady=4)

        # Palet
        self.palet_count = 0
        self.palet_icerik = 0
        self.palet_total = 0
        self.palet_panel = _mini_block(self.summary_pane, "Palet")
        for c in range(3):
            self.palet_panel.columnconfigure(c, weight=1)
        p1, self.lbl_palet_adet = self._create_stat_card(self.palet_panel, "Adet", "0")
        p2, self.lbl_palet_icerik = self._create_stat_card(self.palet_panel, "İçerik", "0")
        p3, self.lbl_palet_toplam = self._create_stat_card(self.palet_panel, "Toplam", "0")
        for idx, card in enumerate((p1, p2, p3)):
            card.grid(row=0, column=idx, sticky="ew", padx=4, pady=4)

        # pane'e ekle (weight: Sistem=2, Ürün=3, Box=3, Palet=2)
        try:
            self.summary_pane.add(self.sys_panel, weight=2)
            self.summary_pane.add(self.urun_panel, weight=3)
            self.summary_pane.add(self.box_panel, weight=3)
            self.summary_pane.add(self.palet_panel, weight=2)
        except Exception:
            pass

        # 3) DOSYA ÇAĞIRMA (Excel tasarımındaki büyük butonlar)
        # İstek: Ürün / Box bölmeleri daraltılıp genişletilebilsin (PanedWindow)
        # =========================
        self.upload_row = ttk.Panedwindow(self.main_frame, orient="horizontal")
        self.upload_row.grid(row=2, column=0, sticky="ew", padx=10, pady=(0, 8))

        self._upload_left = tk.Frame(self.upload_row, bg="#f2f2f2")
        self._upload_right = tk.Frame(self.upload_row, bg="#f2f2f2")
        self.upload_row.add(self._upload_left, weight=1)
        self.upload_row.add(self._upload_right, weight=1)
        try:
            self.upload_row.bind("<ButtonRelease-1>", lambda _e: self._save_layout_sashes())
        except Exception:
            pass

        self.btn_prod = tk.Button(
            self._upload_left,
            text="1. ÜRÜN LİSTESİ",
            command=lambda: self.load_file("prod"),
            bg="white",
            fg="black",
            relief="solid",
            bd=1,
            font=("Segoe UI", 10, "bold"),
            height=2,
            cursor="hand2",
        )
        self.btn_prod.pack(fill="x", expand=True)

        self.btn_box = tk.Button(
            self._upload_right,
            text="2. KOLİ ETİKETLERİ",
            command=lambda: self.load_file("box"),
            bg="white",
            fg="black",
            relief="solid",
            bd=1,
            font=("Segoe UI", 10, "bold"),
            height=2,
            cursor="hand2",
        )
        self.btn_box.pack(fill="x", expand=True)

        # =========================
        # 4) ÖNCEKİ / SONRAKİ DOSYA KUTULARI (PanedWindow)
        # =========================
        self.files_row = ttk.Panedwindow(self.main_frame, orient="horizontal")
        self.files_row.grid(row=3, column=0, sticky="ew", padx=10, pady=(0, 6))

        self._files_left = tk.Frame(self.files_row, bg="#f2f2f2")
        self._files_right = tk.Frame(self.files_row, bg="#f2f2f2")
        self.files_row.add(self._files_left, weight=1)
        self.files_row.add(self._files_right, weight=1)
        try:
            self.files_row.bind("<ButtonRelease-1>", lambda _e: self._save_layout_sashes())
        except Exception:
            pass
        self.prev_box = tk.LabelFrame(self._files_left, text="Önceki", bg="#f2f2f2", font=("Segoe UI", 9, "bold"))
        self.prev_box.pack(fill="x", expand=True)
        self.lbl_previous = tk.Label(self.prev_box, text="-", bg="#f2f2f2", anchor="w")
        self.lbl_previous.pack(fill="x", padx=8, pady=6)

        self.next_box = tk.LabelFrame(self._files_right, text="Sonraki", bg="#f2f2f2", font=("Segoe UI", 9, "bold"))
        self.next_box.pack(fill="x", expand=True)
        self.lbl_nextcode = tk.Label(self.next_box, text="-", bg="#f2f2f2", anchor="w")
        self.lbl_nextcode.pack(fill="x", padx=8, pady=6)

        # =========================
        # 6) KONTROLLER + TABLO
        # =========================
        self.content_frame = tk.Frame(self.main_frame, bg="#f2f2f2")
        self.content_frame.grid(row=4, column=0, sticky="nsew", padx=10, pady=(0, 6))
        self.content_frame.rowconfigure(2, weight=1)
        self.content_frame.rowconfigure(3, weight=0)
        self.content_frame.columnconfigure(0, weight=1)

        controls = tk.Frame(self.content_frame, bg="#f2f2f2")
        controls.grid(row=0, column=0, sticky="ew", pady=(0, 6))
        controls.columnconfigure(9, weight=1)

        tk.Label(controls, text="Koli İçi Adet:", bg="#f2f2f2", font=("Segoe UI", 9, "bold")).grid(
            row=0, column=0, padx=(0, 6)
        )
        self.entry_koli_adet = tk.Entry(controls, width=8)
        self.entry_koli_adet.grid(row=0, column=1, padx=(0, 12))
        self.entry_koli_adet.insert(0, str(self.items_per_box))
        self.entry_koli_adet.bind('<KeyRelease>', self.update_box_size)
        self.entry_koli_adet.bind('<FocusOut>', self.update_box_size)

        self.chk_printer = tk.Checkbutton(
            controls, text="Yazıcı Aktif", variable=self.var_printer_enabled, command=self._on_printer_toggle, bg="#f2f2f2"
        )
        self.chk_printer.grid(row=0, column=2, padx=(0, 12))

        tk.Label(controls, text="Manuel:", bg="#f2f2f2", font=("Segoe UI", 9, "bold")).grid(row=0, column=3, padx=(0, 6))
        self.btn_manual_verify = tk.Button(
            controls,
            text="Manuel Ekle/Doğrula",
            command=self.open_manual_verify,
            bg="#ffffff",
            fg="#111",
            relief="solid",
            bd=1,
            font=("Segoe UI", 9, "bold"),
            cursor="hand2",
            padx=10,
            pady=2,
        )
        self.btn_manual_verify.grid(row=0, column=4, padx=(0, 12), sticky="w")

        # Üretim tarihi
        tk.Label(controls, text="Üretim Tarihi:", bg="#f2f2f2").grid(row=0, column=5, padx=(0, 6))
        self.entry_date = tk.Entry(controls, width=12)
        self.entry_date.grid(row=0, column=6, padx=(0, 12))


        # Numpad: sayı/tarih alanlarına tıklayınca otomatik aç
        try:
            self.bind_numpad(self.entry_koli_adet, "Koli Adet", allow_empty=False)
            self.bind_numpad(self.entry_date, "Tarih (GG.AA.YYYY)", allow_empty=True)
        except Exception:
            pass

        self.chk_date_required = tk.Checkbutton(
            controls, text="Tarih Zorunlu", variable=self.var_date_required, command=self._on_date_required_changed, bg="#f2f2f2"
        )
        self.chk_date_required.grid(row=0, column=7, padx=(0, 12))

        self.lbl_short_status = tk.Label(controls, text="KOD TÜRÜ: -", bg="#f2f2f2", font=("Segoe UI", 10, "bold"))
        self.lbl_short_status.grid(row=0, column=8, sticky="e")
        # FIX: Kod türü etiketi için ortak isim (diğer modüller lbl_loaded_code_type bekliyor)
        self.lbl_loaded_code_type = self.lbl_short_status

        # Tablo
        table_holder = tk.Frame(self.content_frame, bg="#ffffff", bd=1, relief="solid")
        table_holder.grid(row=2, column=0, sticky="nsew")
        table_holder.rowconfigure(0, weight=1)
        table_holder.columnconfigure(0, weight=1)

        columns = ("ID", "Koli", "Durum", "Tarih", "Barkod", "Koli Etiketi", "Koli İç No")
        self.tree = ttk.Treeview(table_holder, columns=columns, show="headings")
        for col in columns:
            self.tree.heading(col, text=col)

        self.tree.column("ID", width=60, anchor="center")
        self.tree.column("Koli", width=70, anchor="center")
        self.tree.column("Durum", width=90, anchor="center")
        self.tree.column("Tarih", width=90, anchor="center")
        self.tree.column("Barkod", width=450, anchor="w")
        self.tree.column("Koli Etiketi", width=260, anchor="w")
        self.tree.column("Koli İç No", width=120, anchor="center")

        vsb = ttk.Scrollbar(table_holder, orient="vertical", command=self.tree.yview)
        hsb = ttk.Scrollbar(table_holder, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)

        self.tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")

        # Sağ tık menüsü (gelişmiş)
        self.context_menu = tk.Menu(self.root, tearoff=0)
        self.context_menu.add_command(label="Karekod Göster", command=self.show_selected_datamatrix)
        self.context_menu.add_command(label="Tam Kodu Kopyala", command=self.copy_product_code)
        self.context_menu.add_command(label="Detayları Göster", command=self.show_selected_details)
        self.context_menu.add_separator()

        self._menu_print_prod = tk.Menu(self.context_menu, tearoff=0)
        self._menu_print_box = tk.Menu(self.context_menu, tearoff=0)
        self.context_menu.add_cascade(label="ÜRÜNÜ YAZDIR ▶", menu=self._menu_print_prod)
        self.context_menu.add_cascade(label="BOX ETİKETİ YAZDIR ▶", menu=self._menu_print_box)

        self.context_menu.add_separator()
        self.context_menu.add_command(label="KOLİ KODUNU KOPYALA", command=self.copy_box_code)

        # Sağ tık menüsü
        self.tree.bind("<Button-3>", self.show_context_menu)

        # =========================
        # 7) ALT: Scanner Durum Raporu + Dashboard (yan yana, sürüklenebilir)
        # İstek: Dashboard (Sistem Hazır / ETA / Kalan / Hız / Koli) bu bölüme taşındı.
        # =========================
        self.bottom_pane = ttk.Panedwindow(self.content_frame, orient="horizontal")
        self.bottom_pane.grid(row=3, column=0, sticky="ew", pady=(8, 0))

        self._bottom_left = tk.Frame(self.bottom_pane, bg="#f2f2f2")
        self._bottom_right = tk.Frame(self.bottom_pane, bg="#f2f2f2")
        self.bottom_pane.add(self._bottom_left, weight=4)
        self.bottom_pane.add(self._bottom_right, weight=2)

        # --- Sol: Scanner Durum Raporu ---
        self.scan_report_frame = tk.LabelFrame(
            self._bottom_left, text="Scanner Durum Raporu", bg="#f2f2f2", font=("Segoe UI", 9, "bold")
        )
        self.scan_report_frame.pack(fill="both", expand=True)

        self.scan_tree = ttk.Treeview(self.scan_report_frame, columns=("no", "mesaj"), show="headings", height=7)
        self.scan_tree.heading("no", text="NO")
        self.scan_tree.heading("mesaj", text="Durum")
        self.scan_tree.column("no", width=50, anchor="center")
        self.scan_tree.column("mesaj", width=900, anchor="w")
        self.scan_tree.pack(fill="both", expand=True)

        # --- Sağ: Dashboard (A/B seçenekleri) ---
        self.dashboard_host = tk.Frame(self._bottom_right, bg="#0b0f14", highlightthickness=1, highlightbackground="#1f2937")
        self.dashboard_host.pack(fill="both", expand=True)
        self._dash_variants = {}
        self._build_dashboard_variants(self.dashboard_host)
        self.set_dashboard_layout("A", persist=False)
        # Paned sash kaydı
        try:
            self.bottom_pane.bind("<ButtonRelease-1>", lambda _e: self._save_layout_sashes())
        except Exception:
            pass

        # tarih alanı ilk duruma göre
        try:
            self._sync_date_ui()
        except Exception:
            pass


        # ---------------- Print selected (Context Menu) ----------------
    def _get_selected_barcode(self):
        """Seçili satırdan Barkod kolonunu döndürür (yoksa None)."""
        try:
            sel = self.tree.selection()
            if not sel:
                return None
            iid = sel[0]
            vals = self.tree.item(iid, 'values') or []
            cols = list(self.tree['columns'])
            if 'Barkod' in cols:
                idx = cols.index('Barkod')
            else:
                # geriye dönük: 5. kolon barkod olabilir
                idx = 4 if len(vals) > 4 else None
            if idx is None or idx >= len(vals):
                return None
            code = str(vals[idx]).strip()
            return code if code and code != '-' else None
        except Exception:
            return None

    def _get_selected_box_label(self):
        """Seçili satırdan 'Koli Etiketi' kolonunu döndürür (yoksa None)."""
        try:
            sel = self.tree.selection()
            if not sel:
                return None
            iid = sel[0]
            vals = self.tree.item(iid, 'values') or []
            cols = list(self.tree['columns'])
            if 'Koli Etiketi' in cols:
                idx = cols.index('Koli Etiketi')
            else:
                # geriye dönük: 6. kolon box etiketi olabilir
                idx = 5 if len(vals) > 5 else None
            if idx is None or idx >= len(vals):
                return None
            code = str(vals[idx]).strip()
            return code if code and code != '-' else None
        except Exception:
            return None

    def _refresh_print_menus(self):
        """Sağ-tık menüsündeki yazdır alt menülerini ayarlara göre yeniler."""
        try:
            s = getattr(getattr(self, "veri", None), "settings", {}) or {}
            # temizle
            try:
                self._menu_print_prod.delete(0, "end")
            except Exception:
                pass
            try:
                self._menu_print_box.delete(0, "end")
            except Exception:
                pass

            # Ürün yazdır
            prod_ip = str(s.get("prod_ip", "") or "").strip()
            prod2_ip = str(s.get("prod2_ip", "") or "").strip()
            if prod_ip:
                self._menu_print_prod.add_command(label="Zebra ZT411 (Ürün)", command=lambda: self._print_selected("prod"))
            else:
                self._menu_print_prod.add_command(label="Zebra ZT411 (Ürün)  (IP yok)", state="disabled")
            if prod2_ip:
                self._menu_print_prod.add_command(label="Zebra ZT411-2 (Yedek)", command=lambda: self._print_selected("prod2"))
            else:
                self._menu_print_prod.add_command(label="Zebra ZT411-2 (Yedek)  (IP yok)", state="disabled")

            # Box etiketi yazdır
            box_ip = str(s.get("box_ip", "") or "").strip()
            if box_ip:
                self._menu_print_box.add_command(label="Zebra ZD230 (Koli)", command=lambda: self._print_selected("box"))
            else:
                self._menu_print_box.add_command(label="Zebra ZD230 (Koli)  (IP yok)", state="disabled")
        except Exception:
            pass

    def show_context_menu(self, event):
        """Ana tabloda sağ tık menüsünü açar."""
        try:
            iid = self.tree.identify_row(event.y)
            if iid:
                self.tree.selection_set(iid)
            try:
                self._refresh_print_menus()
            except Exception:
                pass
            self.context_menu.post(event.x_root, event.y_root)
        except Exception:
            pass

    def copy_product_code(self):
        """Seçili satırın Barkod değerini panoya kopyalar."""
        code = self._get_selected_barcode()
        if not code:
            try:
                from tkinter import messagebox
                messagebox.showinfo("Kopyala", "Lütfen tablodan bir satır seçin (Barkod).")
            except Exception:
                pass
            return
        try:
            self.root.clipboard_clear()
            self.root.clipboard_append(code)
            self.root.update()
        except Exception:
            pass

    def copy_box_code(self):
        """Seçili satırın Koli Etiketi değerini panoya kopyalar."""
        code = self._get_selected_box_label()
        if not code:
            try:
                from tkinter import messagebox
                messagebox.showinfo("Kopyala", "Lütfen tablodan bir satır seçin (Koli Etiketi).")
            except Exception:
                pass
            return
        try:
            self.root.clipboard_clear()
            self.root.clipboard_append(code)
            self.root.update()
        except Exception:
            pass

    def show_selected_details(self):
        """Seçili satırdaki tüm kolonları daha okunabilir biçimde gösterir."""
        try:
            sel = self.tree.selection()
            if not sel:
                messagebox.showinfo("Detay", "Lütfen tablodan bir satır seçin.")
                return
            iid = sel[0]
            vals = self.tree.item(iid, 'values') or []
            cols = list(self.tree['columns'])
            items = []
            for i, col in enumerate(cols):
                val = vals[i] if i < len(vals) else ''
                items.append((str(col), str(val)))

            top = tk.Toplevel(self.root)
            top.title("Detaylar")
            top.geometry("760x460")
            top.minsize(640, 360)
            try:
                top.transient(self.root)
                top.grab_set()
            except Exception:
                pass

            nb = ttk.Notebook(top)
            nb.pack(fill="both", expand=True, padx=10, pady=10)

            # TAB 1: kart görünüm
            t1 = ttk.Frame(nb)
            nb.add(t1, text="Görünüm")

            # scroll
            canvas = tk.Canvas(t1, highlightthickness=0)
            vs = ttk.Scrollbar(t1, orient="vertical", command=canvas.yview)
            canvas.configure(yscrollcommand=vs.set)
            vs.pack(side="right", fill="y")
            canvas.pack(side="left", fill="both", expand=True)

            inner = ttk.Frame(canvas)
            canvas.create_window((0, 0), window=inner, anchor="nw")

            def _on_config(_e=None):
                try:
                    canvas.configure(scrollregion=canvas.bbox("all"))
                except Exception:
                    pass
            inner.bind("<Configure>", _on_config)

            for r, (k, v) in enumerate(items):
                ttk.Label(inner, text=k, width=16).grid(row=r, column=0, sticky="w", padx=(6, 6), pady=4)
                e = ttk.Entry(inner)
                e.grid(row=r, column=1, sticky="ew", padx=(0, 6), pady=4)
                e.insert(0, v)
                e.configure(state="readonly")

                def _mkcopy(val=v):
                    def _copy():
                        try:
                            self.root.clipboard_clear()
                            self.root.clipboard_append(val)
                            self.root.update()
                        except Exception:
                            pass
                    return _copy

                ttk.Button(inner, text="Kopyala", command=_mkcopy()).grid(row=r, column=2, padx=(0, 6), pady=4)

            inner.columnconfigure(1, weight=1)

            # TAB 2: ham metin
            t2 = ttk.Frame(nb)
            nb.add(t2, text="Ham")
            txt = tk.Text(t2, wrap="word")
            txt.pack(fill="both", expand=True)
            txt.insert("1.0", "\n".join([f"{k}: {v}" for k, v in items]))
            txt.configure(state="disabled")

            # alt butonlar
            btns = ttk.Frame(top)
            btns.pack(fill="x", padx=10, pady=(0, 10))

            def _copy_all():
                try:
                    raw = "\n".join([f"{k}: {v}" for k, v in items])
                    self.root.clipboard_clear()
                    self.root.clipboard_append(raw)
                    self.root.update()
                except Exception:
                    pass

            ttk.Button(btns, text="Hepsini Kopyala", command=_copy_all).pack(side="left")
            ttk.Button(btns, text="Kapat", command=top.destroy).pack(side="right")
        except Exception:
            try:
                messagebox.showinfo("Detay", "Detay penceresi açılamadı.")
            except Exception:
                pass


    def show_selected_datamatrix(self):
        """Seçili barkod/etiket için görsel karekod üretip gösterir.

        Öncelik:
        1) DataMatrix (treepoem + pillow varsa)
        2) QR fallback (segno ile - pillow gerektirmez)
        """
        code_prod = self._get_selected_barcode()
        code_box = self._get_selected_box_label()
        if not code_prod and not code_box:
            try:
                messagebox.showinfo("Karekod", "Lütfen tablodan bir satır seçin.")
            except Exception:
                pass
            return

        tmp_files: list[str] = []

        def _render(code: str, scale: int = 5):
            # 1) DataMatrix (treepoem)
            try:
                import treepoem
                from PIL import ImageTk

                img = treepoem.generate_barcode(barcode_type="datamatrix", data=code)
                try:
                    w, h = img.size
                    img = img.resize((w * 3, h * 3))
                except Exception:
                    pass
                return ImageTk.PhotoImage(img), "DataMatrix"
            except Exception:
                pass

            # 2) QR fallback (segno) -> PPM -> PhotoImage
            try:
                import segno
                import tempfile

                qr = segno.make(code, error="M")
                m = qr.matrix
                border = 2
                mh = len(m)
                mw = len(m[0]) if mh else 0
                W = (mw + 2 * border) * scale
                H = (mh + 2 * border) * scale

                path = tempfile.mkstemp(suffix=".ppm")[1]
                tmp_files.append(path)

                white = b"\xff\xff\xff"
                black = b"\x00\x00\x00"
                with open(path, "wb") as f:
                    f.write(f"P6 {W} {H} 255\n".encode("ascii"))
                    # y: -border..mh+border-1
                    for y in range(-border, mh + border):
                        # build one scaled row
                        row_bytes = bytearray()
                        for x in range(-border, mw + border):
                            val = 0
                            if 0 <= y < mh and 0 <= x < mw:
                                val = 1 if m[y][x] else 0
                            # QR: True=dark
                            pix = black if val else white
                            row_bytes.extend(pix * scale)
                        # duplicate row scale times
                        row = bytes(row_bytes)
                        for _ in range(scale):
                            f.write(row)

                return tk.PhotoImage(file=path), "QR (fallback)"
            except Exception:
                return None, None

        top = tk.Toplevel(self.root)
        top.title("Karekod Göster")
        top.geometry("560x520")
        try:
            top.transient(self.root)
            top.grab_set()
        except Exception:
            pass

        def _cleanup_and_close():
            try:
                for p in tmp_files:
                    try:
                        os.remove(p)
                    except Exception:
                        pass
            finally:
                try:
                    top.destroy()
                except Exception:
                    pass

        try:
            top.protocol("WM_DELETE_WINDOW", _cleanup_and_close)
        except Exception:
            pass

        nb = ttk.Notebook(top)
        nb.pack(fill="both", expand=True, padx=10, pady=10)

        def _tab(title: str, code: str):
            f = ttk.Frame(nb)
            nb.add(f, text=title)

            img, kind = _render(code)
            if img is None:
                lbl = ttk.Label(
                    f,
                    text="Görsel karekod üretilemedi.\n\n"
                         "İpucu: 'pip install segno' ile QR fallback aktif olur.\n"
                         "DataMatrix için ayrıca 'treepoem' + 'pillow' kurulabilir.\n\nKod:\n" + code
                )
                lbl.pack(fill="x", pady=12)
            else:
                canvas = tk.Label(f, image=img)
                canvas.image = img
                canvas.pack(pady=(10, 6))
                if kind and kind != "DataMatrix":
                    ttk.Label(f, text=f"Not: {kind} gösteriliyor (DataMatrix modülü yok).").pack()
                ttk.Label(f, text=code).pack(fill="x", padx=10)

            def _copy():
                try:
                    self.root.clipboard_clear()
                    self.root.clipboard_append(code)
                    self.root.update()
                except Exception:
                    pass

            ttk.Button(f, text="Kopyala", command=_copy).pack(pady=10)
            return f

        if code_prod:
            _tab("Ürün Barkodu", code_prod)
        if code_box:
            _tab("Koli Etiketi", code_box)

        ttk.Button(top, text="Kapat", command=_cleanup_and_close).pack(pady=(0, 10))


    def show_selected_code(self):
        """Seçili satırın Barkod/Koli Etiketini popup pencerede gösterir."""
        try:
            import tkinter as tk
            from tkinter import ttk, messagebox
        except Exception:
            return

        barkod = self._get_selected_barcode() or ""
        box = self._get_selected_box_label() or ""

        if not barkod and not box:
            try:
                messagebox.showwarning("Bilgi", "Lütfen tablodan bir satır seçin.")
            except Exception:
                pass
            return

        w = tk.Toplevel(self.root)
        w.title("KODU görüntüle")
        w.resizable(False, False)
        try:
            w.transient(self.root)
            w.grab_set()
        except Exception:
            pass

        frm = ttk.Frame(w, padding=12)
        frm.pack(fill="both", expand=True)

        def _row(title, value):
            ttk.Label(frm, text=title).pack(anchor="w")
            t = tk.Text(frm, height=2, width=72, wrap="word")
            t.pack(fill="x", expand=True, pady=(4, 10))
            t.insert("1.0", value or "")
            t.configure(state="disabled")
            btns = ttk.Frame(frm)
            btns.pack(fill="x", pady=(0, 10))

            def _copy():
                try:
                    w.clipboard_clear()
                    w.clipboard_append(value or "")
                    w.update()
                except Exception:
                    pass

            ttk.Button(btns, text="Kopyala", command=_copy).pack(side="left")
            return _copy

        copy_barkod = _row("ÜRÜN (Barkod):", barkod) if barkod else None
        copy_box = _row("BOX (Koli Etiketi):", box) if box else None

        bottom = ttk.Frame(frm)
        bottom.pack(fill="x")
        ttk.Button(bottom, text="Kapat", command=w.destroy).pack(side="right")

        # Varsayılan: barkod varsa onu kopyala, yoksa box'ı kopyala
        try:
            if copy_barkod:
                copy_barkod()
            elif copy_box:
                copy_box()
        except Exception:
            pass

    def show_selected_qr(self):
        """Üstteki RUS QR butonu: seçili satır kodunu göster (mevcut projede QR çizimi yoksa metin gösterir)."""
        # Bu sürümde QR render kütüphanesi olmadığı için güvenli davranış:
        # Kodları popup'ta gösterip kopyalama sunuyoruz.
        return self.show_selected_code()

    def print_selected_product(self):
        return self._print_selected('prod')

    def print_selected_box(self):
        return self._print_selected('box')

    def _print_selected(self, target: str):
        """Seçili barkodu hedef yazıcıya yollar (socket)."""
        # Ürün yazdır -> Barkod, Box etiketi yazdır -> Koli Etiketi
        code = self._get_selected_box_label() if target == 'box' else self._get_selected_barcode()
        if not code:
            try:
                from tkinter import messagebox
                msg = 'Lütfen tablodan bir satır seçin (Koli Etiketi).' if target == 'box' else 'Lütfen tablodan bir satır seçin (Barkod).'
                messagebox.showinfo('Yazdır', msg)
            except Exception:
                pass
            return
        try:
            # Donanım servisleri üzerinden yazdır
            if hasattr(self, 'donanim') and hasattr(self.donanim, 'print_label'):
                self.donanim.print_label(code, 'box' if target=='box' else 'prod', target_printer=target)
                return
        except Exception as ex:
            try:
                from tkinter import messagebox
                messagebox.showerror('Yazdır', f'Yazdırma hatası: {ex}')
            except Exception:
                pass

    def _create_stat_card(self, parent, title, val, bg="white", fg="black"):
        """İstatistik kartı oluşturur.
        NOT: Bu fonksiyon (frame, value_label) döndürür. Yerleşim grid/pack çağıran tarafta yapılır.
        """
        frame = tk.Frame(parent, bg=bg, borderwidth=1, relief="solid")
        tk.Label(frame, text=title, font=("Segoe UI", 7), bg=bg, fg="#666").pack(pady=(3, 0))
        lbl = tk.Label(frame, text=val, font=("Segoe UI", 13, "bold"), bg=bg, fg=fg)
        lbl.pack(pady=(0, 3))
        return frame, lbl

    def _create_box_status_panel(self, parent):
        """Tek panel içinde bölünmüş KOLİ DURUMU kutusu.

        Üst satır: ŞU AN / SIRADAKİ / TAMAM / KALAN / HEDEF
        Alt satır: KOLİ İÇİ x/y + progress bar + durum etiketi
        """
        frame = tk.Frame(parent, bg="#eef2ff", borderwidth=1, relief="solid")
        frame.pack(side="left", fill="x", expand=True, padx=5, pady=5)

        header = tk.Frame(frame, bg="#eef2ff")
        header.pack(fill="x", padx=8, pady=(6, 0))
        tk.Label(header, text="KOLİ DURUMU", font=("Segoe UI", 8, "bold"), bg="#eef2ff", fg="#334").pack(side="left")
        self.lbl_box_status = tk.Label(header, text="HAZIR", font=("Segoe UI", 8, "bold"), bg="#eef2ff", fg="#0d6efd")
        self.lbl_box_status.pack(side="right")

        top = tk.Frame(frame, bg="#eef2ff")
        top.pack(fill="x", padx=8, pady=(2, 2))

        def _mini(parent, title, init):
            c = tk.Frame(parent, bg="#eef2ff")
            c.pack(side="left", expand=True, fill="x")
            tk.Label(c, text=title, font=("Segoe UI", 7), bg="#eef2ff", fg="#666").pack()
            v = tk.Label(c, text=init, font=("Segoe UI", 12, "bold"), bg="#eef2ff", fg="#111")
            v.pack(pady=(0, 2))
            return v

        self.lbl_box_now = _mini(top, "ŞU AN", "0")
        self.lbl_box_next = _mini(top, "SIRADAKİ", "1")
        self.lbl_box_done = _mini(top, "TAMAM", "0")
        self.lbl_box_left = _mini(top, "KALAN", "0")
        self.lbl_box_goal = _mini(top, "HEDEF", "-")

        bottom = tk.Frame(frame, bg="#eef2ff")
        bottom.pack(fill="x", padx=8, pady=(0, 6))

        self.lbl_box_inbox = tk.Label(bottom, text="KOLİ İÇİ: 0/0", font=("Segoe UI", 9, "bold"), bg="#eef2ff", fg="#111")
        self.lbl_box_inbox.pack(side="left")

        self.pb_box = ttk.Progressbar(bottom, orient="horizontal", mode="determinate", length=140)
        self.pb_box.pack(side="left", padx=10, fill="x", expand=True)
        self.lbl_box_percent = tk.Label(bottom, text="0%", font=("Segoe UI", 9, "bold"), bg="#eef2ff", fg="#111")
        self.lbl_box_percent.pack(side="right")

        return frame

    def toggle_menu(self, event=None):
        """MENÜ popup'unu açar."""
        try:
            w = getattr(self, 'menu_btn', None)
            if not w:
                return
            x = w.winfo_rootx()
            y = w.winfo_rooty() + w.winfo_height()
            self._popup_menu.tk_popup(x, y)
        finally:
            try:
                self._popup_menu.grab_release()
            except Exception:
                pass
    
    # ---------------- Search Window ----------------
    def open_search_window(self):
        try:
            arama_penceresi.open_arama_penceresi(self)
        except Exception as ex:
            from tkinter import messagebox
            messagebox.showerror("Hata", f"Arama penceresi açılamadı: {ex}")
    
    # ---------------- Menü / Popup Aksiyonları (Wrapper) ----------------
    def open_settings(self):
        """MENÜ -> Ayarlar"""
        try:
            # YetkiliPaneli üzerinden ayarlar penceresi (mevcut mimari)
            if hasattr(self, "yetkili") and hasattr(self.yetkili, "open_ayarlar_penceresi"):
                self.yetkili.open_ayarlar_penceresi()
                return
            if hasattr(self, "yetkili") and hasattr(self.yetkili, "open_settings_window"):
                self.yetkili.open_settings_window()
                return
        except Exception as e:
            import traceback
            print("[HATA] open_settings:", e)
            traceback.print_exc()
        try:
            from tkinter import messagebox
            messagebox.showerror("Hata", "Ayarlar penceresi açılamadı.")
        except Exception:
            pass

    def open_admin_panel(self):
        """MENÜ -> Yönetici"""
        try:
            if hasattr(self, "yetkili") and hasattr(self.yetkili, "open_yonetici_paneli"):
                self.yetkili.open_yonetici_paneli()
                return
        except Exception as e:
            import traceback
            print("[HATA] open_admin_panel:", e)
            traceback.print_exc()
        try:
            from tkinter import messagebox
            messagebox.showerror("Hata", "Yönetici paneli açılamadı.")
        except Exception:
            pass

    def open_on_hazirlik(self):
        """MENÜ -> Ön Hazırlık"""
        try:
            import tkinter as tk
            from on_hazirlik import ZebraApp
            top = tk.Toplevel(self.root)
            top.transient(self.root)
            top.grab_set()
            ZebraApp(top)
            return
        except Exception as e:
            import traceback
            print("[HATA] open_on_hazirlik:", e)
            traceback.print_exc()
        try:
            from tkinter import messagebox
            messagebox.showerror("Hata", "Ön Hazırlık penceresi açılamadı.")
        except Exception:
            pass

    def on_exit(self):
        """MENÜ -> Çıkış"""
        try:
            if hasattr(self, "veri") and hasattr(self.veri, "save_settings"):
                self.veri.save_settings()
        except Exception:
            pass
        try:
            self.root.quit()
        except Exception:
            pass
        try:
            self.root.destroy()
        except Exception:
            pass
# ---------------- Settings wrappers ----------------
    def _on_short_code_changed(self):
        self.veri.settings["short_code"] = int(self.var_short_code.get())
        self.veri.save_settings()
    def _on_reject_toggle(self):
        """REJECT checkbox değişince donanım tetiklemeyi aç/kapat."""
        enabled = bool(self.var_reject_enabled.get())
        try:
            self.donanim.reject_user_enabled = enabled
        except Exception:
            pass
        # UI güncelle
        try:
            self.update_ui()
        except Exception:
            pass
    def _on_printer_toggle(self):
        """Yazıcı Aktif/Pasif kutusu değişince ayarı kaydet ve UI'yi güncelle."""
        try:
            # Veri yönetimi ayarlarını güncelle
            self.veri.settings["printer_enabled"] = int(self.var_printer_enabled.get())
            self.veri.save_settings()
        except Exception:
            # Ayarlar kaydı başarısız olsa bile uygulama çalışmaya devam etsin
            pass
        try:
            self.update_ui()
        except Exception:
            pass



    # ---------------- Hardware status buttons ----------------
    def set_device_state(self, name: str, state: str):
        """Üst şeritteki durum butonlarının sadece rengini günceller.
        state: connected | searching | disconnected | refresh | disabled
        """
        btn_map = {
            'scanner': getattr(self, 'btn_scanner_status', None),
            'reject': getattr(self, 'btn_reject_status', None),
            'box': getattr(self, 'btn_zd230', None),
            'prod': getattr(self, 'btn_zt411_01', None),
            'prod2': getattr(self, 'btn_zt411_02', None),
        }
        btn = btn_map.get(name)
        if not btn:
            return
        color = getattr(self, '_hw_colors', {}).get(state, '#7f8c8d')
        try:
            btn.configure(bg=color)
        except Exception:
            pass

    def refresh_device(self, name: str):
        """Cift tik ile yenileme: mavi 1.2sn, sonra ilgili kontrol."""
        # mavi yak
        try:
            self.set_device_state(name, 'refresh')
        except Exception:
            pass

        def _do_refresh():
            try:
                if name == 'scanner':
                    # Scanner thread zaten döngüde; sadece yeniden başlatmayı tetikle
                    try:
                        self.donanim.stop_threads = True
                    except Exception:
                        pass
                    try:
                        self.donanim.stop_threads = False
                        self.donanim.start_scanner_listener()
                    except Exception:
                        pass
                elif name == 'reject':
                    try:
                        self.donanim.init_rejector()
                    except Exception:
                        pass
                    try:
                        self.update_ui()
                    except Exception:
                        pass
                elif name in ('box', 'prod', 'prod2'):
                    # yazıcı socket ping
                    try:
                        self._kick_printer_checks()
                    except Exception:
                        pass
                else:
                    try:
                        self.update_ui()
                    except Exception:
                        pass
            finally:
                # 1.2 sn sonra gerçek duruma dönmesi için güncelle döngüsü
                try:
                    self.update_ui()
                except Exception:
                    pass

        try:
            self.root.after(1200, _do_refresh)
        except Exception:
            _do_refresh()


    # ---------------- Dizayn / Tema / Font / Yerleşim ----------------
    def apply_design_from_settings(self):
        """Ayar dosyasındaki UI seçeneklerini uygular."""
        try:
            s = getattr(getattr(self, "veri", None), "settings", {}) or {}
            theme = str(s.get("ui_theme", "light") or "light").lower().strip()
            fam = str(s.get("ui_font_family", "Segoe UI") or "Segoe UI")
            size = int(s.get("ui_font_size", 9) or 9)
            layout = str(s.get("ui_dashboard_layout", "A") or "A").upper().strip()
            self.apply_ui_theme(theme)
            self.apply_ui_font(fam, size)
            self.set_dashboard_layout(layout, persist=False)
            # bölme konumları
            try:
                self.restore_layout_sashes()
            except Exception:
                pass
        except Exception:
            pass

    def apply_ui_font(self, family: str, size: int):
        """Global fontu günceller (Tk named fonts)."""
        try:
            size = max(8, min(18, int(size)))
        except Exception:
            size = 9
        family = family or "Segoe UI"
        try:
            for name in ("TkDefaultFont", "TkTextFont", "TkMenuFont", "TkHeadingFont"):
                try:
                    f = tkfont.nametofont(name)
                    f.configure(family=family, size=size)
                except Exception:
                    continue
        except Exception:
            pass
        try:
            # Treeview heading font biraz daha belirgin olsun
            self.style.configure("Treeview.Heading", font=(family, size, "bold"))
            self.style.configure("Treeview", font=(family, size))
        except Exception:
            pass

    def apply_ui_theme(self, mode: str):
        """Aydınlık/Karanlık tema uygular."""
        mode = (mode or "light").lower().strip()
        is_dark = (mode == "dark")

        # temel renkler
        bg = "#12161a" if is_dark else "#f2f2f2"
        fg = "#e5e7eb" if is_dark else "#111111"
        panel = "#171c21" if is_dark else "#f2f2f2"
        field = "#0f1317" if is_dark else "#ffffff"
        border = "#2b3440" if is_dark else "#d0d0d0"

        try:
            self.root.configure(bg=bg)
        except Exception:
            pass

        # tk frame/bg güncelle (komut barını dokunma)
        try:
            for w in [getattr(self, "main_frame", None), getattr(self, "content_frame", None),
                      getattr(self, "_upload_left", None), getattr(self, "_upload_right", None),
                      getattr(self, "_files_left", None), getattr(self, "_files_right", None),
                      getattr(self, "_bottom_left", None), getattr(self, "_bottom_right", None)]:
                if w is not None:
                    try:
                        w.configure(bg=panel)
                    except Exception:
                        pass
        except Exception:
            pass
        # LabelFrame arka planları
        try:
            for w in [getattr(self, "prev_box", None), getattr(self, "next_box", None), getattr(self, "scan_report_frame", None)]:
                if w is not None:
                    try:
                        w.configure(bg=panel, fg=fg)
                    except Exception:
                        pass
        except Exception:
            pass

        # ttk stilleri
        try:
            self.style.configure("TFrame", background=panel)
            self.style.configure("TLabel", background=panel, foreground=fg)
            self.style.configure("TLabelframe", background=panel, foreground=fg)
            self.style.configure("TLabelframe.Label", background=panel, foreground=fg)
        except Exception:
            pass

        try:
            self.style.configure(
                "Treeview",
                background=field,
                fieldbackground=field,
                foreground=fg,
                bordercolor=border,
                rowheight=22,
            )
            self.style.map("Treeview", background=[("selected", "#2563eb")], foreground=[("selected", "#ffffff")])
            self.style.configure("Treeview.Heading", background=panel, foreground=fg, bordercolor=border)
        except Exception:
            pass

        # bazı tk widget'ları
        try:
            if hasattr(self, "entry_koli_adet"):
                self.entry_koli_adet.configure(bg=field, fg=fg, insertbackground=fg)
        except Exception:
            pass

        # dashboard renkleri
        try:
            self._apply_dashboard_colors(is_dark)
        except Exception:
            pass

    def _set_bg_recursive(self, widget, bg: str):
        try:
            widget.configure(bg=bg)
        except Exception:
            pass
        try:
            for ch in widget.winfo_children():
                self._set_bg_recursive(ch, bg)
        except Exception:
            pass

    def _apply_dashboard_colors(self, is_dark: bool):
        """Dashboard panelinin (Scanner Raporu yanındaki) renklerini ayarlar."""
        s = getattr(getattr(self, "veri", None), "settings", {}) or {}
        mode = str(s.get("ui_dashboard_bg", "auto") or "auto").lower().strip()
        if mode == "auto":
            mode = "dark" if is_dark else "light"

        if mode == "dark":
            bg = "#0b0f14"
            txt_primary = "#e5e7eb"
            txt_secondary = "#9ca3af"
            ring_bg = "#1f2937"
            status_fg = "#22c55e"
            eta_fg = "#60a5fa"
            kalan_fg = "#f59e0b"
        elif mode == "gray":
            bg = "#e5e7eb"
            txt_primary = "#111111"
            txt_secondary = "#374151"
            ring_bg = "#9ca3af"
            status_fg = "#198754"
            eta_fg = "#1d4ed8"
            kalan_fg = "#b45309"
        else:  # light
            bg = "#ffffff"
            txt_primary = "#111111"
            txt_secondary = "#4b5563"
            ring_bg = "#cbd5e1"
            status_fg = "#198754"
            eta_fg = "#1d4ed8"
            kalan_fg = "#b45309"

        # gauge çizim renkleri için
        self._dash_bg = bg
        self._dash_text_primary = txt_primary
        self._dash_text_secondary = txt_secondary
        self._dash_ring_bg = ring_bg

        try:
            if hasattr(self, "_dash_stack") and self._dash_stack:
                self._set_bg_recursive(self._dash_stack, bg)
        except Exception:
            pass

        try:
            if hasattr(self, "_dash_variants") and self._dash_variants:
                for v in self._dash_variants.values():
                    try:
                        v["lbl_status"].configure(bg=bg, fg=status_fg)
                    except Exception:
                        pass
                    try:
                        v["lbl_eta"].configure(bg=bg, fg=eta_fg)
                    except Exception:
                        pass
                    try:
                        v["lbl_count"].configure(bg=bg, fg=kalan_fg)
                    except Exception:
                        pass
                    try:
                        v["canvas_fill"].configure(bg=bg)
                        v["canvas_speed"].configure(bg=bg)
                    except Exception:
                        pass
        except Exception:
            pass

    def _save_layout_sashes(self):
        """PanedWindow sash konumlarını kaydeder."""
        try:
            s = getattr(getattr(self, "veri", None), "settings", {}) or {}
            # upload
            try:
                s["sash_upload"] = int(self.upload_row.sashpos(0))
            except Exception:
                pass
            # files
            try:
                s["sash_files"] = int(self.files_row.sashpos(0))
            except Exception:
                pass
            # bottom
            try:
                s["sash_bottom"] = int(self.bottom_pane.sashpos(0))
            except Exception:
                pass
            # summary (Sistem/Ürün/Box/Palet)
            try:
                if hasattr(self, "summary_pane") and self.summary_pane:
                    s["sash_summary"] = [int(self.summary_pane.sashpos(i)) for i in range(3)]
            except Exception:
                pass
            try:
                self.veri.save_settings()
            except Exception:
                pass
        except Exception:
            pass

    def restore_layout_sashes(self):
        """Kaydedilmiş sash konumlarını uygular (widget'lar çizildikten sonra)."""
        try:
            s = getattr(getattr(self, "veri", None), "settings", {}) or {}

            def _apply():
                # upload
                try:
                    pos = int(s.get("sash_upload", 0) or 0)
                    if pos > 0:
                        self.upload_row.sashpos(0, pos)
                except Exception:
                    pass
                # files
                try:
                    pos = int(s.get("sash_files", 0) or 0)
                    if pos > 0:
                        self.files_row.sashpos(0, pos)
                except Exception:
                    pass
                # bottom
                try:
                    pos = int(s.get("sash_bottom", 0) or 0)
                    if pos > 0:
                        self.bottom_pane.sashpos(0, pos)
                except Exception:
                    pass

                # summary
                try:
                    poses = s.get("sash_summary", None)
                    if isinstance(poses, (list, tuple)) and hasattr(self, "summary_pane") and self.summary_pane:
                        for i, p in enumerate(poses[:3]):
                            try:
                                p = int(p or 0)
                                if p > 0:
                                    self.summary_pane.sashpos(i, p)
                            except Exception:
                                pass
                except Exception:
                    pass
            self.root.after(120, _apply)
        except Exception:
            pass

    def _build_dashboard_variants(self, parent: tk.Widget):
        """Dashboard panelini hem A hem B varyantı olarak oluşturur."""
        # Stack container
        self._dash_stack = tk.Frame(parent, bg="#0b0f14")
        self._dash_stack.pack(fill="both", expand=True)
        self._dash_stack.rowconfigure(0, weight=1)
        self._dash_stack.columnconfigure(0, weight=1)

        def _make(variant: str):
            frame = tk.Frame(self._dash_stack, bg="#0b0f14")
            frame.grid(row=0, column=0, sticky="nsew")

            # Üst: durum
            lbl_status = tk.Label(frame, text="SİSTEM HAZIR", bg="#0b0f14", fg="#22c55e", font=("Segoe UI", 10, "bold"))
            lbl_status.pack(anchor="w", padx=10, pady=(10, 6))

            # Orta: ETA / Kalan
            if variant == "A":
                fnt_eta = ("Segoe UI", 11, "bold")
                fnt_kalan = ("Segoe UI", 10, "bold")
                gauge = 72
            else:
                fnt_eta = ("Segoe UI", 10, "bold")
                fnt_kalan = ("Segoe UI", 9, "bold")
                gauge = 56

            lbl_eta = tk.Label(frame, text="TAHMİNİ BİTİŞ: --:--", bg="#0b0f14", fg="#60a5fa", font=fnt_eta)
            lbl_eta.pack(anchor="center", pady=(0, 2))
            lbl_count = tk.Label(frame, text="KALAN: --:--:--", bg="#0b0f14", fg="#f59e0b", font=fnt_kalan)
            lbl_count.pack(anchor="center", pady=(0, 8))

            # Alt: gauge'lar
            g_row = tk.Frame(frame, bg="#0b0f14")
            g_row.pack(fill="x", pady=(0, 10))

            if variant == "A":
                # Dikey: alt alta
                c1 = tk.Canvas(g_row, width=gauge, height=gauge, bg="#0b0f14", highlightthickness=0)
                c2 = tk.Canvas(g_row, width=gauge, height=gauge, bg="#0b0f14", highlightthickness=0)
                c1.pack(side="top", pady=(0, 6))
                c2.pack(side="top")
            else:
                # Kompakt: yan yana
                c1 = tk.Canvas(g_row, width=gauge, height=gauge, bg="#0b0f14", highlightthickness=0)
                c2 = tk.Canvas(g_row, width=gauge, height=gauge, bg="#0b0f14", highlightthickness=0)
                c1.pack(side="left", padx=8)
                c2.pack(side="left")

            return frame, {
                "frame": frame,
                "lbl_status": lbl_status,
                "lbl_eta": lbl_eta,
                "lbl_count": lbl_count,
                "canvas_fill": c1,
                "canvas_speed": c2,
            }

        self._dash_variants = {
            "A": _make("A")[1],
            "B": _make("B")[1],
        }
        # frame refleri sözlükte var
        self._dash_variants["A"]["frame"].tkraise()

    def set_dashboard_layout(self, mode: str, persist: bool = True):
        """Dashboard A/B düzenini değiştirir."""
        try:
            mode = str(mode or "A").upper().strip()
            if mode not in ("A", "B"):
                mode = "A"
            if not hasattr(self, "_dash_variants") or not self._dash_variants:
                return
            # aktif frame
            self._dash_variants[mode]["frame"].tkraise()
            # aktif widget referansları
            self.lbl_dash_status = self._dash_variants[mode]["lbl_status"]
            self.lbl_eta = self._dash_variants[mode]["lbl_eta"]
            self.lbl_countdown = self._dash_variants[mode]["lbl_count"]
            self.canvas_fill = self._dash_variants[mode]["canvas_fill"]
            self.canvas_speed = self._dash_variants[mode]["canvas_speed"]

            # gauge loop başlat
            if not getattr(self, "_gauges_started", False):
                self._gauges_started = True
                try:
                    self._draw_gauges()
                except Exception:
                    pass

            if persist:
                try:
                    self.veri.settings["ui_dashboard_layout"] = mode
                    self.veri.save_settings()
                except Exception:
                    pass
        except Exception:
            pass


    # ---------------- Dashboard gauges ----------------
    def _ring_color(self, frac: float) -> str:
        """Mavi -> Yeşil -> Kırmızı geçiş (basit eşik)."""
        if frac < 0.45:
            return '#60a5fa'  # mavi
        if frac < 0.8:
            return '#22c55e'  # yeşil
        return '#ef4444'      # kırmızı

    def _draw_ring(self, canvas: tk.Canvas, frac: float, label: str):
        try:
            canvas.delete('all')
            w = int(canvas.cget('width'))
            h = int(canvas.cget('height'))
            pad = 8
            x0, y0, x1, y1 = pad, pad, w - pad, h - pad

            ring_bg = getattr(self, "_dash_ring_bg", "#1f2937")
            txt_primary = getattr(self, "_dash_text_primary", "#e5e7eb")
            txt_secondary = getattr(self, "_dash_text_secondary", "#9ca3af")

            # arka halka
            canvas.create_oval(x0, y0, x1, y1, outline=ring_bg, width=8)
            # değer halkası
            frac = max(0.0, min(1.0, float(frac)))
            extent = -360 * frac
            canvas.create_arc(x0, y0, x1, y1, start=90, extent=extent, style='arc',
                              outline=self._ring_color(frac), width=8)

            # merkez yazılar
            pct = int(round(frac * 100))
            canvas.create_text(w/2, h/2-6, text=f'{pct}%', fill=txt_primary, font=('Segoe UI', 9, 'bold'))
            canvas.create_text(w/2, h/2+12, text=label, fill=txt_secondary, font=('Segoe UI', 7, 'bold'))
        except Exception:
            pass

    def _draw_gauges(self):
        """Gauge animasyonu: hedefe doğru yumuşak geçiş."""
        try:
            # easing
            self._g_fill_val += (self._g_fill_target - self._g_fill_val) * 0.22
            self._g_speed_val += (self._g_speed_target - self._g_speed_val) * 0.22

            self._draw_ring(self.canvas_fill, self._g_fill_val, 'KOLI')
            self._draw_ring(self.canvas_speed, self._g_speed_val, 'HIZ')
        except Exception:
            pass
        try:
            self.root.after(50, self._draw_gauges)
        except Exception:
            pass

    def _update_speed_gauge(self):
        """Son 60 sn içindeki okutma sayısına göre dakika hızı."""
        try:
            now = time.time()
            # eski kayıtları temizle
            while self._scan_times and (now - self._scan_times[0]) > 60:
                self._scan_times.popleft()
            spm = len(self._scan_times)  # son 60 sn = /dk
            # 0..60+ -> 0..1 normalize (60/dk üstü 1'e sabitle)
            self._g_speed_target = max(0.0, min(1.0, spm / 60.0))
        except Exception:
            pass

    def _update_eta(self):
        """Basit ETA: (kalan / hız)"""
        try:
            now = time.time()
            if (now - float(getattr(self, '_last_eta_update', 0.0))) < 1.0:
                return
            self._last_eta_update = now

            total = int(len(getattr(self, 'work_list', []) or []))
            done = int(getattr(self, 'verified_count', 0) or 0)
            remaining = max(0, total - done)

            # hız (son 60 sn)
            if self._scan_times:
                rate_per_min = len(self._scan_times)
            else:
                rate_per_min = 0
            if rate_per_min <= 0:
                self.lbl_eta.config(text='TAHMİNİ BİTİŞ: --:--')
                self.lbl_countdown.config(text='KALAN: --:--:--')
                return

            minutes_left = remaining / max(1, rate_per_min)
            sec_left = int(round(minutes_left * 60))
            eta_dt = datetime.fromtimestamp(now + sec_left)
            self.lbl_eta.config(text=f'TAHMİNİ BİTİŞ: {eta_dt.strftime("%H:%M")}')
            hh = sec_left // 3600
            mm = (sec_left % 3600) // 60
            ss = sec_left % 60
            self.lbl_countdown.config(text=f'KALAN: {hh:02d}:{mm:02d}:{ss:02d}')
        except Exception:
            pass
    def _sync_date_ui(self):
        required = bool(self.var_date_required.get())
        if required:
            self.entry_date.configure(state="normal")
        else:
            self.entry_date.configure(state="disabled")
    def apply_tree_settings(self):
        """TreeView sütun görünürlüğü ayarını uygular."""
        self.apply_table_columns()
        self.auto_fit_columns()
    def auto_fit_columns(self):
        """TreeView sütunlarını içeriğe göre otomatik genişletir."""
        try:
            font = tkfont.nametofont("TkDefaultFont")
        except Exception:
            font = tkfont.Font(family="Segoe UI", size=9)
        for col in self.tree["columns"]:
            maxw = font.measure(col) + 24
            for iid in self.tree.get_children():
                txt = str(self.tree.set(iid, col))
                if txt:
                    w = font.measure(txt) + 24
                    if w > maxw:
                        maxw = w
            if col == "Barkod":
                maxw = min(maxw, 720)
                maxw = max(maxw, 260)
            elif col == "Koli Etiketi":
                maxw = min(maxw, 380)
                maxw = max(maxw, 140)
            else:
                maxw = min(maxw, 220)
                maxw = max(maxw, 60)
            try:
                self.tree.column(col, width=maxw)
            except Exception:
                pass
    def _on_date_required_changed(self):
        """'Tarih Zorunlu' kutusu değişince UI ve ayarları senkronlar.
        İstek: kutu işaretlenince otomatik bugünün tarihini atsın (GG.AA.YYYY).
        """
        required = bool(self.var_date_required.get())
        self._sync_date_ui()
        if required:
            # Her aktif edildiğinde bugünün tarihini otomatik set et
            today_str = datetime.now().strftime("%d.%m.%Y")
            self.var_prod_date.set(today_str)
            self._on_date_changed()
        self.veri.settings["date_required"] = int(required)
        self.veri.save_settings()
    def _on_date_changed(self):
        # Tarih değiştiğinde validate edip settings'e yaz
        date_str = (self.var_prod_date.get() or "").strip()
        if date_str:
            if not self._is_valid_date(date_str):
                messagebox.showwarning("Uyarı", "Üretim Tarihi formatı hatalı. Örnek: 10.02.2026")
                return
        self.veri.settings["production_date"] = date_str
        self.veri.save_settings()
    @staticmethod
    def _is_valid_date(date_str: str) -> bool:
        try:
            datetime.strptime(date_str, "%d.%m.%Y")
            return True
        except Exception:
            return False
    
    def _flash_message(self, target_bg: str, target_fg: str, flashes: int = 3, interval_ms: int = 250):
        """Flash the message panel between its current colors and a target color.
        Ends by restoring the original colors."""
        # Cancel any previous flashes
        try:
            for job_id in getattr(self, "_flash_job_ids", []):
                try:
                    self.root.after_cancel(job_id)
                except Exception:
                    pass
        except Exception:
            pass
        self._flash_job_ids = []
        orig_bg = self.msg_frame.cget("bg")
        orig_fg = self.lbl_message.cget("fg")
        orig_lbl_bg = self.lbl_message.cget("bg")
        steps = flashes * 2  # on/off pairs
        def apply(bg, fg):
            self.msg_frame.configure(bg=bg)
            self.lbl_message.configure(bg=bg, fg=fg)
        def tick(i: int):
            if i >= steps:
                # restore
                self.msg_frame.configure(bg=orig_bg)
                self.lbl_message.configure(bg=orig_lbl_bg, fg=orig_fg)
                return
            if i % 2 == 0:
                apply(target_bg, target_fg)
            else:
                apply(orig_bg, orig_fg)
            job = self.root.after(interval_ms, lambda: tick(i + 1))
            self._flash_job_ids.append(job)
        tick(0)
    def show_alert(self, message: str, status: str):
        # Keep the text visible; for warning/error we "flash" the panel 3 times and then restore.
        if status == 'success':
            bg_color = "#d1e7dd"; fg_color = "#0f5132"
            self._set_light("green")
            self._play_tone("ok")
            self.msg_frame.configure(bg=bg_color)
            self.lbl_message.configure(text=message, bg=bg_color, fg=fg_color)
            return
        if status == 'warning':
            bg_color = "#fff3cd"; fg_color = "#664d03"
            self._set_light("yellow")
            self._play_tone("dup")
        else:
            bg_color = "#f8d7da"; fg_color = "#842029"
            self._set_light("red")
            self._play_tone("err")
            # Alarm only on error (red)
            self.donanim.trigger_full_alarm()
        # Set text first, then flash the panel (3 times)
        self.lbl_message.configure(text=message)
        self._flash_message(bg_color, fg_color, flashes=3, interval_ms=250)
    # ---------------- Core barcode flow ----------------
    def _require_date_if_needed(self) -> bool:
        if not self.var_date_required.get():
            return True
        date_str = (self.var_prod_date.get() or "").strip()
        if not date_str:
            self.show_alert("❌ Üretim Tarihi zorunlu! Lütfen tarih giriniz.", "error")
            return False
        if not self._is_valid_date(date_str):
            messagebox.showwarning("Uyarı", "Üretim Tarihi formatı hatalı. Örnek: 10.02.2026")
            return False
        return True
    def _set_light(self, color: str):
        colors = {
            "neutral": "#adb5bd",
            "green": "#198754",
            "yellow": "#ffc107",
            "red": "#dc3545",
        }
        self.lbl_light.config(fg=colors.get(color, "#adb5bd"))
    def _play_tone(self, kind: str):
            """Duruma göre güçlü bip sesi üretir.
            ok   : Yeşil / başarılı okuma
            dup  : Sarı  / tekrarlı okuma
            err  : Kırmızı / listede yok veya hata
            """
            try:
                import winsound
            except Exception:
                winsound = None
    
            def _bell():
                try:
                    self.root.bell()
                except Exception:
                    pass
    
            if not winsound:
                return _bell()
    
            # Güçlü ve ayırt edilebilir tonlar
            if kind == "ok":
                # BİP BİP (güçlü)
                winsound.Beep(2000, 130)
                winsound.Beep(2000, 130)
            elif kind == "dup":
                # farklı güçlü desen (3 kısa)
                winsound.Beep(1400, 90)
                winsound.Beep(1400, 90)
                winsound.Beep(900, 120)
            elif kind == "err":
                # düşük + uzun uyarı
                winsound.Beep(500, 220)
                winsound.Beep(350, 260)
            else:
                winsound.Beep(1200, 120)
    
    def _update_code_status(self, info, result_tag: str | None = None):
        """Üst barda kod türü ve meta bilgiyi gösterir.
        result_tag: success|warning|error (opsiyonel)
        """
        try:
            typ = getattr(info, "code_type", "-")
            # Manuel override varsa belirt
            forced = bool(self.var_short_code.get())
            if forced:
                typ_disp = "GS1 SHORT (MANUEL)"
            else:
                typ_disp = typ.replace("_", " ")
            # Renk
            bg = "#343a40"
            if "GS1" in typ_disp:
                bg = "#6f42c1"  # mor
            elif "CTRL" in typ_disp:
                bg = "#6c757d"
            elif "PLAIN" in typ_disp:
                bg = "#198754" if (result_tag == "success") else "#343a40"
            self.lbl_code_status.config(text=f"KOD: {typ_disp}", bg=bg)
            meta = f"RAW:{getattr(info,'raw_len',0)}  NORM:{getattr(info,'normalized_len',0)}"
            if getattr(info, "has_gs", False):
                meta += "  GS✓"
            if getattr(info, "has_other_ctrl", False):
                meta += "  CTRL✓"
            self.lbl_code_meta.config(text=meta)
        except Exception:
            # UI güncellemesi kritik değil
            pass
    def _update_scan_display(self, current: str):
        self.prev_scan_text = self.last_scan_text
        self.last_scan_text = current
        prev = self.prev_scan_text if self.prev_scan_text else "-"
        last = self.last_scan_text if self.last_scan_text else "-"
        self.lbl_prev_scan.config(text=f"Önceki: {prev}")
        self.lbl_last_scan.config(text=f"Son: {last}")
    
    def _clean_barcode(self, s: str) -> str:
        """Scanner/manuel girişten gelen barkod metnini temizler.
        Görünmez/format kontrol karakterlerini kaldırır, NFKC normalize eder.
        GS1 için ASCII 29 korunur.
        """
        if s is None:
            return ""
        s = str(s)
        s = s.replace("\ufeff", "").replace("\u200b", "").replace("\u200c", "").replace("\u200d", "").replace("\u2060", "")
        s = unicodedata.normalize("NFKC", s)
        out = []
        for ch in s:
            o = ord(ch)
            if o == 29:
                out.append(ch)
                continue
            cat = unicodedata.category(ch)
            if cat.startswith("C"):
                continue
            if ch in ("\r", "\n", "\t"):
                continue
            out.append(ch)
        return "".join(out).strip()
    def _log_scan(self, typ: str, barcode: str, row_id=None, box=None, message: str = ""):
        self.scan_report.append({
            "ts": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "type": typ,
            "barcode": barcode,
            "row_id": row_id,
            "box": box,
            "message": message,
        })
        # Çok büyümesin
        if len(self.scan_report) > 3000:
            self.scan_report = self.scan_report[-2000:]

        # mini rapor tablosunu güncelle (varsa)
        if hasattr(self, "scan_tree") and self.scan_tree.winfo_exists():
            try:
                for iid in self.scan_tree.get_children():
                    self.scan_tree.delete(iid)
                last = self.scan_report[-7:]
                for i, it in enumerate(last, start=max(1, len(self.scan_report) - len(last) + 1)):
                    msg = f"{it.get('type','')} | {it.get('barcode','')} {it.get('message','')}".strip()
                    self.scan_tree.insert("", "end", values=(i, msg))
            except Exception:
                pass
    def open_scanner_report_window(self):
        win = tk.Toplevel(self.root)
        win.title("Scanner Raporu (Tekrar / Listede Yok / Hata)")
        win.geometry("980x560")
        top = tk.Frame(win)
        top.pack(fill="x", padx=10, pady=8)
        tk.Label(top, text="Kayıtlar:", font=("Segoe UI", 10, "bold")).pack(side="left")
        def clear():
            self.scan_report.clear()
            refresh()
        tk.Button(top, text="Temizle", command=clear).pack(side="right")
        cols = ("ts", "type", "row_id", "box", "barcode", "message")
        tree = ttk.Treeview(win, columns=cols, show="headings", height=22)
        tree.heading("ts", text="Tarih/Saat"); tree.column("ts", width=150, anchor="w")
        tree.heading("type", text="Tür"); tree.column("type", width=90, anchor="center")
        tree.heading("row_id", text="Satır"); tree.column("row_id", width=70, anchor="center")
        tree.heading("box", text="Koli"); tree.column("box", width=70, anchor="center")
        tree.heading("barcode", text="Barkod"); tree.column("barcode", width=420, anchor="w")
        tree.heading("message", text="Açıklama"); tree.column("message", width=180, anchor="w")
        tree.pack(fill="both", expand=True, padx=10, pady=10)
        # Log context menu (kopyala + görüntüle)
        log_menu = tk.Menu(win, tearoff=0)
        def _get_sel_barcode():
            sel = tree.selection()
            if not sel:
                return ""
            try:
                vals = tree.item(sel[0], "values")
                return vals[4] if len(vals) > 4 else ""
            except Exception:
                return ""
        def _copy():
            bc = _get_sel_barcode()
            if not bc:
                return
            try:
                self.root.clipboard_clear()
                self.root.clipboard_append(bc)
                self.root.update()
            except Exception:
                pass
        def _show():
            bc = _get_sel_barcode()
            if not bc:
                return
            # ana ekrandaki detay penceresini aynı kodla aç
            try:
                # geçici olarak seçili barkodu göstermek için show_selected_code benzeri
                info = code_parser.analyze(bc)
                gs1 = code_parser.parse_gs1(info.cleaned_keep_gs)
                w = tk.Toplevel(self.root)
                w.title("Kod Detayları (Log)")
                w.geometry("760x480")
                tk.Label(w, text="TAM KOD:", font=("Segoe UI", 10, "bold")).pack(anchor="w", padx=12, pady=(12,2))
                t = tk.Text(w, height=3, wrap="none", font=("Consolas", 11))
                t.pack(fill="x", padx=12)
                t.insert("1.0", bc)
                t.configure(state="disabled")
                tk.Label(w, text=f"KOD TÜRÜ: {info.code_type}", fg="#0b2e4a", font=("Segoe UI", 10, "bold")).pack(anchor="w", padx=12, pady=(8,0))
                tk.Label(w, text="GS1 AYRIŞTIRMA:", font=("Segoe UI", 10, "bold")).pack(anchor="w", padx=12, pady=(10,2))
                b = tk.Text(w, height=8, wrap="word", font=("Consolas", 10))
                b.pack(fill="both", expand=True, padx=12, pady=(0,10))
                if gs1:
                    out=[]
                    if "01" in gs1: out.append(f"01 -> GTIN   : {gs1.get('01')}")
                    if "21" in gs1: out.append(f"21 -> Serial : {gs1.get('21')}")
                    for k,v in gs1.items():
                        if k in ("01","21"): continue
                        out.append(f"{k} -> {v}")
                    b.insert("1.0", "\n".join(out))
                else:
                    b.insert("1.0", "(Ayrıştırma bulunamadı.)")
                b.configure(state="disabled")
                tk.Button(w, text="Kapat", command=w.destroy, bg="#dc3545", fg="white").pack(pady=(0,12))
            except Exception:
                pass
        log_menu.add_command(label="🔍 KODU GÖRÜNTÜLE", command=_show)
        log_menu.add_command(label="📋 KOPYALA", command=_copy)
        def _popup(ev):
            iid = tree.identify_row(ev.y)
            if iid:
                tree.selection_set(iid)
                log_menu.post(ev.x_root, ev.y_root)
        tree.bind("<Button-3>", _popup)
        def refresh():
            tree.delete(*tree.get_children())
            for r in reversed(self.scan_report[-2000:]):
                tree.insert("", "end", values=(r["ts"], r["type"], r["row_id"] or "", r["box"] or "", r["barcode"], r["message"]))
        refresh()
    def process_barcode(self, barcode: str):
        if not barcode:
            return
        info = code_parser.analyze(barcode)
        # Manuel override: kullanıcı GS1 Short işaretlediyse zorla short kabul et
        force_short = bool(self.var_short_code.get())
        scan_keep = info.cleaned_keep_gs
        scan_nogs = info.normalized_nogs
        # Ekran "Son/Önceki" gösterimi: okunabilir olsun diye GS -> |
        display_val = scan_keep.replace(chr(29), "|")
        self._update_scan_display(display_val)
        self._update_code_status(info)
        self.manual_entry.delete(0, tk.END)
        if not self._require_date_if_needed():
            self._log_scan("DATE", scan_nogs or scan_keep, message="Üretim tarihi zorunlu / hatalı")
            return
        # Minimum uzunluk kontrolünü normalize edilmiş değere göre yap
        if len(scan_nogs) < 5 and len(scan_keep) < 5:
            self._log_scan("BAD", scan_nogs or scan_keep, message="Okunamayan veri")
            self.show_alert("❌ HATA: OKUNAMAYAN VERİ!", "error")
            self._update_code_status(info, result_tag="error")
            return
        if self.items_per_box <= 0:
            messagebox.showwarning("Uyarı", "Lütfen Koli İçi Adet giriniz.")
            return
        # Eşleştirmede kullanılacak değer:
        # - Normal kodlarda scan_keep (mevcut davranış)
        # - Short/ctrl kodlarda scan_nogs daha güvenli
        match_val_primary = scan_keep
        match_val_alt = scan_nogs
        if force_short or info.code_type in ("GS1_SHORT", "CTRL_MIXED"):
            match_val_primary = scan_nogs
            match_val_alt = scan_keep
        # Log amaçlı: eşleştirmede kullanılan değer
        scan_val = match_val_primary
        if self.items_per_box <= 0:
            messagebox.showwarning("Uyarı", "Lütfen Koli İçi Adet giriniz.")
            return
        # Pending satır var mı?
        for i, item in enumerate(self.work_list):
            if item.get('status') == 'PENDING' and (item.get('search') == match_val_primary or item.get('search_nogs') == match_val_primary or item.get('search') == match_val_alt or item.get('search_nogs') == match_val_alt):
                self.verified_count += 1
                try:
                    self._scan_times.append(time.time())
                    self._update_speed_gauge()
                except Exception:
                    pass
                box_info = self.next_print_info
                item['status'] = 'VERIFIED'
                item['box'] = box_info['box_num']
                item['label'] = box_info['label']
                item['in_box'] = ((self.verified_count - 1) % self.items_per_box) + 1 if self.items_per_box > 0 else ""
                item['production_date'] = (self.var_prod_date.get() or "").strip()
                self.work_list.pop(i)
                self.work_list.insert(0, item)
                self.veri.save_job_db()
                self.refresh_table()
                self.update_ui()
                self.show_alert(f"✅ OKUNDU: {match_val_primary[:30]}...", "success")
                self._update_code_status(info, result_tag="success")
                # Koli sınırına geldiyse koli etiketini bas
                if self.verified_count % self.items_per_box == 0:
                    # BOX etiketi kullanılmıyorsa (box_label_list yoksa) koli etiketi basma.
                    if int(self.var_printer_enabled.get() or 0) == 1 and self.box_label_list and box_info.get('label') not in (None, '', '-'):
                        self.donanim.print_label(box_info['label'], "box")
                return
        # Zaten okundu mu?
        for it in self.work_list:
            if it.get('status') == 'VERIFIED' and (it.get('search') == match_val_primary or it.get('search_nogs') == match_val_primary or it.get('search') == match_val_alt or it.get('search_nogs') == match_val_alt):
                box_no = it.get('box', '-')
                row_id = it.get('id', None)
                self._log_scan("DUP", scan_val, row_id=row_id, box=box_no, message="Zaten okundu")
                self.show_alert(f"⚠ ZATEN OKUNDU! (Satır: {row_id} | Koli: {box_no})", "warning")
                self._update_code_status(info, result_tag="warning")
                return
        # Listede yok
        self._log_scan("MISS", scan_val, message="Listede yok")
        self.show_alert(f"❌ HATA: LİSTEDE YOK! ({match_val_primary[:30]}...)", "error")
        self._update_code_status(info, result_tag="error")
    
    def delete_job(self):
        """Mevcut işi (job) sil. Yönetici Paneli > Silme sekmesinden çağrılır."""
        try:
            self.veri.delete_job()
        except Exception as ex:
            from tkinter import messagebox
            return messagebox.showerror("Hata", str(ex))
        try:
            self.refresh_table()
        except Exception:
            pass
    def update_loaded_code_type(self, code_type: str):
        """Yüklenen dosyanın kod türünü (PLAIN / GS1_SHORT / CTRL_MIXED ...) üstte gösterir."""
        try:
            self.loaded_code_type = code_type or "-"
            self._set_code_type_label(self.loaded_code_type)
        except Exception:
            pass
        try:
            self.update_ui()
        except Exception:
            pass

    def _set_code_type_label(self, code_type: str) -> None:
        """Sağ üstteki KOD TÜRÜ etiketini günceller (uygulama içi gösterim).
        Not: loaded_code_type değiştirmez; yalnızca label günceller.
        """
        try:
            disp = (code_type or "-").replace("_", " ")
            mapping = {
                "PLAIN": "DÜZ",
                "GS1 SHORT": "SHORTKOD",
                "GS1_SHORT": "SHORTKOD",
                "CTRL MIXED": "KONTROL",
                "CTRL_MIXED": "KONTROL",
                "-": "-",
            }
            disp2 = mapping.get(disp, disp)
            if hasattr(self, "lbl_loaded_code_type"):
                self.lbl_loaded_code_type.config(text=f"KOD TÜRÜ: {disp2}")
        except Exception:
            pass

    def _on_table_selection_changed(self, event=None):
        """Treeview satır seçimi değişince, seçili barkoda göre KOD TÜRÜ bilgisini günceller."""
        try:
            sel = self.tree.selection()
            if not sel:
                # Seçim yoksa dosya/genel türü göster
                self._set_code_type_label(getattr(self, "loaded_code_type", "-"))
                return
            vals = self.tree.item(sel[0], "values")
            barcode = vals[4] if vals and len(vals) > 4 else ""
            if not barcode or barcode == "-":
                self._set_code_type_label(getattr(self, "loaded_code_type", "-"))
                return
            info = code_parser.analyze(str(barcode))
            self._set_code_type_label(info.code_type)
        except Exception:
            pass

    def refresh_table(self):
        """Tabloyu work_list verisiyle yeniden doldurur."""
        try:
            def _as_dict(x):
                # dict / sqlite3.Row / tuple/list -> dict
                if x is None:
                    return {}
                if isinstance(x, dict):
                    return x
                # sqlite3.Row or Mapping
                try:
                    if hasattr(x, 'keys'):
                        return {k: x[k] for k in x.keys()}
                except Exception:
                    pass
                # tuple/list fallback (old formats)
                if isinstance(x, (list, tuple)):
                    keys = ['id', 'box', 'status', 'read_at', 'raw', 'label', 'in_box']
                    d = {}
                    for i, k in enumerate(keys):
                        if i < len(x):
                            d[k] = x[i]
                    return d
                return {}

            for iid in self.tree.get_children():
                self.tree.delete(iid)

            def _safe_str(v):
                # Tcl/Tk NUL (\x00) ve kontrol karakterleri sorun çıkarabiliyor.
                try:
                    s = "" if v is None else str(v)
                    s = s.replace("\x00", "")
                    # diğer kontrol karakterlerini de temizle (GS1 ayırıcı 29 hariç)
                    out = []
                    for ch in s:
                        o = ord(ch)
                        if o == 29:  # GS1 ayırıcı kalsın
                            out.append(ch); continue
                        # C0 control range
                        if o < 32:
                            continue
                        out.append(ch)
                    return "".join(out)
                except Exception:
                    return "" if v is None else str(v)

            for item in self.work_list:
                item = _as_dict(item)
                tag = 'verified' if item.get('status') == 'VERIFIED' else 'pending'
                try:
                    self.tree.insert("", "end",
                                     values=(
                                         _safe_str(item.get('id')),
                                         _safe_str(item.get('box')),
                                         _safe_str(item.get('status')),
                                         _safe_str(item.get('read_at','')),
                                         _safe_str(item.get('raw_disp', item.get('raw'))),
                                         _safe_str(item.get('label')),
                                         _safe_str(item.get('in_box', '')),
                                     ),
                                     tags=(tag,))
                except Exception:
                    # Tek satır bozuksa tüm tabloyu boş bırakma
                    continue
# ilk satıra kaydır
            children = self.tree.get_children()
            if children:
                self.tree.see(children[0])
            # Tablo yeniden kurulduysa üstteki kod türü bilgisini senkronla
            try:
                # Eğer loaded_code_type boş/PLAIN görünüyorsa ama listede SHORTKOD varsa SHORTKOD göster
                if getattr(self, "work_list", None):
                    sample = [(_as_dict(i).get('raw')) for i in self.work_list if str((_as_dict(i).get('raw')) or '').strip()][:50]
                    has_short = False
                    for x in sample:
                        try:
                            info = code_parser.analyze(str(x))
                            if info.code_type == "GS1_SHORT":
                                has_short = True
                                break
                        except Exception:
                            pass
                    if has_short:
                        self.loaded_code_type = "GS1_SHORT"
                self._set_code_type_label(getattr(self, "loaded_code_type", "-"))
            except Exception:
                pass
        except Exception:
            pass
    def update_ui(self):
        """Sayaçlar + koli bilgisi + reject durumu."""
        try:
            self.lbl_total.config(text=str(len(self.work_list)))
            self.lbl_ok.config(text=str(self.verified_count))
        except Exception:
            pass
        # --- Üst sayaçlar: Toplam / Tamamlanan / Kalan / Koli(Şu an) / Koli(Sıradaki)
        total = len(self.work_list)
        ok = self.verified_count
        remaining = max(0, total - ok)

        # Koli hesaplama + KOLİ DURUMU paneli
        items_per_box = int(self.items_per_box or 0)

        # toplam koli hedefi (ürün listesi doluysa)
        box_goal = 0
        if items_per_box > 0 and total > 0:
            box_goal = (total + items_per_box - 1) // items_per_box

        if items_per_box > 0:
            if ok == 0:
                current_box_num = 0
                next_box_num = 1
                done_boxes = 0
                inbox = 0
                inbox_disp = 0
                status_txt = 'HAZIR'
            else:
                done_boxes = ok // items_per_box
                inbox = ok % items_per_box
                if inbox == 0:
                    # Tam kat doldu: şu anki koli tamamlandı
                    current_box_num = max(1, done_boxes)
                    next_box_num = current_box_num + 1
                    inbox_disp = items_per_box
                    status_txt = 'TAMAMLANDI'
                else:
                    current_box_num = done_boxes + 1
                    next_box_num = current_box_num + 1
                    inbox_disp = inbox
                    status_txt = 'DOLUYOR'
        else:
            # koli adeti yoksa basit hesap
            current_box_num = 0 if ok == 0 else 1
            next_box_num = current_box_num + 1
            done_boxes = 0
            inbox = 0
            inbox_disp = 0
            status_txt = 'HAZIR'

        # Kalan koli (hedef biliniyorsa)
        box_left = 0
        if box_goal > 0:
            box_left = max(0, box_goal - (ok // items_per_box if items_per_box > 0 else 0))

        # Koli etiketi (box.csv) seçimi: yazdırma için 0 iken 1'i kullan
        print_box_num = current_box_num if current_box_num > 0 else 1

        current_label = '-'
        if self.box_label_list:
            idx = print_box_num - 1
            if 0 <= idx < len(self.box_label_list):
                current_label = self.box_label_list[idx]
            else:
                current_label = 'LİSTE BİTTİ'

        # Üst kartlar
        try:
            self.lbl_total.configure(text=str(total))
            self.lbl_ok.configure(text=str(ok))
            self.lbl_remaining.configure(text=str(remaining))
            # Sonraki (ürün): yapılan + 1 (bitti ise '-')
            nxt = "-" if total > 0 and ok >= total else str(ok + 1)
            self.lbl_next.configure(text=nxt)
        except Exception:
            pass

        # KOLİ DURUMU paneli
        try:
            if hasattr(self, 'lbl_box_now'):
                self.lbl_box_now.configure(text=str(current_box_num))
                self.lbl_box_next.configure(text=str(next_box_num))
                self.lbl_box_done.configure(text=str(ok // items_per_box) if items_per_box > 0 else '0')
                self.lbl_box_left.configure(text=str(box_left) if box_goal > 0 else '-')
                self.lbl_box_goal.configure(text=str(box_goal) if box_goal > 0 else '-')

                # koli içi x/y ve progress
                if items_per_box > 0:
                    self.lbl_box_inbox.configure(text=f'KOLİ İÇİ: {inbox_disp}/{items_per_box}')
                    pct = int(round((inbox_disp / items_per_box) * 100)) if items_per_box else 0
                    try:
                        self._g_fill_target = max(0.0, min(1.0, pct / 100.0))
                    except Exception:
                        pass
                    try:
                        self.pb_box.configure(maximum=100)
                        self.pb_box['value'] = pct
                    except Exception:
                        pass
                    self.lbl_box_percent.configure(text=f'{pct}%')
                else:
                    self.lbl_box_inbox.configure(text='KOLİ İÇİ: -')
                    try:
                        self.pb_box['value'] = 0
                    except Exception:
                        pass
                    self.lbl_box_percent.configure(text='-')

                # durum rengi
                if status_txt == 'TAMAMLANDI':
                    self.lbl_box_status.configure(text=status_txt, fg='#198754')
                elif status_txt == 'DOLUYOR':
                    self.lbl_box_status.configure(text=status_txt, fg='#fd7e14')
                else:
                    self.lbl_box_status.configure(text=status_txt, fg='#0d6efd')
        except Exception:
            pass

        self.next_print_info = {'box_num': print_box_num, 'label': current_label}
    # Reject durum etiketi + kullanıcı toggle
        try:
            active = bool(getattr(self.donanim, 'reject_is_active', False))
            enabled = bool(getattr(self.donanim, 'reject_user_enabled', True))
            if not enabled:
                txt = "REJECT: KAPALI"
                bg = "#6c757d"
            else:
                txt = ("REJECT: AKTİF" if active else "REJECT: PASİF")
                bg = ("#198754" if active else "#dc3545")
                # Sebep bilgisini kısa göster (neden pasif?)
                if not active and getattr(self.donanim, 'rejector', None):
                    rej = self.donanim.rejector
                    err = getattr(rej, 'last_error', None)
                    port = getattr(rej, 'port_name', '') or self.veri.settings.get("reject_port", "COM2")
                    if err == "PYSerialMissing":
                        txt += " (pyserial yok)"
                    elif err == "PORT_NOT_FOUND":
                        ports = []
                        try:
                            ports = rej.available_ports()
                        except Exception:
                            ports = []
                        if ports:
                            txt += f" ({port} yok: {', '.join(ports)})"
                        else:
                            txt += f" ({port} yok)"
                    elif err == "OPEN_FAILED":
                        txt += f" ({port} açılamadı)"
                    elif err == "RUNTIME_ERROR":
                        txt += f" ({port} hata verdi)"
            # REJECT: sadece renk
            try:
                if not enabled:
                    self.set_device_state('reject','disconnected')
                else:
                    self.set_device_state('reject','connected' if active else 'disconnected')
            except Exception:
                pass
            # Yazıcı rozeti
            self._update_printer_device_badges()
            # Excel progress satırı (Koli içi / %)
            self._update_box_panel_excel(total=len(self.work_list), done=self.verified_count)
            try:
                self._update_speed_gauge()
                self._update_eta()
            except Exception:
                pass
        except Exception:
            pass

    def _start_device_badge_loop(self):
        """Yazıcı cihaz rozetlerini gerçek socket bağlantısına göre periyodik günceller.
        UI'yi bloklamamak için kontrol ayrı thread'de yapılır.
        """
        try:
            self._device_badge_loop()
        except Exception:
            # UI asla çökmesin
            pass

    def _device_badge_loop(self):
        try:
            self._kick_printer_checks()
            self._update_printer_device_badges()
        finally:
            try:
                self.root.after(5000, self._device_badge_loop)
            except Exception:
                pass

    def _kick_printer_checks(self):
        """3 yazıcı için kısa timeout'lu socket ping çalıştırır."""
        try:
            if getattr(self, '_printer_check_inflight', False):
                return
            self._printer_check_inflight = True

            s = getattr(self, 'veri', None).settings if getattr(self, 'veri', None) else {}
            enabled = bool(getattr(self, 'printer_enabled', True))

            devices = [
                ("box", (s.get('box_ip') or '').strip(), int(s.get('box_port', 9100) or 9100)),
                ("prod", (s.get('prod_ip') or '').strip(), int(s.get('prod_port', 9100) or 9100)),
                ("prod2", (s.get('prod2_ip') or '').strip(), int(s.get('prod2_port', 9100) or 9100)),
            ]

            def _worker():
                try:
                    if not enabled:
                        self._printer_state = {k: None for (k, _, _) in devices}
                        return
                    out = {}
                    for key, ip, port in devices:
                        if not ip:
                            out[key] = None
                            continue
                        ok = False
                        try:
                            with socket.create_connection((ip, port), timeout=0.6):
                                ok = True
                        except Exception:
                            ok = False
                        out[key] = ok
                    self._printer_state = out
                finally:
                    self._printer_check_inflight = False
                    try:
                        self.root.after(0, self._update_printer_device_badges)
                    except Exception:
                        pass

            threading.Thread(target=_worker, daemon=True).start()
        except Exception:
            self._printer_check_inflight = False


    def _update_printer_device_badges(self):
        """Üst şeritteki yazıcı cihaz rozetlerini günceller.
        - IP yok -> KIRMIZI: IP YOK
        - IP var ama socket bağlanmıyor -> KIRMIZI: BAĞLI DEĞİL
        - Socket bağlanıyor -> YEŞİL: HAZIR
        - Kontrol bekleniyor -> TURUNCU: KONTROL
        - Yazıcı kapalı -> GRİ: PASİF
        """
        try:
            enabled = bool(getattr(self, 'printer_enabled', True))
            s = getattr(self, 'veri', None).settings if getattr(self, 'veri', None) else {}

            box_ip = (s.get('box_ip') or '').strip()
            prod_ip = (s.get('prod_ip') or '').strip()
            prod2_ip = (s.get('prod2_ip') or '').strip()

            state = getattr(self, '_printer_state', {}) or {}

            def _set(badge, ip: str, st: bool | None):
                if not badge:
                    return
                if not enabled:
                    badge.config(bg=self._hw_colors.get('disconnected','#dc3545'))
                    return
                if not ip:
                    badge.config(bg=self._hw_colors.get('disconnected','#dc3545'))
                    return
                if st is True:
                    badge.config(bg=self._hw_colors.get('connected','#198754'))
                    return
                if st is False:
                    badge.config(bg=self._hw_colors.get('disconnected','#dc3545'))
                    return
                badge.config(bg=self._hw_colors.get('searching','#f1c40f'))

            _set(getattr(self, 'badge_zd230', None), box_ip, state.get('box'))
            _set(getattr(self, 'badge_zt411_01', None), prod_ip, state.get('prod'))
            _set(getattr(self, 'badge_zt411_02', None), prod2_ip, state.get('prod2'))

        except Exception:
            pass

    def _update_box_panel_excel(self, total: int | None = None, done: int | None = None):
        """Excel düzenindeki 'Koli içi / HAZIR / progress' satırını günceller.

        total: işteki toplam satır sayısı
        done : doğrulanan/toplamlanan satır sayısı
        """
        try:
            if total is None:
                total = int(getattr(self, 'total_count', 0) or 0)
            if done is None:
                done = int(getattr(self, 'verified_count', 0) or 0)

            items_per_box = int(getattr(self, 'items_per_box', 0) or 0)

            # Koli içi x/y
            if items_per_box > 0:
                inbox = done % items_per_box
                if done > 0 and inbox == 0 and done < total:
                    # Tam bir koli bitti; yeni koliye geçildi (görüntüde 0/x olsun)
                    inbox_disp = 0
                else:
                    inbox_disp = inbox
                denom = items_per_box
            else:
                inbox_disp = 0
                denom = 0

            # Durum + yüzde
            if total <= 0:
                status_txt = "HAZIR"
                pct = 0
            elif done >= total:
                status_txt = "TAMAMLANDI"
                pct = 100
            elif denom <= 0:
                status_txt = "HAZIR"
                pct = 0
            elif inbox_disp <= 0:
                status_txt = "HAZIR"
                pct = 0
            else:
                status_txt = "DOLUYOR"
                pct = int(round((inbox_disp / denom) * 100))

            # UI elemanları (excel layout)
            if hasattr(self, 'lbl_box_inbox') and self.lbl_box_inbox:
                self.lbl_box_inbox.config(text=f"Koli içi: {inbox_disp}/{denom}")
            if hasattr(self, 'lbl_box_status') and self.lbl_box_status:
                self.lbl_box_status.config(text=status_txt)
            if hasattr(self, 'box_progress') and self.box_progress:
                try:
                    self.box_progress.configure(maximum=max(1, denom))
                    self.box_progress['value'] = inbox_disp if denom > 0 else 0
                except Exception:
                    pass
            if hasattr(self, 'lbl_box_percent') and self.lbl_box_percent:
                self.lbl_box_percent.config(text=f"{pct}%")
        except Exception:
            # UI asla çökmesin
            pass


    def refresh_all(self):
        """Tablo + kolon genişliği + üst sayaçları birlikte yeniler."""
        self.refresh_table()
        try:
            self.update_loaded_code_type(getattr(self, 'loaded_code_type', '-'))
        except Exception:
            pass
        try:
            self.auto_fit_columns()
        except Exception:
            pass
        self.update_ui()
    # --- wrappers ---
    def bind_numpad(self, entry: tk.Entry, title: str = "Giriş", allow_empty: bool = True):
        """Entry'ye tıklanınca Numpad açar (modal)."""
        def _open(_evt=None):
            try:
                initial = (entry.get() or "").strip()
            except Exception:
                initial = ""
            np = Numpad(self.root, initial=initial, title=title)
            if np.value is None:
                return "break"
            if (not allow_empty) and (str(np.value).strip() == ""):
                return "break"
            try:
                entry.delete(0, "end")
                entry.insert(0, str(np.value))
                entry.event_generate("<KeyRelease>")
            except Exception:
                pass
            return "break"
        entry.bind("<Button-1>", _open)
    
    def run_product_wizard(self, defaults: dict | str | None = None) -> dict | None:
        """Ürün seçimi sonrası Palet/İçerik/KoliAdet/Tarih adımlarını toplar.

        Not: Bazı çağrılarda yanlışlıkla filename (str) gönderilebiliyor. Bu durumda
        güvenli şekilde dict'e çevirip devam eder.
        """
        try:
            if isinstance(defaults, str):
                defaults = {"prod_file": defaults}
            defaults = defaults or {}
            wiz = ProductWizard(self.root, defaults=defaults)
            return wiz.result
        except Exception:
            return None


    def load_file(self, ftype: str):
        self.veri.load_file(ftype)
    def update_box_size(self, event=None):
        """Koli içi adet değiştiğinde (kullanıcı girişi) box doluluk hesabını günceller."""
        try:
            val = ""
            if hasattr(self, "entry_koli_adet") and self.entry_koli_adet:
                val = (self.entry_koli_adet.get() or "").strip()
            if val:
                self.items_per_box = max(1, int(val))
            else:
                # Boşsa hesap 0 göster, çökme olmasın
                self.items_per_box = 0

            try:
                self.veri.save_job_db()
            except Exception:
                pass

            try:
                self.update_ui()
            except Exception:
                pass
            try:
                self._update_box_panel_excel()
            except Exception:
                pass
        except Exception:
            pass

    def load_job_v2(self, job_id: str):
        """
        Geçmiş İşler (Job V2) penceresinden gelen seçim.
        Parametre job_id'dir (CSV path değildir).
        DB'den header + item'ları çekip UI'ı yeniden kurar.
        """
        try:
            jm = getattr(self, "job_manager", None)
            if jm is None:
                # Son çare: yeni instance
                from job_yonetimi import JobYonetimi
                jm = JobYonetimi()
                self.job_manager = jm

            header, items = jm.load_job(str(job_id))
            if header is None:
                try:
                    from tkinter import messagebox
                    messagebox.showerror("Hata", "Seçili iş veritabanında bulunamadı.")
                except Exception:
                    pass
                return False

            # Aktif job
            self.current_job_id = header.job_id

            # Ayarlar/iş durumu
            try:
                settings = json.loads(header.settings_json or "{}")
            except Exception:
                settings = {}

            # work_list'i yeniden kur (search alanlarını da ekle)
            def _sanitize_for_search(s: str) -> str:
                try:
                    import unicodedata
                    s = "" if s is None else str(s)
                    s = s.replace("\ufeff", "").replace("\u200b", "").replace("\u200c", "").replace("\u200d", "").replace("\u2060", "")
                    s = unicodedata.normalize("NFKC", s)
                    out = []
                    for ch in s:
                        o = ord(ch)
                        if o == 29:  # GS1 ayırıcı
                            out.append(ch); continue
                        cat = unicodedata.category(ch)
                        if cat.startswith("C"):
                            continue
                        if ch in ("\r", "\n", "\t"):
                            continue
                        out.append(ch)
                    return "".join(out).strip()
                except Exception:
                    return ("" if s is None else str(s)).strip()

            self.work_list = []
            verified = 0
            for it in (items or []):
                raw = it.get("raw", "") or ""
                raw_disp = it.get("raw_disp", raw) or raw
                search_val = _sanitize_for_search(raw)
                status = it.get("status", "PENDING") or "PENDING"
                if status == "VERIFIED":
                    verified += 1
                self.work_list.append({
                    "id": int(it.get("id") or 0),
                    "raw": raw,
                    "raw_disp": raw_disp,
                    "search": search_val,
                    "search_nogs": search_val.replace(chr(29), ""),
                    "status": status,
                    "box": it.get("box", "-") if it.get("box", "-") not in (None, "") else "-",
                    "label": it.get("label", "-") if it.get("label", "-") not in (None, "") else "-",
                    "in_box": it.get("in_box", "") or "",
                })

            self.verified_count = verified

            # Koli boyutu / next_print_info
            try:
                self.items_per_box = int(settings.get("box_size") or settings.get("items_per_box") or self.items_per_box or 0)
            except Exception:
                pass
            try:
                self.next_print_info["box_num"] = int(header.current_koli_no or 1)
            except Exception:
                self.next_print_info["box_num"] = 1

            # Box label list: mümkünse dosyadan tekrar oku (varsa)
            self.box_label_list = []
            try:
                work_dir = settings.get("work_dir") or settings.get("last_dir") or settings.get("base_dir") or ""
                box_file = header.box_file or ""
                # box_file tam yol değilse work_dir ile birleştir
                if box_file:
                    if os.path.isabs(box_file):
                        box_path = box_file
                    else:
                        box_path = os.path.join(work_dir, box_file) if work_dir else box_file
                    if os.path.exists(box_path):
                        from veri_yonetimi import _read_barcode_records
                        self.box_label_list = _read_barcode_records(box_path)
            except Exception:
                pass

            # UI buton yazıları
            try:
                self.current_file = header.job_name or "YeniIs"
            except Exception:
                pass

            try:
                if hasattr(self, "btn_prod") and header.prod_file:
                    self.btn_prod.config(text=f"✅ ÜRÜN: {header.prod_file}", bg="#d1e7dd", fg="#0f5132")
                if hasattr(self, "btn_box") and header.box_file:
                    self.btn_box.config(text=f"🏷️ KOLİ: {header.box_file}", bg="#d1e7dd", fg="#0f5132")
            except Exception:
                pass

            # Koli boyutu alanı
            try:
                if hasattr(self, "entry_box_size") and self.items_per_box:
                    self.entry_box_size.delete(0, "end")
                    self.entry_box_size.insert(0, str(self.items_per_box))
            except Exception:
                pass

            # Yenile
            try:
                self.refresh_all()
            except Exception:
                try:
                    self.refresh_table()
                except Exception:
                    pass
            return True

        except Exception as e:
            try:
                from tkinter import messagebox
                messagebox.showerror("Hata", f"İş yükleme başarısız: {e}")
            except Exception:
                pass
            return False





    def open_kaydet_window(self):
        # Aynı pencereyi tekrar tekrar açma: varsa öne getir
        if self._kaydet_win is not None:
            try:
                if self._kaydet_win.winfo_exists():
                    self._kaydet_win.deiconify()
                    self._kaydet_win.lift()
                    self._kaydet_win.focus_force()
                    self._kaydet_win.attributes('-topmost', True)
                    return
            except Exception:
                pass
            self._kaydet_win = None
        win = tk.Toplevel(self.root)
        self._kaydet_win = win
        try:
            win.transient(self.root)
            win.attributes('-topmost', True)
        except Exception:
            pass
        def _on_close():
            self._kaydet_win = None
            win.destroy()
        win.protocol('WM_DELETE_WINDOW', _on_close)
        win.title("Kaydet")
        win.geometry("420x320")
        win.resizable(False, False)
        tk.Label(win, text="Kayıt / Rapor İşlemleri", font=("Segoe UI", 11, "bold")).pack(pady=(14, 6))
        tk.Label(win, text="Aşağıdan istediğiniz kaydı alın.", fg="#6c757d").pack(pady=(0, 10))
        btns = tk.Frame(win)
        btns.pack(pady=8)
        tk.Button(btns, text="Geçmiş İşler", width=18, command=self.open_history_window).grid(row=0, column=0, padx=8, pady=6)
        tk.Button(btns, text="Bitenler (Detay)", width=18, command=self.export_finished).grid(row=0, column=1, padx=8, pady=6)
        tk.Button(btns, text="Bitenler (Tekli)", width=18, command=self.export_finished_single).grid(row=1, column=1, padx=8, pady=6)
        tk.Button(btns, text="Kalanlar", width=18, command=self.export_remaining).grid(row=1, column=0, padx=8, pady=6)
        tk.Button(btns, text="Scanner Raporu", width=18, command=self.open_scanner_report_window).grid(row=2, column=0, padx=8, pady=6)
        tk.Button(btns, text="PDF Çıktısı", width=18, command=self.export_pdf_report).grid(row=2, column=1, padx=8, pady=6)
        sep = ttk.Separator(win, orient="horizontal")
        sep.pack(fill="x", padx=18, pady=12)
        tk.Button(win, text="▶ 3'ünü Çalıştır (Detay + Tekli + Kalanlar)",
                  command=self.export_all_three, bg="#198754", fg="white",
                  font=("Segoe UI", 10, "bold"), height=2).pack(fill="x", padx=18)
        bar = tk.Frame(win)
        bar.pack(fill="x", padx=18, pady=12)
        tk.Button(bar, text="İptal", width=12, command=_on_close).pack(side="left")
        tk.Button(bar, text="Uygula", width=12, bg="#198754", fg="white",
                  command=lambda: (self.export_all_three(), win.after(80, lambda: (win.lift(), win.focus_force(), win.attributes("-topmost", True))))).pack(side="left", padx=10)
        tk.Button(bar, text="Kaydet", width=12, bg="#0d6efd", fg="white", command=lambda: (self.export_all_three(), _on_close())).pack(side="right")


    def export_all_three(self):
        self.veri.export_all_three(silent=False)

    def export_pdf_report(self):
        self.veri.export_pdf_report(silent=False)

    def open_history_window(self):
        self.veri.open_history_window()
    def export_finished(self):
        self.veri.export_finished()
    def export_finished_single(self):
        self.veri.export_finished_single()
    def export_remaining(self):
        self.veri.export_remaining()
    # -------------------- Tablo Görünümü / Kolonlar --------------------
    def _default_table_columns(self):
        return ("ID", "Koli", "Durum", "Tarih", "Barkod", "Koli Etiketi", "Koli İçerik No")
    def _default_column_visibility(self):
        return {c: True for c in self._default_table_columns()}
    def apply_table_columns(self, visible_map=None):
        """
        Treeview kolonlarını göster/gizle uygular.
        Tk Treeview'da en temiz yöntem: displaycolumns kullanmak.
        """
        try:
            all_cols = self._default_table_columns()
            if visible_map is None:
                # Ayarlardan oku
                visible_map = self.veri.settings.get("table_columns_visible", None)
            if not isinstance(visible_map, dict):
                visible_map = self._default_column_visibility()
            display = [c for c in all_cols if bool(visible_map.get(c, True))]
            if not display:
                # hiçbiri kapalı kalmasın; minimum Barkod açık kalsın
                display = ["Barkod"]
                visible_map["Barkod"] = True
            self.tree["displaycolumns"] = tuple(display)
        except Exception:
            # UI bozulmasın
            pass
    
    def open_manual_verify(self):
        """Manuel barkod doğrulama: sadece PENDING kayıtları listeler."""
        try:
            import arama_penceresi
            arama_penceresi.open_arama_penceresi(self, mode="manual_verify", status_filter="PENDING")
        except Exception as e:
            try:
                from tkinter import messagebox
                messagebox.showerror("Hata", f"Manuel pencere açılamadı: {e}")
            except Exception:
                pass

    def manual_verify_item_by_id(self, item_id: int):
        """Seçili ID'yi sanki scanner okumuş gibi VERIFIED yapar (manuel)."""
        try:
            it = None
            for x in self.work_list:
                try:
                    if int(x.get('id', -1)) == int(item_id):
                        it = x
                        break
                except Exception:
                    continue
            if not it:
                return False
            if str(it.get('status')) == 'VERIFIED':
                return False

            it['status'] = 'VERIFIED'
            try:
                it['read_at'] = datetime.now().isoformat(timespec='seconds')
            except Exception:
                pass
            # box no (koli)
            try:
                it['box'] = str(self.next_print_info.get('box_num', 1) or 1)
            except Exception:
                it['box'] = it.get('box', '-')

            # job_v2 write-through
            try:
                jm = getattr(self, 'job_manager', None)
                if jm is not None and getattr(self, 'current_job_id', None):
                    jm.update_item_status(self.current_job_id, int(item_id), status='VERIFIED', box_no=str(it.get('box','-')), label=str(it.get('label','-')), manual=1)
            except Exception:
                pass

            # rapor / log
            try:
                self.scan_report.append({
                    'ts': time.time(),
                    'type': 'MANUAL',
                    'barcode': str(it.get('raw','')),
                    'row_id': int(item_id),
                    'box': str(it.get('box','-')),
                    'message': 'Manuel doğrulama'
                })
            except Exception:
                pass

            # persist
            try:
                self.veri.save_job_db()
            except Exception:
                pass
            try:
                self.update_ui()
            except Exception:
                pass
            try:
                self.refresh_table()
            except Exception:
                pass
            return True
        except Exception:
            return False
    def open_columns_window(self):
            # tek pencere olsun
            try:
                if getattr(self, "_columns_win", None) is not None and self._columns_win.winfo_exists():
                    self._columns_win.lift()
                    self._columns_win.focus_force()
                    return
            except Exception:
                pass
    
            # --- Ana Tablo ---
            cols_main = self._default_table_columns()
            vis_main = self.veri.settings.get("table_columns_visible", self._default_column_visibility())
            if not isinstance(vis_main, dict):
                vis_main = self._default_column_visibility()
    
            def on_apply_main(vis):
                self.apply_table_columns(vis)
    
            def on_save_main(vis):
                self.veri.settings["table_columns_visible"] = dict(vis)
                try:
                    self.veri.save_settings()
                except Exception:
                    pass
                self.apply_table_columns(vis)
    
            # --- Geçmiş İşler ---
            try:
                cols_hist, default_hist = self.veri._history_default_columns()
            except Exception:
                cols_hist = ("Kaynak", "Durum", "İş Adı", "Ürün Dosyası", "Koli Dosyası", "Güncelleme")
                default_hist = {c: True for c in cols_hist}
                default_hist["İş Adı"] = False
    
            vis_hist = self.veri.settings.get("history_columns_visible", default_hist)
            if not isinstance(vis_hist, dict):
                vis_hist = dict(default_hist)
    
            def on_apply_hist(vis):
                try:
                    self.veri.apply_history_columns(vis)
                except Exception:
                    pass
    
            def on_save_hist(vis):
                self.veri.settings["history_columns_visible"] = dict(vis)
                try:
                    self.veri.save_settings()
                except Exception:
                    pass
                try:
                    self.veri.apply_history_columns(vis)
                except Exception:
                    pass
    
            sections = [
                {
                    "title": "Ana Tablo",
                    "columns": cols_main,
                    "visible_map": vis_main,
                    "default_map": self._default_column_visibility(),
                    "on_apply": on_apply_main,
                    "on_save": on_save_main,
                },
                {
                    "title": "Geçmiş İşler",
                    "columns": cols_hist,
                    "visible_map": vis_hist,
                    "default_map": default_hist,
                    "on_apply": on_apply_hist,
                    "on_save": on_save_hist,
                },
            ]
    
            self._columns_win = KolonlarPenceresi(self.root, sections=sections, title="Kolonlar")
    
def _write_fatal_log(exc: BaseException) -> str:
    try:
        base_dir = os.path.dirname(os.path.abspath(__file__))
    except Exception:
        base_dir = os.getcwd()
    log_dir = os.path.join(base_dir, "logs")
    try:
        os.makedirs(log_dir, exist_ok=True)
    except Exception:
        log_dir = base_dir
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_path = os.path.join(log_dir, f"fatal_{ts}.log")
    try:
        import traceback as _tb
        with open(log_path, "w", encoding="utf-8") as f:
            f.write(_tb.format_exc())
    except Exception:
        pass
    return log_path
def main():
    try:
        root = tk.Tk()
        AnaEkran(root)
        root.mainloop()
    except Exception as e:
        # Hata mesajı + log dosyası
        log_path = _write_fatal_log(e)
        try:
            messagebox.showerror(
                "Kritik Hata",
                "Program beklenmedik şekilde kapandı.\n\n"
                f"Hata kaydı: {log_path}\n\n"
                "Lütfen bu dosyayı bana gönder."
            )
        except Exception:
            pass
        raise

class Numpad(tk.Toplevel):
    def __init__(self, master, initial="", title="Giriş"):
        super().__init__(master)
        self.title(title)
        self.resizable(False, False)
        self.value = None

        self.var = tk.StringVar(value=str(initial))
        e = tk.Entry(self, textvariable=self.var, font=("Segoe UI", 16), justify="right", width=14)
        e.grid(row=0, column=0, columnspan=3, padx=10, pady=10)
        e.focus_set()

        def add(ch):
            self.var.set(self.var.get() + ch)

        def back():
            self.var.set(self.var.get()[:-1])

        def clear():
            self.var.set("")

        def ok():
            self.value = self.var.get().strip()
            self.destroy()

        def cancel():
            self.value = None
            self.destroy()

        btns = [
            ("7", lambda: add("7")), ("8", lambda: add("8")), ("9", lambda: add("9")),
            ("4", lambda: add("4")), ("5", lambda: add("5")), ("6", lambda: add("6")),
            ("1", lambda: add("1")), ("2", lambda: add("2")), ("3", lambda: add("3")),
            ("C", clear), ("0", lambda: add("0")), ("⌫", back),
        ]
        r = 1
        c = 0
        for txt, cmd in btns:
            tk.Button(self, text=txt, command=cmd, width=6, height=2).grid(row=r, column=c, padx=5, pady=5)
            c += 1
            if c == 3:
                c = 0
                r += 1

        tk.Button(self, text="Tamam", command=ok, width=10).grid(row=r, column=0, columnspan=2, padx=5, pady=10, sticky="ew")
        tk.Button(self, text="İptal", command=cancel, width=6).grid(row=r, column=2, padx=5, pady=10)

        self.grab_set()
        self.wait_window()


class ProductWizard(tk.Toplevel):
    """Ürün yüklendikten sonra opsiyonel adımlar: Palet Adet -> Palet İçerik -> Koli Adet -> Tarih"""
    def __init__(self, master, defaults: dict | None = None, default_koli_adet: int = 0):
        super().__init__(master)
        self.title("Ürün Seçenekleri")
        self.resizable(False, False)
        self.result = None
        self._step = 0

        defaults = defaults or {}
        # values
        def _s(v):
            try:
                if v is None:
                    return ""
                if isinstance(v, (int, float)):
                    return str(int(v))
                return str(v)
            except Exception:
                return ""

        self.var_palet_count = tk.StringVar(value=_s(defaults.get("palet_count", "")))
        self.var_palet_icerik = tk.StringVar(value=_s(defaults.get("palet_icerik", "")))
        _koli = defaults.get("koli_adet", None)
        if _koli in (None, "") and default_koli_adet:
            _koli = default_koli_adet
        self.var_koli_adet = tk.StringVar(value=_s(_koli))
        self.var_tarih = tk.StringVar(value=_s(defaults.get("prod_date", "")))

        self.body = tk.Frame(self)
        self.body.pack(fill="both", expand=True, padx=12, pady=12)

        self.lbl_title = tk.Label(self.body, text="", font=("Segoe UI", 12, "bold"))
        self.lbl_title.pack(anchor="w")
        self.lbl_hint = tk.Label(self.body, text="", font=("Segoe UI", 9), fg="#555")
        self.lbl_hint.pack(anchor="w", pady=(2, 10))

        self.entry = tk.Entry(self.body, font=("Segoe UI", 14), width=18, justify="right")
        self.entry.pack(anchor="w")
        self.entry.bind("<Button-1>", self._open_numpad)

        self.btn_row = tk.Frame(self)
        self.btn_row.pack(fill="x", padx=12, pady=(0, 12))

        self.btn_back = tk.Button(self.btn_row, text="Geri", command=self._back)
        self.btn_back.pack(side="left")
        self.btn_skip = tk.Button(self.btn_row, text="Atla", command=self._skip)
        self.btn_skip.pack(side="left", padx=(8, 0))

        self.btn_next = tk.Button(self.btn_row, text="Sonraki", command=self._next)
        self.btn_next.pack(side="right")
        self.btn_ok = tk.Button(self.btn_row, text="Tamam", command=self._finish)
        self.btn_ok.pack(side="right", padx=(0, 8))

        self.protocol("WM_DELETE_WINDOW", self._cancel)
        self._render()
        self.grab_set()
        self.wait_window()

    def _open_numpad(self, _evt=None):
        np = Numpad(self, initial=self.entry.get(), title="Giriş")
        if np.value is None:
            return "break"
        self.entry.delete(0, "end")
        self.entry.insert(0, str(np.value))
        return "break"

    def _render(self):
        steps = [
            ("Kaç Palet?", "Boş bırakabilirsiniz.", self.var_palet_count),
            ("Palet İçeriği", "Boş bırakabilirsiniz.", self.var_palet_icerik),
            ("Koli Adet", "Boş bırakabilirsiniz.", self.var_koli_adet),
            ("Tarih", "GG.AA.YYYY (opsiyonel)", self.var_tarih),
        ]
        title, hint, var = steps[self._step]
        self.lbl_title.config(text=f"{self._step+1}/4 - {title}")
        self.lbl_hint.config(text=hint)
        self.entry.delete(0, "end")
        self.entry.insert(0, var.get())
        self.btn_back.config(state=("disabled" if self._step == 0 else "normal"))
        # last step
        if self._step == len(steps)-1:
            self.btn_next.config(state="disabled")
            self.btn_ok.config(state="normal")
        else:
            self.btn_next.config(state="normal")
            self.btn_ok.config(state="disabled")

    def _save_current(self):
        val = (self.entry.get() or "").strip()
        if self._step == 0:
            self.var_palet_count.set(val)
        elif self._step == 1:
            self.var_palet_icerik.set(val)
        elif self._step == 2:
            self.var_koli_adet.set(val)
        elif self._step == 3:
            self.var_tarih.set(val)

    def _next(self):
        self._save_current()
        if self._step < 3:
            self._step += 1
            self._render()

    def _back(self):
        self._save_current()
        if self._step > 0:
            self._step -= 1
            self._render()

    def _skip(self):
        self.entry.delete(0, "end")
        self._next()

    def _finish(self):
        self._save_current()
        def _to_int(s):
            try:
                s=str(s).strip()
                return int(s) if s else 0
            except Exception:
                return 0
        self.result = {
            "palet_count": _to_int(self.var_palet_count.get()),
            "palet_icerik": _to_int(self.var_palet_icerik.get()),
            "koli_adet": _to_int(self.var_koli_adet.get()),
            "prod_date": (self.var_tarih.get() or "").strip(),
        }
        self.destroy()

    def _cancel(self):
        self.result = None
        self.destroy()

if __name__ == "__main__":
    main()
