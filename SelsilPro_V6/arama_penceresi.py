"""
arama_penceresi.py
Tablodaki kayıtlarda (work_list) seçilen sütunda arama yapma.

- Kullanıcı bir sütun seçer (ID, Koli, Durum, Tarih, Barkod, Koli Etiketi, Koli İçerik No)
- Arama metni girer
- Sonuçlar listelenir; çift tıklayınca ana tabloda ilgili satıra gider.
"""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk


COLS = [
    ("id", "ID"),
    ("box", "Koli"),
    ("status", "Durum"),
    ("read_at", "Tarih"),
    ("raw_disp", "Barkod"),
    ("label", "Koli Etiketi"),
    ("in_box", "Koli İçerik No"),
]


def _norm(s: object) -> str:
    if s is None:
        return ""
    return str(s).strip()


def open_arama_penceresi(app, mode: str = "goto", status_filter: str | None = None):
    # Tek pencere
    if getattr(app, "_search_win", None) is not None and app._search_win.winfo_exists():
        app._search_win.lift()
        app._search_win.focus_force()
        return

    win = tk.Toplevel(app.root)
    app._search_win = win
    win.title("ARAMA")
    win.geometry("920x420")
    win.configure(bg="#f7f7f7")

    # top controls
    top = tk.Frame(win, bg="#f7f7f7", pady=8)
    top.pack(fill="x", padx=10)

    tk.Label(top, text="Sütun:", bg="#f7f7f7", font=("Segoe UI", 10, "bold")).pack(side="left")

    col_var = tk.StringVar(value=COLS[4][1])  # default Barkod
    col_map = {label: key for key, label in COLS}

    cmb = ttk.Combobox(top, textvariable=col_var, values=[label for _, label in COLS], state="readonly", width=18)
    cmb.pack(side="left", padx=(8, 14))

    tk.Label(top, text="Ara:", bg="#f7f7f7", font=("Segoe UI", 10, "bold")).pack(side="left")
    q_var = tk.StringVar()
    exact_var = tk.IntVar(value=1)
    ent = tk.Entry(top, textvariable=q_var, width=45, font=("Segoe UI", 10))
    ent.pack(side="left", padx=8)

    chk = tk.Checkbutton(top, text="Tam Eşleşme", variable=exact_var, bg="#f7f7f7", font=("Segoe UI", 9, "bold"))
    chk.pack(side="left", padx=(6, 0))
    ent.focus_set()

    # results
    cols = ("ID", "Koli", "Durum", "Tarih", "Barkod", "Koli Etiketi", "Koli İçerik No")
    tree = ttk.Treeview(win, columns=cols, show="headings", height=13)
    for c in cols:
        tree.heading(c, text=c)
    tree.column("ID", width=60, anchor="center")
    tree.column("Koli", width=60, anchor="center")
    tree.column("Durum", width=90, anchor="center")
    tree.column("Tarih", width=110, anchor="center")
    tree.column("Barkod", width=360, anchor="w")
    tree.column("Koli Etiketi", width=160, anchor="w")
    tree.column("Koli İçerik No", width=110, anchor="center")
    tree.pack(fill="both", expand=True, padx=10, pady=(0, 10))

    sb = ttk.Scrollbar(win, orient="vertical", command=tree.yview)
    tree.configure(yscroll=sb.set)
    sb.place(relx=0.985, rely=0.16, relheight=0.74)

    status = tk.Label(win, text="Hazır", bg="#f7f7f7", fg="#198754", font=("Segoe UI", 9, "bold"))
    status.pack(anchor="w", padx=12, pady=(0, 6))

    def do_search():
        # clear
        for iid in tree.get_children():
            tree.delete(iid)

        key = col_map.get(col_var.get(), "raw_disp")
        q = _norm(q_var.get())
        if not q:
            status.config(text="Arama metni boş.", fg="#dc3545")
            return

        q_low = q.lower()
        results = []
        for item in getattr(app, "work_list", []) or []:
            # Manuel doğrulama modunda sadece PENDING göster
            if mode == "manual_verify" and str(item.get("status", "")).upper() != "PENDING":
                continue
            val = _norm(item.get(key, ""))
            v_low = val.lower()
            if exact_var.get() == 1:
                if q_low == v_low:
                    results.append(item)
            else:
                if q_low in v_low:
                    results.append(item)

        for it in results[:5000]:
            tree.insert(
                "",
                "end",
                values=(
                    it.get("id", ""),
                    it.get("box", ""),
                    it.get("status", ""),
                    it.get("read_at", ""),
                    it.get("raw_disp", it.get("raw", "")),
                    it.get("label", ""),
                    it.get("in_box", ""),
                ),
            )

        status.config(text=f"{len(results)} sonuç bulundu.", fg="#0b2e4a")

    def clear_search():
        q_var.set("")
        for iid in tree.get_children():
            tree.delete(iid)
        status.config(text="Hazır", fg="#198754")
        ent.focus_set()

    def goto_selected(_evt=None):
        sel = tree.selection()
        if not sel:
            return
        vals = tree.item(sel[0], "values")
        if not vals:
            return
        target_id = str(vals[0])

        if mode == "manual_verify":
            try:
                from tkinter import messagebox
                ok = messagebox.askyesno("Manuel Doğrula", f"ID {target_id} barkodunu manuel olarak doğrulamak istiyor musunuz?")
            except Exception:
                ok = True
            if ok:
                try:
                    app.manual_verify_item_by_id(int(target_id))
                except Exception:
                    pass
            try:
                win.destroy()
            except Exception:
                pass
            return

        # ana tabloda ID eşleşen ilk satıra git
        try:
            for iid in app.tree.get_children():
                row = app.tree.item(iid, "values")
                if row and str(row[0]) == target_id:
                    app.tree.selection_set(iid)
                    app.tree.focus(iid)
                    app.tree.see(iid)
                    break
        except Exception:
            pass

        try:
            win.lift()
        except Exception:
            pass

    # buttons
    btns = tk.Frame(top, bg="#f7f7f7")
    btns.pack(side="right")

    tk.Button(btns, text="Ara", command=do_search, bg="#0d6efd", fg="white",
              font=("Segoe UI", 9, "bold"), width=10).pack(side="left", padx=6)
    tk.Button(btns, text="Temizle", command=clear_search, bg="#6c757d", fg="white",
              font=("Segoe UI", 9, "bold"), width=10).pack(side="left", padx=6)
    tk.Button(btns, text="Kapat", command=win.destroy, bg="#dc3545", fg="white",
              font=("Segoe UI", 9, "bold"), width=10).pack(side="left", padx=6)

    ent.bind("<Return>", lambda e: do_search())
    tree.bind("<Double-1>", goto_selected)

    def on_close():
        try:
            app._search_win = None
        except Exception:
            pass
        win.destroy()

    win.protocol("WM_DELETE_WINDOW", on_close)
