import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import socket
import os
import json
import threading
import time
import ctypes # Windows Güç Yönetimi için

# --- FABRİKA AYARLARI ---
FACTORY_DEFAULTS = {
    "long": {
        "dpi": 203, "module_size": 3, "offset_x": 30, "offset_y": -20,
        "orientation": "N", "label_w": 20, "label_h": 20
    },
    "short": {
        "dpi": 203, "module_size": 5, "offset_x": 60, "offset_y": 15,
        "orientation": "N", "label_w": 20, "label_h": 20
    }
}

# --- WINDOWS GÜÇ YÖNETİMİ SABİTLERİ ---
ES_CONTINUOUS = 0x80000000
ES_SYSTEM_REQUIRED = 0x00000001 # Bilgisayarın uyumasını engeller
# ES_DISPLAY_REQUIRED = 0x00000002 # Ekranın kapanmasını engeller (İsterseniz aktif edilebilir)

class ZebraApp:
    def __init__(self, root):
        self.root = root
        self.root.title("ÖN HAZIRLIK - Etiket Hazırlama (Selsil Zebra Master)")
        self.root.geometry("750x950")
        self.root.configure(bg="#333")
        # Windows davranışı: pencere "daima üstte" olmasın
        try: self.root.wm_attributes("-topmost", False)
        except Exception: pass

        self.work_list = []
        self.current_list_path = None  # Liste dosyası yolu (çıktı klasörü için)
        
        # --- CONFIG ---
        app_data_dir = os.getenv('APPDATA')
        self.save_dir = os.path.join(app_data_dir, "SelsilZebra")
        if not os.path.exists(self.save_dir): os.makedirs(self.save_dir)
        self.config_file = os.path.join(self.save_dir, "zebra_config.json")
        
        defaults = self.load_config()
        
        self.var_ip = tk.StringVar(value=defaults.get("ip", "192.168.1.111"))
        self.var_darkness = tk.IntVar(value=defaults.get("darkness", 15))
        self.var_mode = tk.StringVar(value=defaults.get("mode", "long"))
        self.var_dpi = tk.IntVar(value=defaults.get("dpi", 203))
        self.var_module_size = tk.IntVar(value=defaults.get("module_size", 3))
        self.var_label_w = tk.DoubleVar(value=defaults.get("label_w", 20)) 
        self.var_label_h = tk.DoubleVar(value=defaults.get("label_h", 20)) 
        self.var_offset_x = tk.IntVar(value=defaults.get("offset_x", 30)) 
        self.var_offset_y = tk.IntVar(value=defaults.get("offset_y", -20)) 
        self.var_orientation = tk.StringVar(value=defaults.get("orientation", "N"))
        
        self.var_print_scope = tk.StringVar(value="all")
        self.var_range_start = tk.StringVar(value="1")
        self.var_range_end = tk.StringVar(value="1")

        # --- Değişiklik takibi (ayarlar kaybolmasın diye) ---
        self._dirty = False
        for _v in [
            self.var_ip, self.var_darkness, self.var_mode, self.var_dpi, self.var_module_size,
            self.var_label_w, self.var_label_h, self.var_offset_x, self.var_offset_y, self.var_orientation
        ]:
            try:
                _v.trace_add("write", lambda *_: self._mark_dirty())
            except Exception:
                pass

        # Pencere kapatılırken ayarları otomatik kaydet
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

        # --- DURUM BAYRAKLARI ---
        self.is_printing = False
        self.is_paused = False
        self.stop_requested = False

        self.setup_ui()

    # --- BİLGİSAYAR UYKUSUNU ENGELLEME ---
    def prevent_system_sleep(self):
        """Yazdırma başladığında PC'nin uyumasını engeller"""
        try:
            # Sadece Sistemi açık tut (Ekran kapanabilir ama PC çalışır)
            ctypes.windll.kernel32.SetThreadExecutionState(ES_CONTINUOUS | ES_SYSTEM_REQUIRED)
            print("⚡ UYKU MODU ENGELLENDİ: Yazdırma Güvenli")
        except: pass

    def allow_system_sleep(self):
        """Yazdırma bitince normal moda döner"""
        try:
            ctypes.windll.kernel32.SetThreadExecutionState(ES_CONTINUOUS)
            print("💤 UYKU MODU SERBEST")
        except: pass

    def load_config(self):
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, "r") as f: return json.load(f)
            except: pass
        return {}

    def get_output_dir(self):
        """Çıktı/ayar klasörü: Liste dosyası seçildiyse onun adıyla klasör açar.
        - Örn: C:\...\liste.csv -> C:\...\liste\
        Seçilmediyse APPDATA\SelsilZebra kullanılır.
        """
        try:
            if self.current_list_path:
                base_dir = os.path.dirname(self.current_list_path)
                stem = os.path.splitext(os.path.basename(self.current_list_path))[0]
                out_dir = os.path.join(base_dir, stem)
                os.makedirs(out_dir, exist_ok=True)
                return out_dir
        except Exception:
            pass
        return self.save_dir

    def save_config(self):
        data = {
            "ip": self.var_ip.get(), "darkness": self.var_darkness.get(), "mode": self.var_mode.get(),
            "dpi": self.var_dpi.get(), "module_size": self.var_module_size.get(),
            "label_w": self.var_label_w.get(), "label_h": self.var_label_h.get(),
            "offset_x": self.var_offset_x.get(), "offset_y": self.var_offset_y.get(),
            "orientation": self.var_orientation.get()
        }
        try:
            # 1) Global (APPDATA) ayarlarını kaydet (varsayılanların kaybolmaması için)
            with open(self.config_file, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)

            # 2) Liste dosyası seçildiyse, o dosya adına göre klasör açıp içine de kaydet
            out_dir = self.get_output_dir()
            per_file_cfg = os.path.join(out_dir, "zebra_config.json")
            try:
                with open(per_file_cfg, "w", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
            except Exception:
                # Per-dosya kaydı başarısız olsa bile global kayıt kalsın
                pass

            if self.current_list_path:
                messagebox.showinfo("Bilgi", f"✅ Ayarlar Kaydedildi!\n\nKlasör: {out_dir}")
            else:
                messagebox.showinfo("Bilgi", "✅ Ayarlar Kaydedildi!")
            self._dirty = False
        except Exception as e:
            messagebox.showerror("Hata", str(e))

    def _mark_dirty(self):
        self._dirty = True

    def apply_settings(self):
        """Ayarları uygular (UI değerleri zaten aktif). Seçili moda ait fabrika presetini istersen uygular."""
        # Kullanıcı mod değiştirdiyse, o moda göre önerilen ofset/dot ayarlarını uygula
        self.apply_preset()
        self.lbl_status.config(text="✅ Ayarlar Uygulandı", fg="#00ff00")
        self._dirty = True

    def on_close(self):
        """Kapatırken ayarları kaybetmemek için otomatik kaydeder."""
        try:
            # Sessiz otomatik kayıt (kullanıcı her seferinde yeniden ayar yapmasın)
            self._save_config_silent()
        finally:
            self.root.destroy()

    def _save_config_silent(self):
        data = {
            "ip": self.var_ip.get(), "darkness": int(self.var_darkness.get()), "mode": self.var_mode.get(),
            "dpi": int(self.var_dpi.get()), "module_size": int(self.var_module_size.get()),
            "label_w": float(self.var_label_w.get()), "label_h": float(self.var_label_h.get()),
            "offset_x": int(self.var_offset_x.get()), "offset_y": int(self.var_offset_y.get()),
            "orientation": self.var_orientation.get()
        }
        try:
            with open(self.config_file, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)

            # Liste dosyası seçildiyse, aynı ayarı o dosyanın klasörüne de yaz
            out_dir = self.get_output_dir()
            per_file_cfg = os.path.join(out_dir, "zebra_config.json")
            try:
                with open(per_file_cfg, "w", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
            except Exception:
                pass

            self._dirty = False
        except Exception:
            pass

    def apply_preset(self):
        mode = self.var_mode.get()
        preset = FACTORY_DEFAULTS.get(mode)
        if preset:
            self.var_dpi.set(preset["dpi"])
            self.var_module_size.set(preset["module_size"])
            self.var_offset_x.set(preset["offset_x"])
            self.var_offset_y.set(preset["offset_y"])
            self.var_orientation.set(preset["orientation"])
            self.var_label_w.set(preset["label_w"])
            self.var_label_h.set(preset["label_h"])

    def setup_ui(self):
        tk.Label(self.root, text="SELSİL ZEBRA MASTER V2.7", font=("Segoe UI", 16, "bold"), bg="#333", fg="white").pack(pady=10)

        # --- YAZICI ---
        frame_con = tk.LabelFrame(self.root, text="Yazıcı ve DPI", bg="#444", fg="#00ff00", font=("Segoe UI", 10, "bold"))
        frame_con.pack(padx=15, fill="x", pady=5)
        tk.Label(frame_con, text="IP:", bg="#444", fg="white").grid(row=0, column=0, padx=5)
        tk.Entry(frame_con, textvariable=self.var_ip, width=15).grid(row=0, column=1, padx=5)
        
        # KOYULUK AYARI
        tk.Label(frame_con, text="Koyuluk (0-30):", bg="#444", fg="#ffc107", font=("Arial", 9, "bold")).grid(row=0, column=2, padx=5)
        tk.Spinbox(frame_con, from_=0, to=30, textvariable=self.var_darkness, width=5, font=("Arial", 10, "bold")).grid(row=0, column=3, padx=5)
        
        tk.Label(frame_con, text="DPI:", bg="#444", fg="#ffc107").grid(row=0, column=4, padx=5)
        tk.Radiobutton(frame_con, text="203", variable=self.var_dpi, value=203, bg="#444", fg="white", selectcolor="black").grid(row=0, column=5)
        tk.Radiobutton(frame_con, text="300", variable=self.var_dpi, value=300, bg="#444", fg="white", selectcolor="black").grid(row=0, column=6)
        btn_cfg = tk.Frame(frame_con, bg="#444")
        btn_cfg.grid(row=0, column=7, padx=15)

        tk.Button(btn_cfg, text="✅ UYGULA", command=self.apply_settings, bg="#198754", fg="white", width=10).pack(side="left", padx=4)
        tk.Button(btn_cfg, text="💾 KAYDET", command=self.save_config, bg="#0d6efd", fg="white", width=10).pack(side="left", padx=4)
        tk.Button(btn_cfg, text="🚪 KAPAT", command=self.on_close, bg="#6c757d", fg="white", width=10).pack(side="left", padx=4)

        # --- MOD ---
        frame_mode = tk.LabelFrame(self.root, text="ETİKET TİPİ (Otomatik)", bg="#444", fg="#ffc107", font=("Segoe UI", 11, "bold"))
        frame_mode.pack(padx=15, fill="x", pady=10)
        self.rb_long = tk.Radiobutton(frame_mode, text="LONG MODE (203 DPI, Dot:3, X:30, Y:-20)", variable=self.var_mode, value="long", bg="#444", fg="white", selectcolor="black", command=self.apply_preset, font=("Arial", 10))
        self.rb_long.pack(anchor="w", padx=20, pady=5)
        self.rb_short = tk.Radiobutton(frame_mode, text="SHORT MODE (203 DPI, Dot:5, X:60, Y:15)", variable=self.var_mode, value="short", bg="#444", fg="white", selectcolor="black", command=self.apply_preset, font=("Arial", 10))
        self.rb_short.pack(anchor="w", padx=20, pady=5)
        tk.Button(frame_mode, text="🔄 SEÇİLİ MODUN VARSAYILANLARINI YÜKLE", command=self.apply_preset, bg="#6c757d", fg="white").pack(pady=5)

        # --- AYARLAR ---
        frame_dim = tk.LabelFrame(self.root, text="Aktif Ayarlar", bg="#444", fg="#0dcaf0", font=("Segoe UI", 10, "bold"))
        frame_dim.pack(padx=15, fill="x", pady=5)
        tk.Button(frame_dim, text="♻ VARSAYILAN", command=self.apply_preset, bg="#6c757d", fg="white", width=14).grid(row=0, column=6, rowspan=2, padx=10, pady=3)
        tk.Label(frame_dim, text="Etiket (mm):", bg="#444", fg="#aaa").grid(row=0, column=0, padx=5)
        tk.Entry(frame_dim, textvariable=self.var_label_w, width=5).grid(row=0, column=1)
        tk.Label(frame_dim, text="x", bg="#444", fg="#aaa").grid(row=0, column=2)
        tk.Entry(frame_dim, textvariable=self.var_label_h, width=5).grid(row=0, column=3)
        tk.Label(frame_dim, text="Dot Boyutu:", bg="#444", fg="white").grid(row=0, column=4, padx=10)
        tk.Spinbox(frame_dim, from_=1, to=10, textvariable=self.var_module_size, width=5).grid(row=0, column=5)
        tk.Label(frame_dim, text="X Ofset:", bg="#444", fg="white").grid(row=1, column=0, padx=5, pady=5)
        tk.Spinbox(frame_dim, from_=-100, to=200, textvariable=self.var_offset_x, width=5).grid(row=1, column=1)
        tk.Label(frame_dim, text="Y Ofset:", bg="#444", fg="white").grid(row=1, column=2, padx=5)
        tk.Spinbox(frame_dim, from_=-100, to=200, textvariable=self.var_offset_y, width=5).grid(row=1, column=3)
        tk.Label(frame_dim, text="Yön:", bg="#444", fg="white").grid(row=1, column=4, padx=10)
        ttk.Combobox(frame_dim, textvariable=self.var_orientation, values=["N", "I"], width=3, state="readonly").grid(row=1, column=5)

        # --- DOSYA ---
        frame_act = tk.Frame(self.root, bg="#333")
        frame_act.pack(pady=10)
        self.lbl_file = tk.Label(frame_act, text="Dosya Yok", bg="#333", fg="#aaa")
        self.lbl_file.pack()
        tk.Button(frame_act, text="📂 LİSTE YÜKLE", command=self.load_file, bg="#6f42c1", fg="white", width=30).pack(pady=5)
        
        frame_range = tk.Frame(self.root, bg="#333")
        frame_range.pack()
        tk.Radiobutton(frame_range, text="Tümü", variable=self.var_print_scope, value="all", bg="#333", fg="white", selectcolor="black", command=self.toggle_range).pack(side="left")
        tk.Radiobutton(frame_range, text="Aralık:", variable=self.var_print_scope, value="range", bg="#333", fg="white", selectcolor="black", command=self.toggle_range).pack(side="left", padx=5)
        self.entry_start = tk.Entry(frame_range, textvariable=self.var_range_start, width=5, state="disabled"); self.entry_start.pack(side="left")
        tk.Label(frame_range, text="-", bg="#333", fg="white").pack(side="left")
        self.entry_end = tk.Entry(frame_range, textvariable=self.var_range_end, width=5, state="disabled"); self.entry_end.pack(side="left")

        # --- BUTONLAR ---
        frame_btns = tk.Frame(self.root, bg="#333")
        frame_btns.pack(pady=10)
        tk.Button(frame_btns, text="TEK TEST", command=self.print_test_label, bg="#fd7e14", fg="white", width=10).pack(side="left", padx=5)
        self.btn_start = tk.Button(frame_btns, text="🖨️ BAŞLAT", command=self.start_bulk_print, bg="#198754", fg="white", font=("Arial", 11, "bold"), width=15, height=2)
        self.btn_start.pack(side="left", padx=5)
        self.btn_pause = tk.Button(frame_btns, text="⏸️ DURAKLAT", command=self.toggle_pause, bg="#ffc107", fg="black", font=("Arial", 10, "bold"), width=12, state="disabled")
        self.btn_pause.pack(side="left", padx=5)
        self.btn_cancel = tk.Button(frame_btns, text="🟥 İPTAL ET", command=self.cancel_print, bg="#dc3545", fg="white", font=("Arial", 10, "bold"), width=12, state="disabled")
        self.btn_cancel.pack(side="left", padx=5)

        # --- DURUM ---
        frame_progress = tk.Frame(self.root, bg="#222", pady=5)
        frame_progress.pack(side="bottom", fill="x")
        self.lbl_status = tk.Label(frame_progress, text="Hazır", bg="#222", fg="#00ff00", font=("Segoe UI", 12, "bold"))
        self.lbl_status.pack(pady=2)
        self.progress_bar = ttk.Progressbar(frame_progress, orient="horizontal", length=600, mode="determinate")
        self.progress_bar.pack(pady=5, padx=20, fill="x")

    def toggle_range(self):
        st = "normal" if self.var_print_scope.get() == "range" else "disabled"
        self.entry_start.config(state=st); self.entry_end.config(state=st)

    def load_file(self):
        path = filedialog.askopenfilename(filetypes=[("Data", "*.csv;*.txt")])
        if not path: return
        self.current_list_path = path
        # Eğer bu liste için daha önce kaydedilmiş ayar varsa otomatik yükle
        try:
            out_dir = self.get_output_dir()
            per_file_cfg = os.path.join(out_dir, "zebra_config.json")
            if os.path.exists(per_file_cfg):
                with open(per_file_cfg, "r", encoding="utf-8") as f:
                    cfg = json.load(f)
                # Kayıtlı ayarları uygula (IP/DPI/Ofset vb.)
                self.var_ip.set(cfg.get("ip", self.var_ip.get()))
                self.var_darkness.set(int(cfg.get("darkness", self.var_darkness.get())))
                self.var_dpi.set(int(cfg.get("dpi", self.var_dpi.get())))
                self.var_module_size.set(int(cfg.get("module_size", self.var_module_size.get())))
                self.var_label_w.set(float(cfg.get("label_w", self.var_label_w.get())))
                self.var_label_h.set(float(cfg.get("label_h", self.var_label_h.get())))
                self.var_offset_x.set(int(cfg.get("offset_x", self.var_offset_x.get())))
                self.var_offset_y.set(int(cfg.get("offset_y", self.var_offset_y.get())))
                self.var_orientation.set(cfg.get("orientation", self.var_orientation.get()))
        except Exception:
            pass
        self.work_list = []
        self.current_list_path = None  # Liste dosyası yolu (çıktı klasörü için)
        try:
            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                for line in f:
                    raw_line = line.strip()
                    if raw_line.startswith('"') and raw_line.endswith('"'):
                        raw_line = raw_line[1:-1]
                        raw_line = raw_line.replace('""', '"')
                    if len(raw_line) > 5:
                        self.work_list.append(raw_line)
            if self.work_list:
                first = self.work_list[0]
                if len(first) < 39:
                    self.var_mode.set("short"); self.apply_preset()
                    self.rb_long.config(state="disabled"); self.rb_short.config(state="normal")
                    self.lbl_file.config(text=f"✅ {os.path.basename(path)} ({len(self.work_list)}) [KISA KOD]", fg="yellow")
                else:
                    self.var_mode.set("long"); self.apply_preset()
                    self.rb_long.config(state="normal"); self.rb_short.config(state="normal")
                    self.lbl_file.config(text=f"✅ {os.path.basename(path)} ({len(self.work_list)}) [UZUN KOD]", fg="#00ff00")
            self.var_range_end.set(str(len(self.work_list)))
        except Exception as e: messagebox.showerror("Hata", str(e))

    def generate_zpl(self, raw_data):
        final_data = raw_data
        if len(raw_data) < 39: final_data = raw_data
        elif self.var_mode.get() == "short": final_data = self.parse_short_code(raw_data)
        
        dpi = self.var_dpi.get()
        scale = 8.0 if dpi == 203 else 11.81
        label_w_dots = int(self.var_label_w.get() * scale)
        label_h_dots = int(self.var_label_h.get() * scale)
        module_size = self.var_module_size.get()
        
        matrix_size = 32 * module_size 
        center_x = (label_w_dots - matrix_size) // 2
        center_y = (label_h_dots - matrix_size) // 2
        final_x = center_x + self.var_offset_x.get()
        final_y = center_y + self.var_offset_y.get()
        if final_x < 0: final_x = 0
        if final_y < 0: final_y = 0

        zpl = f"""
        ^XA
        ~SD{int(self.var_darkness.get()):02d}
        ^MD0
        ^PO{self.var_orientation.get()}
        ^PW{label_w_dots}
        ^LL{label_h_dots}
        ^FO{final_x},{final_y}
        ^BXN,{module_size},200
        ^FD{final_data}^FS
        ^XZ
        """
        return zpl

    def parse_short_code(self, text):
        if not text.startswith("01") or len(text) < 18: return text
        gtin = text[2:16]; remainder = text[16:]
        if remainder.startswith("21"):
            serial_raw = remainder[2:]; cut_index = len(serial_raw)
            for m in ["91", "92", "93", "11", "17"]:
                idx = serial_raw.find(m)
                if idx != -1 and idx < cut_index: cut_index = idx
            return f"01{gtin}21{serial_raw[:cut_index]}"
        return text

    def send_to_printer_stable(self, zpl_code):
        ip = self.var_ip.get()
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(3)
                s.connect((ip, 9100))
                s.sendall(zpl_code.encode('utf-8'))
                time.sleep(0.05) 
            return True
        except: return False

    def print_test_label(self):
        data = self.work_list[0] if self.work_list else '010123456789012821TEST91X'
        if self.send_to_printer_stable(self.generate_zpl(data)):
            self.lbl_status.config(text="Test Gönderildi", fg="#00ff00")
        else: messagebox.showerror("Hata", "Bağlantı Hatası")

    def toggle_pause(self):
        if self.is_paused:
            self.is_paused = False
            self.btn_pause.config(text="⏸️ DURAKLAT", bg="#ffc107")
            self.lbl_status.config(text="DEVAM EDİYOR...", fg="orange")
        else:
            self.is_paused = True
            self.btn_pause.config(text="▶️ DEVAM ET", bg="#0d6efd", fg="white")
            self.lbl_status.config(text="⏸️ DURAKLATILDI", fg="yellow")

    def cancel_print(self):
        if messagebox.askyesno("İptal", "Yazdırma işlemi iptal edilsin mi?"):
            self.stop_requested = True
            self.is_paused = False 

    def start_bulk_print(self):
        if self.is_printing: return
        if not self.work_list: return messagebox.showwarning("Uyarı", "Veri yok.")
        target_list = []
        if self.var_print_scope.get() == "all": target_list = self.work_list
        else:
            try:
                s = int(self.var_range_start.get()); e = int(self.var_range_end.get())
                if s < 1: s = 1
                target_list = self.work_list[s-1:e]
            except: return messagebox.showerror("Hata", "Geçersiz aralık!")

        if not messagebox.askyesno("Onay", f"{len(target_list)} adet basılacak.\nYazıcı hazır mı?"): return
        
        # BAŞLANGIÇTA UYKUYU ENGELLE
        self.prevent_system_sleep()
        
        self.is_printing = True; self.stop_requested = False; self.is_paused = False
        self.btn_start.config(state="disabled"); self.btn_pause.config(state="normal", text="⏸️ DURAKLAT", bg="#ffc107"); self.btn_cancel.config(state="normal")
        self.progress_bar["maximum"] = len(target_list); self.progress_bar["value"] = 0
        
        threading.Thread(target=self.print_loop, args=(target_list,), daemon=True).start()

    def print_loop(self, data_list):
        cnt = 0
        total = len(data_list)
        for i, data in enumerate(data_list):
            if self.stop_requested: self.end_process("❌ İPTAL EDİLDİ", "red"); return
            while self.is_paused:
                if self.stop_requested: self.end_process("❌ İPTAL EDİLDİ", "red"); return
                time.sleep(0.2)

            zpl = self.generate_zpl(data)
            
            # Smart Retry (Bağlantı Koparsa Tekrar Dene)
            success = False
            while not success:
                if self.stop_requested: self.end_process("❌ İPTAL EDİLDİ", "red"); return
                if self.send_to_printer_stable(zpl):
                    success = True
                    cnt += 1
                    percent = int((cnt / total) * 100)
                    self.root.after(0, lambda c=cnt, t=total, p=percent: self.update_live_ui(c, t, p))
                    time.sleep(0.08)
                else:
                    self.root.after(0, lambda: self.lbl_status.config(text="BAĞLANTI KOPTU! TEKRAR DENENİYOR...", fg="red"))
                    time.sleep(2)

        self.end_process("✅ TAMAMLANDI", "#00ff00")
        self.root.after(0, lambda: messagebox.showinfo("Bitti", "İşlem tamamlandı."))

    def update_live_ui(self, cnt, total, percent):
        self.progress_bar["value"] = cnt
        self.lbl_status.config(text=f"Basılıyor... %{percent} ({cnt}/{total})", fg="orange")
        self.root.update_idletasks() # EKRANI ZORLA GÜNCELLE

    def end_process(self, msg, color):
        # BİTİŞTE UYKUYU SERBEST BIRAK
        self.allow_system_sleep()
        
        self.is_printing = False
        self.stop_requested = False
        def _reset():
            self.lbl_status.config(text=msg, fg=color)
            self.btn_start.config(state="normal"); self.btn_pause.config(state="disabled"); self.btn_cancel.config(state="disabled")
        self.root.after(0, _reset)

if __name__ == "__main__":
    root = tk.Tk()
    app = ZebraApp(root)
    root.mainloop()