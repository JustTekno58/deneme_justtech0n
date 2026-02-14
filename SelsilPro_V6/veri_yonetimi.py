'''
Veri Yönetimi: SQLite + export + job backup + ayarlar.json okuma/yazma
'''
from __future__ import annotations

import csv
import io
import datetime
import json
import os
import sqlite3
import time
import unicodedata
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

DB_NAME = "SelsilPro.db"
DB_PATH = os.path.join(os.path.dirname(__file__), DB_NAME)

# -----------------------------
# Metin/etiket temizleme yardımcıları
# -----------------------------
def _sanitize_text(s: str) -> str:
    """Barkod/QR içeriği için en agresif ama güvenli temizlik.
    - NFKC normalize (Türkçe/Rusça karakterleri korur)
    - Görünmez/format kontrol karakterlerini kaldırır (GS1 için ASCII 29 hariç)
    - Satır sonlarını tek satıra indirger
    """
    if s is None:
        return ""
    s = str(s)

    # BOM ve tipik görünmezler
    s = s.replace("\ufeff", "").replace("\u200b", "").replace("\u200c", "").replace("\u200d", "").replace("\u2060", "")

    # Normalize
    s = unicodedata.normalize("NFKC", s)

    out = []
    for ch in s:
        o = ord(ch)
        if o == 29:  # GS (Group Separator) - GS1 için önemli
            out.append(ch)
            continue
        cat = unicodedata.category(ch)
        # C*: control/format/surrogate/private-use/unassigned
        if cat.startswith("C"):
            continue
        # Tek satır
        if ch in ("\r", "\n", "\t"):
            continue
        out.append(ch)
    return "".join(out).strip()


def _read_lines_any_encoding(path: str) -> list[str]:
    """Etiket dosyalarını farklı encoding'lerle okumayı dener."""
    encodings = ["utf-8-sig", "utf-8", "cp1254", "cp1251", "latin-1"]
    last_err = None
    for enc in encodings:
        try:
            with open(path, "r", encoding=enc, errors="strict") as f:
                return f.read().splitlines()
        except Exception as e:
            last_err = e
            continue
    # Son çare: ignore
    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        return f.read().splitlines()



def _read_barcode_records(path: str) -> list[str]:
    """CSV/TXT içinden barkod kayıtlarını okur ve gerekirse çok satırlı GS1 parçalarını birleştirir.

    Bazı exportlarda GS1 barkod tek satır yerine:
      01...  (ana satır)
      93...
      91...
    şeklinde ayrı satırlar halinde gelebilir. Bu fonksiyon, 01 ile başlayan satırı
    kayıt başlangıcı kabul eder ve devam satırlarını ASCII 29 (GS) ile birleştirir.
    """
    # 1) Dosyayı tüm metin olarak oku (encoding fallback)
    encodings = ["utf-8-sig", "utf-8", "cp1254", "cp1251", "latin-1"]
    raw_text = None
    last_err = None
    for enc in encodings:
        try:
            with open(path, "r", encoding=enc, errors="strict") as f:
                raw_text = f.read()
            break
        except Exception as e:
            last_err = e
            continue
    if raw_text is None:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            raw_text = f.read()

    # 2) CSV ayracını algıla ve hücreleri çıkar (olmazsa satır satır devam et)
    values: list[str] = []
    try:
        sample = raw_text[:4096]
        sniffer = csv.Sniffer()
        dialect = sniffer.sniff(sample, delimiters=";,\t|")
        reader = csv.reader(io.StringIO(raw_text), dialect)
        for row in reader:
            if not row:
                continue
            # satırdaki ilk dolu hücreyi al
            cell = ""
            for c in row:
                c = (c or "").strip()
                if c:
                    cell = c
                    break
            if cell:
                values.append(cell)
    except Exception:
        # CSV değilse: satır satır
        for line in raw_text.splitlines():
            line = (line or "").strip()
            if line:
                values.append(line)

    # 3) Temizle + header satırlarını atla
    cleaned: list[str] = []
    for v in values:
        vv = _sanitize_text(v)
        if not vv:
            continue
        low = vv.lower()
        if low in ("barkod", "barcode", "datamatrix", "code", "kod") or "barkod" in low:
            continue
        cleaned.append(vv)

    # 4) Çok satırlı GS1 parçalarını birleştir
    merged: list[str] = []
    cur = ""
    for v in cleaned:
        is_new = v.startswith("01") and len(v) >= 16
        if is_new:
            if cur:
                merged.append(cur)
            cur = v
            continue
        # devam satırı
        if cur:
            cur = f"{cur}{chr(29)}{v}"
        else:
            # dosya 01 ile başlamıyorsa yine de kayıt yap
            cur = v
    if cur:
        merged.append(cur)

    return merged


class VeriYonetimi:
    def __init__(self, app):
        self.app = app
        self.conn = None
        self.cursor = None
        self.settings = {}

    def load_settings(self):
        defaults_path = os.path.join(os.path.dirname(__file__), "ayarlar.json")
        if os.path.exists(defaults_path):
            try:
                with open(defaults_path, "r", encoding="utf-8") as f:
                    self.settings = json.load(f)
            except Exception:
                self.settings = {}
        else:
            self.settings = {}

        # çalışma klasöründeki ayarlar.json override
        if os.path.exists("ayarlar.json"):
            try:
                with open("ayarlar.json", "r", encoding="utf-8") as f:
                    data = json.load(f)
                self.settings.update(data)
            except Exception:
                pass

    
        # --- Ayar anahtarı uyumluluğu (eski/yeni) ---
        # Bazı sürümlerde anahtar adları farklı kaydedilmiş olabilir.
        key_map = {
            "prod_width_mm": "prod_w",
            "prod_height_mm": "prod_h",
            "prod_x_mm": "prod_x",
            "prod_y_mm": "prod_y",
            "box_width_mm": "box_w",
            "box_height_mm": "box_h",
            "box_x_mm": "box_x",
            "box_y_mm": "box_y",
            "box_printer_ip": "box_ip",
            "box_printer_port": "box_port",
            "prod_printer_ip": "prod_ip",
            "prod_printer_port": "prod_port",
            "reject_com": "reject_port",
            "reject_duration_s": "reject_duration",
            "reject_delay_s": "reject_delay",
            "prod2_printer_ip": "prod2_ip",
            "prod2_printer_port": "prod2_port",
        }
        for src, dst in key_map.items():
            if src in self.settings and dst not in self.settings:
                self.settings[dst] = self.settings.get(src)
        # varsayılanlar
        self.settings.setdefault("prod_darkness", 20)
        self.settings.setdefault("prod_x", 0)
        self.settings.setdefault("prod_y", 0)
        self.settings.setdefault("prod_module", 6)
        self.settings.setdefault("box_darkness", 20)
        self.settings.setdefault("box_x", 0)
        self.settings.setdefault("box_y", 0)
        self.settings.setdefault("box_copies", 1)
        self.settings.setdefault("printer_enabled", 1)

        # --- UI / Dizayn varsayılanları ---
        self.settings.setdefault("ui_theme", "light")      # light | dark
        self.settings.setdefault("ui_font_family", "Segoe UI")
        self.settings.setdefault("ui_font_size", 9)
        self.settings.setdefault("ui_dashboard_layout", "A")  # A | B
        # sash konumları (piksel)
        self.settings.setdefault("sash_upload", 0)
        self.settings.setdefault("sash_files", 0)
        self.settings.setdefault("sash_bottom", 0)

    def save_settings(self):
        # UI bağlı ayarlar
        try:
            self.settings["short_code"] = int(self.app.var_short_code.get())
        except Exception:
            pass
        try:
            self.settings["date_required"] = int(self.app.var_date_required.get())
            self.settings["production_date"] = str(self.app.var_prod_date.get() or "")
        except Exception:
            pass
        try:
            self.settings["printer_enabled"] = int(self.app.var_printer_enabled.get())
        except Exception:
            pass
        with open("ayarlar.json", "w", encoding="utf-8") as f:
            json.dump(self.settings, f, ensure_ascii=False, indent=2)

    def init_db(self):
        self.conn = sqlite3.connect(DB_PATH, check_same_thread=False)
        self.cursor = self.conn.cursor()
        self.cursor.execute(
            '''CREATE TABLE IF NOT EXISTS jobs
               (filename TEXT PRIMARY KEY, work_list TEXT, box_labels TEXT,
                count INTEGER, box_size INTEGER, last_updated TEXT)'''
        )
        self.conn.commit()

    def save_job_db(self):
        if not self.app.current_file:
            return
        data = {"list": [item for item in self.app.work_list], "labels": self.app.box_label_list}
        try:
            self.cursor.execute(
                "INSERT OR REPLACE INTO jobs VALUES (?, ?, ?, ?, ?, ?)",
                (
                    self.app.current_file,
                    json.dumps(data, ensure_ascii=False),
                    json.dumps(self.app.box_label_list, ensure_ascii=False),
                    self.app.verified_count,
                    self.app.items_per_box,
                    str(time.time()),
                )
            )
            self.conn.commit()
        except Exception:
            pass

    def load_last_job(self):
        try:
            self.cursor.execute("SELECT * FROM jobs ORDER BY last_updated DESC LIMIT 1")
            row = self.cursor.fetchone()
            if row:
                if messagebox.askyesno("Devam Et", f"Son çalışma bulundu: {row[0]}\nDevam etmek ister misiniz?"):
                    filename = row[0]
                    # Öncelik: Job V2 üzerinden yükle (migration varsa legacy::<filename> olarak bulunur)
                    try:
                        job_id = f"legacy::{filename}"
                        if hasattr(self.app, "load_job_v2"):
                            ok = self.app.load_job_v2(job_id)
                            if ok:
                                # V2 yüklediysek legacy alanlarını ayrıca doldurma
                                return
                    except Exception:
                        pass

                    # Fallback: Eski V3 formatı (doğrudan work_list)
                    self.app.current_file = filename
                    data = json.loads(row[1])
                    if isinstance(data, dict) and "list" in data:
                        self.app.work_list = data["list"]
                    else:
                        self.app.work_list = data

                    try:
                        self.app.box_label_list = json.loads(row[2])
                    except Exception:
                        self.app.box_label_list = []

                    self.app.verified_count = row[3]
                    self.app.items_per_box = row[4]
                    # UI alan adı değişti: entry_box_size -> entry_koli_adet
                    try:
                        if hasattr(self.app, 'entry_koli_adet') and self.app.entry_koli_adet is not None:
                            self.app.entry_koli_adet.delete(0, tk.END)
                            self.app.entry_koli_adet.insert(0, str(self.app.items_per_box))
                    except Exception:
                        pass

                    self.app.btn_prod.config(text=f"✅ ÜRÜN: {self.app.current_file}", bg="#d1e7dd", fg="#0f5132")
                    saved_box_name = self.settings.get("last_box_filename", "")
                    if saved_box_name and self.app.box_label_list:
                        self.app.btn_box.config(text=f"🏷️ KOLİ: {saved_box_name}", bg="#d1e7dd", fg="#0f5132")
                    elif self.app.box_label_list:
                        self.app.btn_box.config(text=f"🏷️ {len(self.app.box_label_list)} ETİKET (İsimsiz)", bg="#d1e7dd", fg="#0f5132")

                    # UI yenile
                    if hasattr(self.app, 'refresh_all'):
                        self.app.refresh_all()
                    else:
                        if hasattr(self.app, 'refresh_table'):
                            self.app.refresh_table()
                        if hasattr(self.app, 'update_ui'):
                            self.app.update_ui()
        except Exception:
            pass

    def auto_backup_current_job(self):
        if not self.app.work_list:
            return
        ts = datetime.datetime.now().strftime("%Y%m%d_%H%M")
        work_dir = self.settings.get("work_dir", os.getcwd())
        if not os.path.exists(work_dir):
            work_dir = os.getcwd()
        base_name = os.path.splitext(self.app.current_file)[0]

        finished = [i for i in self.app.work_list if i['status'] == 'VERIFIED']
        if finished:
            try:
                finished.sort(key=lambda x: int(x['box']) if str(x['box']).isdigit() else 999999)
            except Exception:
                pass
            path = os.path.join(work_dir, f"{base_name}_OTO_YEDEK_DETAY_{ts}.csv")
            try:
                with open(path, "w", newline='', encoding="utf-8") as f:
                    writer = csv.writer(f, delimiter=';')
                    writer.writerow(["ID", "Koli", "Koli Etiketi", "Durum", "Barkod"])
                    for item in finished:
                        writer.writerow([item.get('id'), item.get('box'), item.get('label'), item.get('status'), item.get('raw')])
            except Exception:
                pass

        remaining = [i for i in self.app.work_list if i['status'] == 'PENDING']
        if remaining:
            path = os.path.join(work_dir, f"{base_name}_OTO_YEDEK_KALAN_{ts}.csv")
            try:
                with open(path, "w", newline='', encoding="utf-8") as f:
                    for item in remaining:
                        f.write(f"{item['raw']}\n")
            except Exception:
                pass

    def load_file(self, ftype: str):
        path = filedialog.askopenfilename(filetypes=[("Data", "*.csv;*.txt")])
        if not path:
            return

        file_dir = os.path.dirname(path)
        self.settings["work_dir"] = file_dir
        self.save_settings()

        filename = os.path.basename(path)

        if ftype == 'prod' and self.app.work_list:
            self.auto_backup_current_job()
            messagebox.showinfo("Oto Yedek", "⚠️ Önceki işin dosyaları otomatik yedeklendi.\n(Klasörde 'OTO_YEDEK' adıyla bulabilirsiniz.)")

        new_data_list = []
        try:
            new_data_list = _read_barcode_records(path)

            # Yüklenen dosyanın kod türünü örnekleyerek algıla
            try:
                sample = [x for x in new_data_list if str(x).strip()][:50]
                counts = {}
                for x in sample:
                    try:
                        info = code_parser.analyze(str(x))
                        counts[info.code_type] = counts.get(info.code_type, 0) + 1
                    except Exception:
                        pass
                # Eğer dosyada en az 1 adet SHORTKOD varsa kullanıcı açısından SHORTKOD kabul et.
                # (Chestny ZNAK dosyalarında bazı satırlar kontrol/boşluk vb. nedeniyle PLAIN görünebilir.)
                if counts.get("GS1_SHORT", 0) > 0:
                    detected = "GS1_SHORT"
                else:
                    detected = max(counts, key=counts.get) if counts else "PLAIN"
                self.app.loaded_code_type = detected
                if hasattr(self.app, 'update_loaded_code_type'):
                    self.app.update_loaded_code_type(detected)
            except Exception:
                pass

        except Exception as e:
            messagebox.showerror("Hata", f"Dosya okunamadı: {e}")
            return


        if ftype == 'prod':
            # Ürün seçimi sonrası: Palet/Koli/Tarih sihirbazı (modal)
            try:
                wiz = None
                if hasattr(self.app, 'run_product_wizard'):
                    wiz = self.app.run_product_wizard({
                        'palet_count': self.settings.get('palet_count', 0),
                        'palet_icerik': self.settings.get('palet_icerik', 0),
                        'koli_adet': self.settings.get('koli_adet', getattr(self.app, 'items_per_box', 0)),
                        'prod_date': self.settings.get('production_date', ''),
                    })
                if wiz is None:
                    wiz = {}  # İptal edilse de ürün yüklemeye devam et
                # Uygula
                try:
                    self.app.palet_count = int(wiz.get('palet_count',0) or 0)
                except Exception:
                    self.app.palet_count = 0
                try:
                    self.app.palet_icerik = int(wiz.get('palet_icerik',0) or 0)
                except Exception:
                    self.app.palet_icerik = 0
                try:
                    self.app.palet_total = int(self.app.palet_count) * int(self.app.palet_icerik)
                except Exception:
                    self.app.palet_total = 0
                try:
                    if hasattr(self.app,'lbl_palet_adet'): self.app.lbl_palet_adet.config(text=str(self.app.palet_count))
                    if hasattr(self.app,'lbl_palet_icerik'): self.app.lbl_palet_icerik.config(text=str(self.app.palet_icerik))
                    if hasattr(self.app,'lbl_palet_toplam'): self.app.lbl_palet_toplam.config(text=str(self.app.palet_total))
                except Exception:
                    pass
                # Koli içi adet
                try:
                    koli_adet = int(wiz.get('koli_adet',0) or 0)
                    if koli_adet > 0:
                        self.app.items_per_box = koli_adet
                        if hasattr(self.app,'entry_koli_adet') and self.app.entry_koli_adet:
                            self.app.entry_koli_adet.delete(0,'end'); self.app.entry_koli_adet.insert(0,str(koli_adet))
                except Exception:
                    pass
                # Tarih
                try:
                    prod_date = (wiz.get('prod_date') or '').strip()
                    self.settings['production_date'] = prod_date
                    try: self.app.var_prod_date.set(prod_date)
                    except Exception: pass
                    if hasattr(self.app,'entry_date') and self.app.entry_date:
                        self.app.entry_date.delete(0,'end'); self.app.entry_date.insert(0,prod_date)
                except Exception:
                    pass
                # sonraki açılış için varsayılanları kaydet
                try:
                    self.settings["palet_count"] = getattr(self.app, "palet_count", 0)
                    self.settings["palet_icerik"] = getattr(self.app, "palet_icerik", 0)
                    self.settings["koli_adet"] = getattr(self.app, "items_per_box", 0)
                except Exception:
                    pass
                self.save_settings()
            except Exception:
                pass
            self.app.current_file = filename
            self.app.work_list = []
            self.app.verified_count = 0
            uid = 1
            for clean_data in new_data_list:
                search_val = _sanitize_text(clean_data)
                self.app.work_list.append({
                    "id": uid,
                    "raw": clean_data,
                    "raw_disp": clean_data.replace(chr(29), "|"),
                    "search": search_val,
                    "search_nogs": search_val.replace(chr(29), ""),
                    "status": "PENDING",
                    "box": "-",
                    "label": "-"
                })
                uid += 1

            self.app.btn_prod.config(text=f"✅ ÜRÜN: {filename}", bg="#d1e7dd", fg="#0f5132")
            if hasattr(self.app, 'refresh_all'):
                self.app.refresh_all()
            elif hasattr(self.app, 'refresh_table'):
                self.app.refresh_table()

            # --- Job V2: yüklenen ürün listesini DB'ye yaz ve aktif job yap ---
            try:
                jm = getattr(self.app, "job_manager", None)
                if jm is not None:
                    # mevcut box dosyası / ayarlar
                    box_file = getattr(self.app, "current_box_file", "") or self.settings.get("last_box_filename", "") or ""
                    try:
                        settings = self.app._collect_job_settings() if hasattr(self.app, "_collect_job_settings") else dict(self.settings)
                    except Exception:
                        settings = dict(self.settings)

                    try:
                        current_koli_no = int(getattr(self.app, "next_print_info", {}).get("box_num", 1) or 1)
                    except Exception:
                        current_koli_no = 1

                    # iş adı: ürün dosyası + zaman (çakışmayı önler)
                    try:
                        import datetime as _dt
                        ts = _dt.datetime.now().strftime("%Y%m%d_%H%M%S")
                    except Exception:
                        ts = str(int(time.time()))
                    job_name = f"{filename} ({ts})"

                    job_id = jm.create_job(job_name, filename, box_file, settings, current_koli_no=current_koli_no)
                    jm.upsert_items_from_work_list(job_id, self.app.work_list)
                    jm.set_active_job(job_id)
                    self.app.current_job_id = job_id
            except Exception:
                # Job sistemi çalışmasa bile UI devam etsin
                pass

        elif ftype == 'box':
            self.app.box_label_list = new_data_list
            self.app.btn_box.config(text=f"🏷️ KOLİ: {filename}", bg="#d1e7dd", fg="#0f5132")
            try:
                self.app.current_box_file = filename
                # Job başlığı box dosyası ile güncellensin
                if getattr(self.app,'current_job_id',None) and getattr(self.app,'job_manager',None) is not None:
                    self.app.job_manager.update_header(self.app.current_job_id, settings=self.app._collect_job_settings(), current_koli_no=int(self.app.next_print_info.get('box_num',1) or 1))
            except Exception:
                pass
            self.settings["last_box_filename"] = filename
            self.save_settings()

        self.save_job_db()
        if hasattr(self.app, 'refresh_all'):
            self.app.refresh_all()
        elif hasattr(self.app, 'update_ui'):
            self.app.update_ui()

    def get_export_path(self, suffix: str):
        work_dir = self.settings.get("work_dir", "")
        if not work_dir or not os.path.exists(work_dir):
            work_dir = os.getcwd()
        base_name = os.path.splitext(self.app.current_file)[0]
        filename = f"{base_name}_{suffix}.csv"
        return os.path.join(work_dir, filename), work_dir

    def export_finished(self, silent: bool = False):
        finished_items = [i for i in self.app.work_list if i['status'] == 'VERIFIED']
        if not finished_items:
            if not silent:
                return messagebox.showinfo("Bilgi", "Veri yok.")
        try:
            finished_items.sort(key=lambda x: int(x['box']) if str(x['box']).isdigit() else 999999)
        except Exception:
            pass
        full_path, work_dir = self.get_export_path("finish")
        try:
            with open(full_path, "w", newline='', encoding="utf-8") as f:
                writer = csv.writer(f, delimiter=';')
                for item in finished_items:
                    writer.writerow([item.get('box'), item.get('label'), item.get('raw')])
            if not silent:
                messagebox.showinfo("Başarılı", f"Kaydedildi\\n{full_path}")
            if not silent:
                try:
                    os.startfile(work_dir)
                except Exception:
                    pass
        except Exception as e:
            messagebox.showerror("Hata", str(e))

    def export_finished_single(self, silent: bool = False):
        finished_items = [i for i in self.app.work_list if i['status'] == 'VERIFIED']
        if not finished_items:
            if not silent:
                return messagebox.showinfo("Bilgi", "Veri yok.")
        finished_items.sort(key=lambda x: x['id'])
        full_path, work_dir = self.get_export_path("bitenlertekli")
        try:
            with open(full_path, "w", newline='', encoding="utf-8") as f:
                for item in finished_items:
                    f.write(f"{item['raw']}\n")
            if not silent:
                messagebox.showinfo("Başarılı", f"Kaydedildi\\n{full_path}")
            if not silent:
                try:
                    os.startfile(work_dir)
                except Exception:
                    pass
        except Exception as e:
            messagebox.showerror("Hata", str(e))

    def export_remaining(self, silent: bool = False):
        remaining_items = [i for i in self.app.work_list if i['status'] == 'PENDING']
        if not remaining_items:
            if not silent:
                return messagebox.showinfo("Bilgi", "Veri yok.")
        remaining_items.sort(key=lambda x: x['id'])
        full_path, work_dir = self.get_export_path("okunmayanlar")
        try:
            with open(full_path, "w", newline='', encoding="utf-8") as f:
                for item in remaining_items:
                    f.write(f"{item['raw']}\n")
            if not silent:
                messagebox.showinfo("Başarılı", f"Kaydedildi\\n{full_path}")
            if not silent:
                try:
                    os.startfile(work_dir)
                except Exception:
                    pass
        except Exception as e:
            messagebox.showerror("Hata", str(e))


    def export_all_three(self, silent: bool = False):
        """Bitenler (Detay) + Bitenler (Tekli) + Kalanlar raporlarını aynı anda üretir."""
        self.export_finished(silent=True if silent else False)
        self.export_finished_single(silent=True if silent else False)
        self.export_remaining(silent=True if silent else False)
        if not silent:
            try:
                messagebox.showinfo("Başarılı", "3 rapor üretildi (Detay + Tekli + Kalanlar).")
            except Exception:
                pass

    
    def open_history_window(self):
        """Geçmiş İşler: Job System (V2) ile geri çağır / kopyala."""
        try:
            from job_yonetimi import JobYonetimi
        except Exception:
            messagebox.showerror("Hata", "Job sistemi bulunamadı (job_yonetimi.py eksik).")
            return

        jm = None
        try:
            jm = JobYonetimi()
        except Exception as e:
            messagebox.showerror("Hata", f"Veritabanı açılamadı: {e}")
            return

        win = tk.Toplevel(self.app.root)
        win.title("Geçmiş İşler")
        win.geometry("900x520")
        win.resizable(True, True)

        frm = ttk.Frame(win, padding=10)
        frm.pack(fill="both", expand=True)

        ttk.Label(frm, text="Geçmiş İşler", font=("Segoe UI", 14, "bold")).pack(anchor="w", pady=(0, 8))

        cols = ("Durum", "İş Adı", "Ürün Dosyası", "Koli Dosyası", "Güncelleme", "JobId")
        tree = ttk.Treeview(frm, columns=cols, show="headings", height=18)
        for c, w in zip(cols, (90, 260, 190, 190, 120, 0)):
            tree.heading(c, text=c)
            tree.column(c, width=w, anchor="w")
        tree.column("JobId", width=0, stretch=False)
        tree.pack(fill="both", expand=True)

        def refresh():
            tree.delete(*tree.get_children())
            jobs = jm.list_jobs()
            for j in jobs:
                try:
                    upd = j.updated_at
                except Exception:
                    upd = ""
                tree.insert("", "end", values=(j.status, j.job_name, j.prod_file, j.box_file, upd, j.job_id))

        refresh()

        btns = ttk.Frame(frm)
        btns.pack(fill="x", pady=(10, 0))

        def get_selected_job_id():
            sel = tree.selection()
            if not sel:
                return None
            vals = tree.item(sel[0], "values") or ()
            if len(vals) < 6:
                return None
            return vals[5]

        def devam_et():
            jid = get_selected_job_id()
            if not jid:
                messagebox.showwarning("Uyarı", "Lütfen bir iş seçin.")
                return
            if hasattr(self.app, "load_job_v2") and self.app.load_job_v2(jid):
                try:
                    win.destroy()
                except Exception:
                    pass

        def kopyala_yeni_is():
            jid = get_selected_job_id()
            if not jid:
                messagebox.showwarning("Uyarı", "Lütfen bir iş seçin.")
                return
            header, items = jm.load_job(jid)
            if header is None:
                messagebox.showerror("Hata", "İş bulunamadı.")
                return
            # yeni iş: aynı dosyalar, aynı ayarlar, fakat okumalar PENDING'e çekilir
            try:
                settings = json.loads(header.settings_json or "{}")
                new_name = f"{header.job_name} - Kopya"
                new_jid = jm.create_job(new_name, header.prod_file, header.box_file, settings, current_koli_no=1)
                # items kopyala ama okunmamış
                for it in items:
                    it["status"] = "PENDING"
                    it["box"] = "-"
                    it["label"] = "-"
                    it["in_box"] = ""
                jm.upsert_items_from_work_list(new_jid, items)
                jm.set_active_job(new_jid)
                if hasattr(self.app, "load_job_v2"):
                    self.app.load_job_v2(new_jid)
                win.destroy()
            except Exception as e:
                messagebox.showerror("Hata", f"Kopyalama başarısız: {e}")

        ttk.Button(btns, text="Devam Et", command=devam_et).pack(side="left")
        ttk.Button(btns, text="Kopyala (Yeni İş)", command=kopyala_yeni_is).pack(side="left", padx=8)
        ttk.Button(btns, text="Yenile", command=refresh).pack(side="right")



    def delete_job(self):
        if not self.app.current_file:
            return
        if messagebox.askyesno("Sil", "Mevcut iş silinsin mi?"):
            self.cursor.execute("DELETE FROM jobs WHERE filename=?", (self.app.current_file,))
            self.conn.commit()
            self.app.work_list = []
            self.app.box_label_list = []
            self.app.verified_count = 0
            self.app.current_file = "YeniIs"
            self.app.btn_prod.config(text="📦 1. ÜRÜN LİSTESİ", bg="white", fg="black")
            self.app.btn_box.config(text="🏷️ 2. KOLİ ETİKETLERİ", bg="white", fg="black")
            self.settings["last_box_filename"] = ""
            self.save_settings()
            if hasattr(self.app, 'refresh_all'):
                self.app.refresh_all()
            elif hasattr(self.app, 'refresh_table'):
                self.app.refresh_table()
        if hasattr(self.app, 'refresh_all'):
            self.app.refresh_all()
        elif hasattr(self.app, 'update_ui'):
            self.app.update_ui()


    def export_pdf_report(self, silent: bool = False):
        """Basit PDF raporu üretir (Bitenler + Kalanlar özet)."""
        try:
            from reportlab.lib.pagesizes import A4
            from reportlab.pdfgen import canvas
        except Exception:
            return messagebox.showerror("Hata", "PDF için 'reportlab' kütüphanesi gerekli. Lütfen tekrar çalıştırın; kurulum otomatik yapılacaktır.")

        finished = [i for i in self.app.work_list if i.get('status') == 'VERIFIED']
        remaining = [i for i in self.app.work_list if i.get('status') == 'PENDING']

        if not finished and not remaining:
            if not silent:
                return messagebox.showinfo("Bilgi", "Veri yok.")
            return

        full_path, work_dir = self.get_export_path("rapor_pdf")
        # uzantıyı pdf yap
        if not full_path.lower().endswith(".pdf"):
            full_path = os.path.splitext(full_path)[0] + ".pdf"

        try:
            c = canvas.Canvas(full_path, pagesize=A4)
            w, h = A4
            y = h - 40

            def line(txt, step=16, bold=False):
                nonlocal y
                if y < 60:
                    c.showPage()
                    y = h - 40
                c.setFont("Helvetica-Bold" if bold else "Helvetica", 11 if bold else 10)
                c.drawString(40, y, txt)
                y -= step

            line("SELSIL PRO - PDF RAPORU", step=20, bold=True)
            line(datetime.datetime.now().strftime("Tarih: %d.%m.%Y %H:%M"))
            line(f"Toplam Kayıt: {len(self.app.work_list)}")
            line(f"Biten (VERIFIED): {len(finished)}")
            line(f"Kalan (PENDING): {len(remaining)}")
            line("")

            # Örnek ilk 40 satır (bitenler)
            if finished:
                line("BİTENLER (İlk 40)", step=18, bold=True)
                for it in finished[:40]:
                    raw = str(it.get("raw", ""))[:120]
                    line(f"- {it.get('box','-')} | {it.get('label','-')} | {raw}")

            if remaining:
                line("")
                line("KALANLAR (İlk 40)", step=18, bold=True)
                for it in remaining[:40]:
                    raw = str(it.get("raw", ""))[:120]
                    line(f"- {it.get('id','-')} | {raw}")

            c.save()

            if not silent:
                messagebox.showinfo("Başarılı", f"PDF kaydedildi\n{full_path}")
                try:
                    os.startfile(work_dir)
                except Exception:
                    pass
        except Exception as e:
            messagebox.showerror("Hata", str(e))