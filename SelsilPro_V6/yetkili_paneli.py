'''
Yetkili Paneli (Ayarlar / Yönetim)

- Ayarlar Penceresi: yazdırma ölçüleri + koyuluk + konum + tablo sütun görünürlüğü
- Yönetici Paneli: şifreli; kritik IP/Port + Reject süre/gecikme + silme işlemleri

Bu modül, ana ekrandan çağrılan isimler için geriye dönük uyumluluk sağlar:
open_ayarlar_penceresi / require_password_then / open_yonetici_paneli
'''
from __future__ import annotations

import hashlib
import tkinter as tk
from tkinter import ttk, messagebox

try:
    import dizayn
except Exception:
    dizayn = None


def _sha256(s: str) -> str:
    return hashlib.sha256(s.encode('utf-8')).hexdigest()


class YetkiliPaneli:
    def __init__(self, app):
        self.app = app
        self._settings_win = None
        self._admin_win = None
        self._delete_win = None

    # -----------------------------
    # Pencere yardımcıları
    # -----------------------------
    def _bring_to_front(self, win: tk.Toplevel):
        """Pencereyi öne getirir.

        Kullanıcı "daima üstte" istemiyor; sadece açıldığında/işlem sonrası
        öne gelsin istiyor. Bu yüzden '-topmost' sadece KISA süreli kullanılır.
        """
        try:
            win.deiconify()
        except Exception:
            pass
        try:
            win.lift()
            win.focus_force()
        except Exception:
            pass
        # Kısa süreli üstte tut (odak sorunlarını çözer), sonra normale dön.
        try:
            win.attributes('-topmost', True)
            win.after(200, lambda: win.attributes('-topmost', False))
        except Exception:
            pass

    # -----------------------------
    # Geriye dönük uyumluluk
    # -----------------------------
    def open_ayarlar_penceresi(self):
        return self.open_settings()

    def open_settings(self):
        return self.open_settings_window()

    def open_yonetici_paneli(self):
        return self._open_admin_window()

    def require_password_then(self, on_success):
        """Şifre doğruysa verilen callback'i çalıştırır."""
        s = self.app.veri.settings

        default_hash = _sha256("2546")
        expected = s.get("admin_password_hash")

        # Kullanıcı isteği: varsayılan şifre 2546. Eski varsayılan (1234) kayıtlıysa güncelle.
        try:
            if expected == _sha256("1234"):
                expected = _sha256("2546")
                s["admin_password_hash"] = expected
                self.app.veri.save_settings()
        except Exception:
            pass

        # Eski anahtar varsa migrate et
        if not expected and s.get("admin_password"):
            expected = _sha256(str(s["admin_password"]))
            s["admin_password_hash"] = expected
            s.pop("admin_password", None)
            self.app.veri.save_settings()

        if not expected:
            expected = default_hash
            s["admin_password_hash"] = expected
            self.app.veri.save_settings()

        # Şifre penceresi açıksa tekrar açma, öne getir.
        if self._settings_win is not None:
            try:
                if self._settings_win.winfo_exists():
                    self._bring_to_front(self._settings_win)
                    return
            except Exception:
                pass
            self._settings_win = None

        win = tk.Toplevel(self.app.root)
        self._settings_win = win
        try:
            win.transient(self.app.root)
        except Exception:
            pass
        def _on_close():
            try:
                self._settings_win = None
            except Exception:
                pass
            win.destroy()
        win.protocol('WM_DELETE_WINDOW', _on_close)
        win.title("Yönetici Girişi")
        win.geometry("360x180")
        win.resizable(False, False)
        win.grab_set()
        self._bring_to_front(win)

        tk.Label(win, text="Yönetici Şifresi", font=("Segoe UI", 11, "bold")).pack(pady=(16, 8))
        ent = tk.Entry(win, show="*", font=("Segoe UI", 12), justify="center")
        ent.pack(padx=24, fill="x")
        ent.focus_set()

        tk.Label(win, text="Varsayılan: 2546", fg="#6c757d").pack(pady=(6, 0))

        def submit():
            pwd = ent.get().strip()
            if not pwd:
                return messagebox.showwarning("Uyarı", "Şifre giriniz.")
            if _sha256(pwd) == expected:
                win.destroy()
                try:
                    on_success()
                except Exception as ex:
                    messagebox.showerror("Hata", str(ex))
            else:
                messagebox.showerror("Hata", "Şifre hatalı!")

        btns = tk.Frame(win)
        btns.pack(pady=14)
        tk.Button(btns, text="Giriş", width=10, bg="#198754", fg="white", command=submit).pack(side="left", padx=8)
        tk.Button(btns, text="İptal", width=10, command=win.destroy).pack(side="left", padx=8)
        win.bind("<Return>", lambda _e: submit())

    # -----------------------------
    # AYARLAR (operasyonel)
    # -----------------------------
    def open_settings_window(self):
        s = self.app.veri.settings

        # Aynı pencereyi tekrar tekrar açma: varsa öne getir
        if self._settings_win is not None:
            try:
                if self._settings_win.winfo_exists():
                    self._bring_to_front(self._settings_win)
                    return self._settings_win
            except Exception:
                pass
            self._settings_win = None

        win = tk.Toplevel(self.app.root)
        self._settings_win = win
        try:
            win.transient(self.app.root)
        except Exception:
            pass
        def _on_close():
            try:
                self._settings_win = None
            except Exception:
                pass
            win.destroy()
        win.protocol('WM_DELETE_WINDOW', _on_close)
        self._bring_to_front(win)
        win.title("Ayarlar")
        # Pencere boyutu içerik bazlı ayarlanır (gereksiz boşlukları azaltır)
        win.resizable(False, False)

        tk.Label(win, text="Gelişmiş Yazdırma Ayarları", font=("Segoe UI", 12, "bold")).pack(pady=(14, 8))

        # Ürün
        frm_prod = tk.LabelFrame(win, text="Ürün Etiketi (ZT411 (1))", padx=10, pady=10)
        frm_prod.pack(fill="x", padx=14, pady=8)

        prod_w = tk.StringVar(value=str(s.get("prod_w", 50)))
        prod_h = tk.StringVar(value=str(s.get("prod_h", 30)))
        prod_dark = tk.StringVar(value=str(s.get("prod_darkness", 20)))
        prod_x = tk.StringVar(value=str(s.get("prod_x", 0)))
        prod_y = tk.StringVar(value=str(s.get("prod_y", 0)))
        prod_module = tk.StringVar(value=str(s.get("prod_module", 6)))

        row = 0
        tk.Label(frm_prod, text="Genişlik (mm):").grid(row=row, column=0, sticky="w")
        tk.Entry(frm_prod, textvariable=prod_w, width=8).grid(row=row, column=1, padx=6)
        tk.Label(frm_prod, text="Yükseklik (mm):").grid(row=row, column=2, sticky="w")
        tk.Entry(frm_prod, textvariable=prod_h, width=8).grid(row=row, column=3, padx=6)

        row += 1
        tk.Label(frm_prod, text="Koyuluk:").grid(row=row, column=0, sticky="w", pady=(6,0))
        tk.Entry(frm_prod, textvariable=prod_dark, width=8).grid(row=row, column=1, padx=6, pady=(6,0))
        tk.Label(frm_prod, text="Konum X (mm):").grid(row=row, column=2, sticky="w", pady=(6,0))
        tk.Entry(frm_prod, textvariable=prod_x, width=8).grid(row=row, column=3, padx=6, pady=(6,0))
        row += 1
        tk.Label(frm_prod, text="DM Modül:").grid(row=row, column=0, sticky="w", pady=(6,0))
        tk.Spinbox(frm_prod, from_=2, to=10, textvariable=prod_module, width=6).grid(row=row, column=1, padx=6, pady=(6,0))
        tk.Label(frm_prod, text="Konum Y (mm):").grid(row=row, column=2, sticky="w", pady=(6,0))
        tk.Entry(frm_prod, textvariable=prod_y, width=8).grid(row=row, column=3, padx=6, pady=(6,0))

        # Ürün etiketi için varsayılan ayarla (pencere kapanmaz)
        tk.Button(frm_prod, text="Varsayılan olarak ayarla", bg="#f39c12", fg="white", activebackground="#f5b041", command=lambda: _apply_prod()).grid(row=0, column=4, rowspan=3, padx=(18,0), sticky="ns")

        # Ürün (Yedek / 2)
        frm_prod2 = tk.LabelFrame(win, text="Ürün Etiketi (ZT411 (2))", padx=10, pady=10)
        frm_prod2.pack(fill="x", padx=14, pady=8)

        prod2_w = tk.StringVar(value=str(s.get("prod2_w", s.get("prod_w", 50))))
        prod2_h = tk.StringVar(value=str(s.get("prod2_h", s.get("prod_h", 30))))
        prod2_dark = tk.StringVar(value=str(s.get("prod2_darkness", s.get("prod_darkness", 20))))
        prod2_x = tk.StringVar(value=str(s.get("prod2_x", s.get("prod_x", 0))))
        prod2_y = tk.StringVar(value=str(s.get("prod2_y", s.get("prod_y", 0))))
        prod2_module = tk.StringVar(value=str(s.get("prod2_module", s.get("prod_module", 6))))

        row = 0
        tk.Label(frm_prod2, text="Genişlik (mm):").grid(row=row, column=0, sticky="w")
        tk.Entry(frm_prod2, textvariable=prod2_w, width=8).grid(row=row, column=1, padx=6)
        tk.Label(frm_prod2, text="Yükseklik (mm):").grid(row=row, column=2, sticky="w")
        tk.Entry(frm_prod2, textvariable=prod2_h, width=8).grid(row=row, column=3, padx=6)

        row += 1
        tk.Label(frm_prod2, text="Koyuluk:").grid(row=row, column=0, sticky="w", pady=(6,0))
        tk.Entry(frm_prod2, textvariable=prod2_dark, width=8).grid(row=row, column=1, padx=6, pady=(6,0))
        tk.Label(frm_prod2, text="Konum X (mm):").grid(row=row, column=2, sticky="w", pady=(6,0))
        tk.Entry(frm_prod2, textvariable=prod2_x, width=8).grid(row=row, column=3, padx=6, pady=(6,0))

        row += 1
        tk.Label(frm_prod2, text="DM Modül:").grid(row=row, column=0, sticky="w", pady=(6,0))
        tk.Spinbox(frm_prod2, from_=2, to=10, textvariable=prod2_module, width=6).grid(row=row, column=1, padx=6, pady=(6,0))
        tk.Label(frm_prod2, text="Konum Y (mm):").grid(row=row, column=2, sticky="w", pady=(6,0))
        tk.Entry(frm_prod2, textvariable=prod2_y, width=8).grid(row=row, column=3, padx=6, pady=(6,0))

        tk.Button(
            frm_prod2,
            text="Varsayılan olarak ayarla",
            bg="#f39c12",
            fg="white",
            activebackground="#f5b041",
            command=lambda: _apply_prod2()
        ).grid(row=0, column=4, rowspan=3, padx=(18,0), sticky="ns")

        # Koli
        frm_box = tk.LabelFrame(win, text="Koli Etiketi (ZD230)", padx=10, pady=10)
        frm_box.pack(fill="x", padx=14, pady=8)

        box_w = tk.StringVar(value=str(s.get("box_w", 20)))
        box_h = tk.StringVar(value=str(s.get("box_h", 20)))
        box_dark = tk.StringVar(value=str(s.get("box_darkness", 20)))
        box_x = tk.StringVar(value=str(s.get("box_x", 0)))
        box_y = tk.StringVar(value=str(s.get("box_y", 0)))
        box_copy = tk.StringVar(value=str(s.get("box_copies", 1)))
        box_module = tk.StringVar(value=str(s.get("box_module", 6)))

        row = 0
        tk.Label(frm_box, text="Genişlik (mm):").grid(row=row, column=0, sticky="w")
        tk.Entry(frm_box, textvariable=box_w, width=8).grid(row=row, column=1, padx=6)
        tk.Label(frm_box, text="Yükseklik (mm):").grid(row=row, column=2, sticky="w")
        tk.Entry(frm_box, textvariable=box_h, width=8).grid(row=row, column=3, padx=6)

        row += 1
        tk.Label(frm_box, text="Kopya:").grid(row=row, column=0, sticky="w", pady=(6,0))
        tk.Entry(frm_box, textvariable=box_copy, width=8).grid(row=row, column=1, padx=6, pady=(6,0))
        tk.Label(frm_box, text="Koyuluk:").grid(row=row, column=2, sticky="w", pady=(6,0))
        tk.Entry(frm_box, textvariable=box_dark, width=8).grid(row=row, column=3, padx=6, pady=(6,0))

        row += 1
        tk.Label(frm_box, text="Konum X (mm):").grid(row=row, column=0, sticky="w", pady=(6,0))
        tk.Entry(frm_box, textvariable=box_x, width=8).grid(row=row, column=1, padx=6, pady=(6,0))
        tk.Label(frm_box, text="Konum Y (mm):").grid(row=row, column=2, sticky="w", pady=(6,0))
        tk.Entry(frm_box, textvariable=box_y, width=8).grid(row=row, column=3, padx=6, pady=(6,0))

        row += 1
        tk.Label(frm_box, text="DM Modül:").grid(row=row, column=0, sticky="w", pady=(6,0))
        tk.Spinbox(frm_box, from_=2, to=10, textvariable=box_module, width=6).grid(row=row, column=1, padx=6, pady=(6,0))

        # Koli etiketi için varsayılan ayarla (pencere kapanmaz)
        tk.Button(frm_box, text="Varsayılan olarak ayarla", bg="#f39c12", fg="white", activebackground="#f5b041", command=lambda: _apply_box()).grid(row=0, column=4, rowspan=4, padx=(18,0), sticky="ns")

        def _apply_prod():
            # Sadece ürün ayarlarını kaydet + uygula (kapatma)
            try:
                s["prod_w"] = float(prod_w.get().replace(",", "."))
                s["prod_h"] = float(prod_h.get().replace(",", "."))
                s["prod_darkness"] = int(float(prod_dark.get().replace(",", ".")))
                s["prod_x"] = float(prod_x.get().replace(",", "."))
                s["prod_y"] = float(prod_y.get().replace(",", "."))
                s["prod_module"] = int(float(prod_module.get().replace(",", ".")))
                s["prod_module"] = max(2, min(10, s["prod_module"]))
            except Exception:
                return messagebox.showerror("Hata", "Ürün ayarları sayı olmalı.")
            self.app.veri.save_settings()
            try:
                self.app.apply_tree_settings()
            except Exception:
                pass
            messagebox.showinfo("Bilgi", "Ürün etiketi ayarları varsayılan olarak kaydedildi.")

        def _apply_prod2():
            # Sadece ürün-2 ayarlarını kaydet + uygula (kapatma)
            try:
                s["prod2_w"] = float(prod2_w.get().replace(",", "."))
                s["prod2_h"] = float(prod2_h.get().replace(",", "."))
                s["prod2_darkness"] = int(float(prod2_dark.get().replace(",", ".")))
                s["prod2_x"] = float(prod2_x.get().replace(",", "."))
                s["prod2_y"] = float(prod2_y.get().replace(",", "."))
                s["prod2_module"] = int(float(prod2_module.get().replace(",", ".")))
                s["prod2_module"] = max(2, min(10, s["prod2_module"]))
            except Exception:
                return messagebox.showerror("Hata", "Ürün-2 ayarları sayı olmalı.")
            self.app.veri.save_settings()
            try:
                self.app.apply_tree_settings()
            except Exception:
                pass
            messagebox.showinfo("Bilgi", "Ürün-2 etiketi ayarları varsayılan olarak kaydedildi.")

        def _apply_box():
            # Sadece koli ayarlarını kaydet + uygula (kapatma)
            try:
                s["box_w"] = float(box_w.get().replace(",", "."))
                s["box_h"] = float(box_h.get().replace(",", "."))
                s["box_darkness"] = int(float(box_dark.get().replace(",", ".")))
                s["box_x"] = float(box_x.get().replace(",", "."))
                s["box_y"] = float(box_y.get().replace(",", "."))
                s["box_copies"] = int(float(box_copy.get().replace(",", ".")))
                s["box_module"] = int(float(box_module.get().replace(",", ".")))
                s["box_module"] = max(2, min(10, s["box_module"]))
            except Exception:
                return messagebox.showerror("Hata", "Koli ayarları sayı olmalı.")
            self.app.veri.save_settings()
            try:
                self.app.apply_tree_settings()
            except Exception:
                pass
            messagebox.showinfo("Bilgi", "Koli etiketi ayarları varsayılan olarak kaydedildi.")

        def _apply(close_after: bool):
            try:
                s["prod_w"] = float(prod_w.get().replace(",", "."))
                s["prod_h"] = float(prod_h.get().replace(",", "."))
                s["prod_darkness"] = int(float(prod_dark.get().replace(",", ".")))
                s["prod_x"] = float(prod_x.get().replace(",", "."))
                s["prod_y"] = float(prod_y.get().replace(",", "."))
                s["prod_module"] = int(float(prod_module.get().replace(",", ".")))
                s["prod_module"] = max(2, min(10, s["prod_module"]))
            except Exception:
                return messagebox.showerror("Hata", "Ürün ayarları sayı olmalı.")

            try:
                s["box_w"] = float(box_w.get().replace(",", "."))
                s["box_h"] = float(box_h.get().replace(",", "."))
                s["box_darkness"] = int(float(box_dark.get().replace(",", ".")))
                s["box_x"] = float(box_x.get().replace(",", "."))
                s["box_y"] = float(box_y.get().replace(",", "."))
                s["box_copies"] = int(float(box_copy.get().replace(",", ".")))
                s["box_module"] = int(float(box_module.get().replace(",", ".")))
                s["box_module"] = max(2, min(10, s["box_module"]))
            except Exception:
                return messagebox.showerror("Hata", "Koli ayarları sayı olmalı.")

            self.app.veri.save_settings()
            # Ana ekranda sütunları uygula
            try:
                self.app.apply_tree_settings()
            except Exception:
                pass

            if close_after:
                messagebox.showinfo("Bilgi", "Ayarlar kaydedildi.")
                win.destroy()
            else:
                # Uygula: pencere açık kalsın
                try:
                    status_lbl.config(text="Uygulandı ✅")
                except Exception:
                    pass
                try:
                    # Pencere arkaya düşmesin (kalıcı topmost yapma)
                    self._bring_to_front(win)
                except Exception:
                    pass

                # --- Alt Butonlar (Standart) ---
        btn_bar = tk.Frame(win)
        btn_bar.pack(fill="x", padx=14, pady=(12, 10))

        def _cancel():
            # Değişiklikleri kaydetmeden kapat
            win.destroy()

        tk.Button(btn_bar, text="İptal", width=12, bg="#6c757d", fg="white", activebackground="#868e96", command=_cancel).pack(side="left")

        tk.Button(btn_bar, text="Uygula", width=12, bg="#198754", fg="white", activebackground="#28a745",
                  command=lambda: _apply(False)).pack(side="left", padx=10)

        tk.Button(btn_bar, text="Kaydet", width=12, bg="#0d6efd", fg="white",
                  command=lambda: _apply(True)).pack(side="right")

        # İçeriğe göre pencere boyutunu otomatik ayarla (fazla boşluğu kaldır)
        try:
            win.update_idletasks()
            win.geometry(f"{win.winfo_reqwidth()}x{win.winfo_reqheight()}")
        except Exception:
            pass


    # -----------------------------
    # YÖNETİCİ PANELİ (şifreli)
    # -----------------------------
    def _open_admin_window(self):
        s = self.app.veri.settings

        if self._admin_win is not None:
            try:
                if self._admin_win.winfo_exists():
                    self._bring_to_front(self._admin_win)
                    return
            except Exception:
                pass
            self._admin_win = None

        win = tk.Toplevel(self.app.root)
        self._admin_win = win
        try:
            win.transient(self.app.root)
        except Exception:
            pass
        def _on_close_admin():
            try:
                self._admin_win = None
            except Exception:
                pass
            win.destroy()
        win.protocol('WM_DELETE_WINDOW', _on_close_admin)
        self._bring_to_front(win)
        win.title("Yönetici Paneli")
        win.geometry("760x520")
        win.resizable(False, False)

        nb = ttk.Notebook(win)
        nb.pack(fill="both", expand=True, padx=10, pady=10)

        tab_cfg = tk.Frame(nb)
        tab_del = tk.Frame(nb)
        tab_design = tk.Frame(nb)
        nb.add(tab_cfg, text="Cihaz / IP-PORT")
        nb.add(tab_del, text="Silme")
        nb.add(tab_design, text="Dizayn")

        # Dizayn sekmesi
        try:
            if dizayn is not None and hasattr(dizayn, "build_design_tab"):
                dizayn.build_design_tab(tab_design, self.app)
        except Exception:
            pass

        # -----------------------------
        # Silme işlemleri (Ana tabloda seçim yap -> buradan uygula)
        # -----------------------------
        tk.Label(tab_del, text="Silme İşlemleri", font=("Segoe UI", 13, "bold")).pack(pady=(14, 6))
        tk.Label(
            tab_del,
            text="Not: Önce ana ekrandaki tablodan satır(lar)ı seçin, sonra aşağıdaki butonları kullanın.",
            fg="#6c757d"
        ).pack(pady=(0, 10))

        btn_row = tk.Frame(tab_del)
        btn_row.pack(pady=8)

        def _get_selected_ids() -> list[int]:
            return getattr(self.app, "get_selected_display_ids", lambda: [])()

        def _ask_and_delete_rows(mode: str):
            ids = _get_selected_ids()
            if not ids:
                return messagebox.showwarning("Uyarı", "Lütfen ana tablodan en az 1 satır seçin.")
            if mode == "one":
                ids = [ids[0]]
                msg = f"Seçili 1 satır silinsin mi? (ID: {ids[0]})"
            else:
                msg = f"Seçili {len(ids)} satır silinsin mi?"
            if not messagebox.askyesno("Onay", msg):
                return
            silinen = getattr(self.app, "delete_rows_by_ids", lambda _ids: 0)(ids)
            messagebox.showinfo("Bilgi", f"{silinen} satır silindi.")
            self._bring_to_front(win)

        def _ask_and_reset_read(mode: str):
            ids = _get_selected_ids()
            if mode == "all":
                if not messagebox.askyesno("Onay", "Tüm okunan durumları sıfırlansın mı? (Satırlar korunur)"):
                    return
                adet = getattr(self.app, "reset_read_all", lambda: 0)()
                messagebox.showinfo("Bilgi", f"{adet} satır sıfırlandı (PENDING).")
                self._bring_to_front(win)
                return
            if not ids:
                return messagebox.showwarning("Uyarı", "Lütfen ana tablodan en az 1 satır seçin.")
            if mode == "one":
                ids = [ids[0]]
                msg = f"Seçili satırın okuma durumu sıfırlansın mı? (ID: {ids[0]})"
            else:
                msg = f"Seçili {len(ids)} satırın okuma durumu sıfırlansın mı?"
            if not messagebox.askyesno("Onay", msg):
                return
            adet = getattr(self.app, "reset_read_by_ids", lambda _ids: 0)(ids)
            messagebox.showinfo("Bilgi", f"{adet} satır sıfırlandı (PENDING).")
            self._bring_to_front(win)

        # Satır silme
        tk.Button(btn_row, text="Satırı Sil", width=16, bg="#ffc107", command=lambda: _ask_and_delete_rows("one")).pack(side="left", padx=10)
        tk.Button(btn_row, text="Seçili Satırları Sil", width=18, bg="#fd7e14", fg="white", command=lambda: _ask_and_delete_rows("many")).pack(side="left", padx=10)

        # Okunanı sil (satırlar kalır)
        btn_row2 = tk.Frame(tab_del)
        btn_row2.pack(pady=(10, 8))
        tk.Button(btn_row2, text="Okunanı Sil (Seçili)", width=18, bg="#0dcaf0", command=lambda: _ask_and_reset_read("many")).pack(side="left", padx=10)
        tk.Button(btn_row2, text="Okunanı Sil (Tek)", width=18, bg="#0dcaf0", command=lambda: _ask_and_reset_read("one")).pack(side="left", padx=10)
        tk.Button(btn_row2, text="Okunanı Sil (Hepsi)", width=18, bg="#0dcaf0", command=lambda: _ask_and_reset_read("all")).pack(side="left", padx=10)

        # Mevcut iş sil
        btn_row3 = tk.Frame(tab_del)
        btn_row3.pack(pady=(12, 8))
        tk.Button(btn_row3, text="Mevcut İşi Sil", width=18, bg="#dc3545", fg="white", command=lambda: getattr(self.app, "delete_job", lambda: None)()).pack(side="left", padx=10)

        # --- Cihaz ayarları ---
        lf_sc = tk.LabelFrame(tab_cfg, text="Scanner (Kamera)", padx=10, pady=10)
        lf_sc.pack(fill="x", padx=10, pady=8)
        v_sc_ip = tk.StringVar(value=str(s.get("scanner_ip", "192.168.1.12")))
        v_sc_port = tk.StringVar(value=str(s.get("scanner_port", 9000)))
        tk.Label(lf_sc, text="IP:").grid(row=0, column=0, sticky="w")
        tk.Entry(lf_sc, textvariable=v_sc_ip, width=18).grid(row=0, column=1, padx=6)
        tk.Label(lf_sc, text="Port:").grid(row=0, column=2, sticky="w")
        tk.Entry(lf_sc, textvariable=v_sc_port, width=8).grid(row=0, column=3, padx=6)

        lf_box = tk.LabelFrame(tab_cfg, text="Koli Yazıcı (ZD230) Socket", padx=10, pady=10)
        lf_box.pack(fill="x", padx=10, pady=8)
        v_box_ip = tk.StringVar(value=str(s.get("box_printer_ip", "192.168.1.230")))
        v_box_port = tk.StringVar(value=str(s.get("box_printer_port", 9100)))
        tk.Label(lf_box, text="IP:").grid(row=0, column=0, sticky="w")
        tk.Entry(lf_box, textvariable=v_box_ip, width=18).grid(row=0, column=1, padx=6)
        tk.Label(lf_box, text="Port:").grid(row=0, column=2, sticky="w")
        tk.Entry(lf_box, textvariable=v_box_port, width=8).grid(row=0, column=3, padx=6)

        # Windows yazıcı listesi bu projede kullanılmaz (SOCKET ONLY).

        lf_prod = tk.LabelFrame(tab_cfg, text="Ürün Yazıcı (ZT411 (1)) Socket", padx=10, pady=10)
        lf_prod.pack(fill="x", padx=10, pady=8)
        v_prod_ip = tk.StringVar(value=str(s.get("prod_printer_ip", "192.168.1.240")))
        v_prod_port = tk.StringVar(value=str(s.get("prod_printer_port", 9100)))
        tk.Label(lf_prod, text="IP:").grid(row=0, column=0, sticky="w")
        tk.Entry(lf_prod, textvariable=v_prod_ip, width=18).grid(row=0, column=1, padx=6)
        tk.Label(lf_prod, text="Port:").grid(row=0, column=2, sticky="w")
        tk.Entry(lf_prod, textvariable=v_prod_port, width=8).grid(row=0, column=3, padx=6)

        # Windows yazıcı listesi bu projede kullanılmaz (SOCKET ONLY).

        lf_prod2 = tk.LabelFrame(tab_cfg, text="Ürün Yazıcı (ZT411 (2)) Socket", padx=10, pady=10)
        lf_prod2.pack(fill="x", padx=10, pady=8)
        v_prod2_ip = tk.StringVar(value=str(s.get("prod2_printer_ip", s.get("prod2_ip", ""))))
        v_prod2_port = tk.StringVar(value=str(s.get("prod2_printer_port", s.get("prod2_port", 9100))))
        tk.Label(lf_prod2, text="IP:").grid(row=0, column=0, sticky="w")
        tk.Entry(lf_prod2, textvariable=v_prod2_ip, width=18).grid(row=0, column=1, padx=6)
        tk.Label(lf_prod2, text="Port:").grid(row=0, column=2, sticky="w")
        tk.Entry(lf_prod2, textvariable=v_prod2_port, width=8).grid(row=0, column=3, padx=6)
        
        # Windows yazıcı listesi bu projede kullanılmaz (SOCKET ONLY).
        lf_rej = tk.LabelFrame(tab_cfg, text="Reject Sistemi", padx=10, pady=10)
        lf_rej.pack(fill="x", padx=10, pady=8)
        v_com = tk.StringVar(value=str(s.get("reject_com", "COM2")))
        v_dur = tk.StringVar(value=str(s.get("reject_duration_s", 0.5)))
        v_del = tk.StringVar(value=str(s.get("reject_delay_s", 0.4)))

        tk.Label(lf_rej, text="Port:").grid(row=0, column=0, sticky="w")
        tk.Entry(lf_rej, textvariable=v_com, width=10).grid(row=0, column=1, padx=6)
        tk.Label(lf_rej, text="Süre (sn):").grid(row=0, column=2, sticky="w")
        tk.Entry(lf_rej, textvariable=v_dur, width=8).grid(row=0, column=3, padx=6)
        tk.Label(lf_rej, text="Gecikme (sn):").grid(row=0, column=4, sticky="w")
        tk.Entry(lf_rej, textvariable=v_del, width=8).grid(row=0, column=5, padx=6)

        def test_reject():
            try:
                self.app.donanim.test_reject_pulse()
            except Exception as ex:
                messagebox.showerror("Hata", str(ex))

        tk.Button(lf_rej, text="TEST", bg="#dc3545", fg="white", command=test_reject).grid(row=0, column=6, padx=10)

        def save_cfg(close_after: bool = True):
            s["scanner_ip"] = v_sc_ip.get().strip()
            try:
                s["scanner_port"] = int(v_sc_port.get())
            except Exception:
                return messagebox.showerror("Hata", "Scanner Port sayı olmalı.")

            s["box_printer_ip"] = v_box_ip.get().strip()
            # Uyumlu anahtarlar
            s["box_ip"] = s["box_printer_ip"]
            try:
                s["box_printer_port"] = int(v_box_port.get())
                s["box_port"] = s["box_printer_port"]
            except Exception:
                return messagebox.showerror("Hata", "BOX Port sayı olmalı.")

            s["prod_printer_ip"] = v_prod_ip.get().strip()
            s["prod_ip"] = s["prod_printer_ip"]
            try:
                s["prod_printer_port"] = int(v_prod_port.get())
                s["prod_port"] = s["prod_printer_port"]
            except Exception:
                return messagebox.showerror("Hata", "URUN Port sayı olmalı.")

            s["prod2_printer_ip"] = v_prod2_ip.get().strip()
            s["prod2_ip"] = s["prod2_printer_ip"]
            try:
                s["prod2_printer_port"] = int(v_prod2_port.get())
                s["prod2_port"] = s["prod2_printer_port"]
            except Exception:
                return messagebox.showerror("Hata", "URUN-2 Port sayı olmalı.")

            # Windows yazıcı adları
            try:
                s["printer_box"] = v_box_prn.get()
            except Exception:
                pass
            try:
                s["printer_prod"] = v_prod_prn.get()
            except Exception:
                pass

            try:
                s["printer_prod2"] = v_prod2_prn.get()
            except Exception:
                pass

            s["reject_com"] = v_com.get().strip()
            try:
                s["reject_duration_s"] = float(v_dur.get().replace(",", "."))
                s["reject_delay_s"] = float(v_del.get().replace(",", "."))
            except Exception:
                return messagebox.showerror("Hata", "Reject süre/gecikme sayı olmalı.")

            self.app.veri.save_settings()
            messagebox.showinfo("Bilgi", "Yönetici ayarları kaydedildi.")
            # "Uygula" sonrası pencere arkaya düşmesin
            try:
                self._bring_to_front(win)
            except Exception:
                pass
            if close_after:
                win.destroy()

        def save_cfg_keep_open():
            return save_cfg(close_after=False)

        # --- Alt Butonlar (Standart) ---
        bar = tk.Frame(tab_cfg)
        bar.pack(fill="x", padx=10, pady=12)

        tk.Button(bar, text="İptal", width=12, command=win.destroy).pack(side="left")
        tk.Button(bar, text="Uygula", width=12, bg="#198754", fg="white",
                  command=lambda: save_cfg_keep_open()).pack(side="left", padx=10)
        tk.Button(bar, text="Kaydet", width=12, bg="#0d6efd", fg="white",
                  command=save_cfg).pack(side="right")

        # Pencereyi içeriğe göre küçült (gereksiz boşluk olmasın)
        try:
            win.update_idletasks()
            req_w = win.winfo_reqwidth() + 20
            req_h = win.winfo_reqheight() + 20
            w = max(560, min(760, req_w))
            h = max(420, min(560, req_h))
            win.geometry(f"{w}x{h}")
            win.resizable(False, False)
        except Exception:
            pass