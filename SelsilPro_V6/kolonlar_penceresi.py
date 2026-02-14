"""
kolonlar_penceresi.py
Selsil Pro V6 - Tablo Görünümü / Kolonlar

- Ana tablo ve Geçmiş İşler gibi farklı tablolarda kolon görünürlüğünü yönetir.
- Seçimleri ayarlara kaydedebilir.
"""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk


class KolonlarPenceresi(tk.Toplevel):
    """Kolon görünürlüğü yöneticisi.

    Geriye dönük uyumluluk:
    - Eski kullanım: KolonlarPenceresi(master, columns, visible_map, on_apply, on_save)
    - Yeni kullanım: KolonlarPenceresi(master, sections=[...])
      sections: list[dict] -> {title, columns, visible_map, on_apply, on_save, default_map}
    """

    def __init__(self, master, columns=None, visible_map=None, on_apply=None, on_save=None, *, sections=None, title=None):
        super().__init__(master)
        self.title(title or "Kolonlar")
        self.resizable(False, False)

        try:
            self.attributes("-topmost", False)
        except Exception:
            pass

        # Normalize sections
        if sections is None:
            sections = [{
                "title": "Ana Tablo",
                "columns": list(columns or []),
                "visible_map": dict(visible_map or {}),
                "on_apply": on_apply,
                "on_save": on_save,
                "default_map": None,
            }]
        self.sections = sections

        self._vars_by_section = {}   # title -> {col: tk.BooleanVar}
        self._widgets_by_section = {}  # title -> {col: widget}
        self._filter_by_section = {} # title -> tk.StringVar

        root = ttk.Frame(self, padding=12)
        root.pack(fill="both", expand=True)

        ttk.Label(root, text="Kolon Görünürlüğü", font=("Segoe UI", 12, "bold")).pack(anchor="w")

        nb = ttk.Notebook(root)
        nb.pack(fill="both", expand=True, pady=(10, 10))

        for sec in self.sections:
            self._build_tab(nb, sec)

        # alt butonlar
        btns = ttk.Frame(root)
        btns.pack(fill="x")

        ttk.Button(btns, text="Uygula", command=self._apply_all).pack(side="right", padx=(6, 0))
        ttk.Button(btns, text="Kaydet", command=self._save_all).pack(side="right", padx=(6, 0))
        ttk.Button(btns, text="Kapat", command=self.destroy).pack(side="right")

        # Pencereyi ortala
        try:
            self.update_idletasks()
            w = self.winfo_width()
            h = self.winfo_height()
            x = max(0, (self.winfo_screenwidth() - w) // 2)
            y = max(0, (self.winfo_screenheight() - h) // 2)
            self.geometry(f"{w}x{h}+{x}+{y}")
        except Exception:
            pass

    def _build_tab(self, nb: ttk.Notebook, sec: dict):
        title = sec.get("title") or "Tablo"
        columns = list(sec.get("columns") or [])
        visible_map = sec.get("visible_map") or {}
        default_map = sec.get("default_map")

        tab = ttk.Frame(nb, padding=10)
        nb.add(tab, text=title)

        # filtre
        filter_var = tk.StringVar(value="")
        self._filter_by_section[title] = filter_var

        top = ttk.Frame(tab)
        top.pack(fill="x")

        ttk.Label(top, text="Ara:").pack(side="left")
        ent = ttk.Entry(top, textvariable=filter_var, width=24)
        ent.pack(side="left", padx=(6, 10))
        ent.bind("<KeyRelease>", lambda e, t=title: self._apply_filter(t))

        ttk.Button(top, text="Tümü", width=10, command=lambda t=title: self._select_all(t, True)).pack(side="left", padx=3)
        ttk.Button(top, text="Hiçbiri", width=10, command=lambda t=title: self._select_all(t, False)).pack(side="left", padx=3)
        ttk.Button(top, text="Varsayılan", width=10, command=lambda t=title, dm=default_map: self._reset_default(t, dm)).pack(side="left", padx=3)

        box = ttk.Labelframe(tab, text="Kolonlar", padding=10)
        box.pack(fill="both", expand=True, pady=(10, 0))

        vars_map = {}
        widgets_map = {}

        # scrollable area
        canvas = tk.Canvas(box, height=260, highlightthickness=0)
        scroll = ttk.Scrollbar(box, orient="vertical", command=canvas.yview)
        inner = ttk.Frame(canvas)

        inner.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=inner, anchor="nw")
        canvas.configure(yscrollcommand=scroll.set)

        canvas.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")

        for i, col in enumerate(columns):
            v = tk.BooleanVar(value=bool(visible_map.get(col, True)))
            chk = ttk.Checkbutton(inner, text=col, variable=v)
            chk.grid(row=i, column=0, sticky="w", pady=2)
            vars_map[col] = v
            widgets_map[col] = chk

        self._vars_by_section[title] = vars_map
        self._widgets_by_section[title] = widgets_map

    def _current_map(self, title: str) -> dict:
        out = {}
        for c, v in (self._vars_by_section.get(title) or {}).items():
            try:
                out[c] = bool(v.get())
            except Exception:
                out[c] = True
        return out

    def _select_all(self, title: str, state: bool):
        for v in (self._vars_by_section.get(title) or {}).values():
            try:
                v.set(bool(state))
            except Exception:
                pass
        self._apply_filter(title)

    def _reset_default(self, title: str, default_map: dict | None):
        if not isinstance(default_map, dict):
            return
        for c, v in (self._vars_by_section.get(title) or {}).items():
            try:
                v.set(bool(default_map.get(c, True)))
            except Exception:
                pass
        self._apply_filter(title)

    def _apply_filter(self, title: str):
        needle = (self._filter_by_section.get(title).get() or "").strip().lower()
        widgets = self._widgets_by_section.get(title) or {}
        for col, w in widgets.items():
            show = (needle in col.lower()) if needle else True
            try:
                w.grid_remove() if not show else w.grid()
            except Exception:
                pass

    def _apply_all(self):
        for sec in self.sections:
            title = sec.get("title") or "Tablo"
            cb = sec.get("on_apply")
            if callable(cb):
                try:
                    cb(self._current_map(title))
                except Exception:
                    pass

    def _save_all(self):
        for sec in self.sections:
            title = sec.get("title") or "Tablo"
            cb = sec.get("on_save")
            if callable(cb):
                try:
                    cb(self._current_map(title))
                except Exception:
                    pass
        # Kaydet sonrası da uygula
        self._apply_all()
