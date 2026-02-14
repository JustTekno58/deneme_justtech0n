"""dizayn.py

Yönetici Paneli > Dizayn sekmesi.

Bu modül; tema (aydınlık/karanlık), dashboard yerleşimi (A/B), font ayarları
ve bölme (paned) yerleşimlerini yönetmek için küçük bir UI sağlar.

Gerçek uygulama değişiklikleri AnaEkran tarafındaki:
- apply_design_from_settings()
- set_dashboard_layout(...)
- apply_ui_theme(...)
- apply_ui_font(...)
metodlarıyla yapılır.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk, messagebox
import tkinter.font as tkfont


def _safe_int(v, default: int) -> int:
    try:
        return int(str(v).strip())
    except Exception:
        return default


def build_design_tab(parent: tk.Widget, app) -> None:
    """Yönetici paneline 'Dizayn' sekmesini doldurur."""
    s = getattr(getattr(app, "veri", None), "settings", {}) or {}

    # --- Varsayılanlar ---
    v_theme = tk.StringVar(value=str(s.get("ui_theme", "light")))
    v_dash = tk.StringVar(value=str(s.get("ui_dashboard_layout", "A")).upper() or "A")
    v_dash_bg = tk.StringVar(value=str(s.get("ui_dashboard_bg", "auto")))

    v_font_family = tk.StringVar(value=str(s.get("ui_font_family", "Segoe UI")))
    v_font_size = tk.StringVar(value=str(s.get("ui_font_size", 9)))

    outer = ttk.Frame(parent)
    outer.pack(fill="both", expand=True, padx=12, pady=12)

    title = ttk.Label(outer, text="Dizayn / Tema / Font", font=("Segoe UI", 12, "bold"))
    title.pack(anchor="w", pady=(0, 10))

    # --- Tema ---
    lf_theme = ttk.LabelFrame(outer, text="Tema")
    lf_theme.pack(fill="x", pady=(0, 10))

    row = ttk.Frame(lf_theme)
    row.pack(fill="x", padx=10, pady=10)

    ttk.Radiobutton(row, text="Aydınlık", value="light", variable=v_theme).pack(side="left", padx=(0, 14))
    ttk.Radiobutton(row, text="Karanlık", value="dark", variable=v_theme).pack(side="left")

    # --- Dashboard ---
    lf_dash = ttk.LabelFrame(outer, text="Dashboard Yerleşimi")
    lf_dash.pack(fill="x", pady=(0, 10))

    rowd = ttk.Frame(lf_dash)
    rowd.pack(fill="x", padx=10, pady=10)

    ttk.Radiobutton(rowd, text="Seçenek A (Dikey)  ✅ önerilen", value="A", variable=v_dash).pack(anchor="w")
    ttk.Radiobutton(rowd, text="Seçenek B (Kompakt)", value="B", variable=v_dash).pack(anchor="w", pady=(4, 0))

    rowd2 = ttk.Frame(lf_dash)
    rowd2.pack(fill="x", padx=10, pady=(0, 10))
    ttk.Label(rowd2, text="Arka Plan:").pack(side="left")
    cb_bg = ttk.Combobox(rowd2, textvariable=v_dash_bg, values=["auto", "dark", "light", "gray"], width=10, state="readonly")
    cb_bg.pack(side="left", padx=8)
    ttk.Label(rowd2, text="(auto: tema ile uyumlu)", foreground="#6c757d").pack(side="left", padx=6)

    # --- Font ---
    lf_font = ttk.LabelFrame(outer, text="Yazı Fontu")
    lf_font.pack(fill="x", pady=(0, 10))

    rowf = ttk.Frame(lf_font)
    rowf.pack(fill="x", padx=10, pady=10)

    ttk.Label(rowf, text="Aile:").grid(row=0, column=0, sticky="w")

    # Sistem fontları (bulunamazsa sabit liste)
    try:
        families = sorted(set(tkfont.families()))
    except Exception:
        families = ["Segoe UI", "Arial", "Calibri", "Tahoma"]

    cb = ttk.Combobox(rowf, textvariable=v_font_family, values=families, width=28)
    cb.grid(row=0, column=1, padx=8, sticky="w")

    ttk.Label(rowf, text="Boyut:").grid(row=0, column=2, padx=(20, 4), sticky="w")
    sp = ttk.Spinbox(rowf, from_=8, to=18, width=6, textvariable=v_font_size)
    sp.grid(row=0, column=3, sticky="w")

    ttk.Label(rowf, text="Not: Bazı başlıklar sabit kalabilir.", foreground="#6c757d").grid(
        row=1, column=0, columnspan=4, sticky="w", pady=(8, 0)
    )

    # --- Yerleşim reset ---
    lf_layout = ttk.LabelFrame(outer, text="Panel Yerleşimleri")
    lf_layout.pack(fill="x", pady=(0, 10))

    rowl = ttk.Frame(lf_layout)
    rowl.pack(fill="x", padx=10, pady=10)

    def reset_sashes():
        try:
            s["sash_upload"] = 0
            s["sash_files"] = 0
            s["sash_bottom"] = 0
            s["sash_summary"] = []
            app.veri.save_settings()
        except Exception:
            pass
        try:
            if hasattr(app, "restore_layout_sashes"):
                app.restore_layout_sashes()
        except Exception:
            pass
        messagebox.showinfo("Bilgi", "Yerleşim bölmeleri sıfırlandı.")

    ttk.Button(rowl, text="Bölmeleri Sıfırla", command=reset_sashes).pack(side="left")
    ttk.Label(rowl, text="(Özet, Ürün/Box, Önceki/Sonraki, Rapor/Dashboard)", foreground="#6c757d").pack(side="left", padx=10)

    # --- Uygula / Kaydet ---
    btns = ttk.Frame(outer)
    btns.pack(fill="x", pady=(8, 0))

    def apply_only(save: bool):
        # write settings
        s["ui_theme"] = v_theme.get().strip() or "light"
        s["ui_dashboard_layout"] = (v_dash.get().strip() or "A").upper()
        s["ui_dashboard_bg"] = (v_dash_bg.get().strip() or "auto")
        s["ui_font_family"] = v_font_family.get().strip() or "Segoe UI"
        s["ui_font_size"] = _safe_int(v_font_size.get(), 9)

        if save:
            try:
                app.veri.save_settings()
            except Exception:
                pass

        # apply live
        try:
            if hasattr(app, "apply_design_from_settings"):
                app.apply_design_from_settings()
        except Exception:
            pass

    def apply_now():
        apply_only(save=False)
        messagebox.showinfo("Bilgi", "Dizayn uygulandı.")

    def save_and_apply():
        apply_only(save=True)
        messagebox.showinfo("Bilgi", "Dizayn kaydedildi ve uygulandı.")

    def set_defaults():
        v_theme.set("light")
        v_dash.set("A")
        v_dash_bg.set("auto")
        v_font_family.set("Segoe UI")
        v_font_size.set("9")
        apply_only(save=True)

    ttk.Button(btns, text="Uygula", command=apply_now).pack(side="left")
    ttk.Button(btns, text="Kaydet", command=save_and_apply).pack(side="left", padx=8)
    ttk.Button(btns, text="Varsayılanlar", command=set_defaults).pack(side="left")

    ttk.Label(btns, text="Değişiklikler yeniden başlatmadan da uygulanır.", foreground="#6c757d").pack(side="right")
