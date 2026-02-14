"""
job_yonetimi.py
Selsil Pro V6 - Job (İş) Yönetimi

Amaç:
- Bir işin (Job) tüm durumunu SQLite içinde saklamak
- Uygulama kapansa bile kaldığı yerden devam edebilmek
- Geçmiş işleri listeleyip geri çağırabilmek

Not:
Bu modül, mevcut veri_yonetimi.py içindeki eski "jobs" tablosunu bozmaz.
Yeni tablolar: jobs_v2, job_items_v2
"""
from __future__ import annotations

import json
import os
import sqlite3
import time
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

# DB dosyası her ortamda aynı yerden açılsın (çalışma dizinine bağlı kalmasın)
DB_NAME = "SelsilPro.db"
DB_PATH = os.path.join(os.path.dirname(__file__), DB_NAME)


def _now_iso() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


@dataclass
class JobHeader:
    job_id: str
    job_name: str
    prod_file: str
    box_file: str
    status: str
    created_at: str
    updated_at: str
    settings_json: str
    current_koli_no: int


class JobYonetimi:
    def __init__(self, db_path: Optional[str] = None) -> None:
        self.db_path = db_path or DB_PATH
        self.conn = sqlite3.connect(self.db_path)
        self.conn.row_factory = sqlite3.Row
        self._ensure_tables()
        self._migrate_legacy_jobs_if_needed()


    def _migrate_legacy_jobs_if_needed(self) -> None:
        """
        Eski V3/V4 formatındaki `jobs` tablosunu (filename, work_list, box_labels, count, box_size, last_updated)
        yeni Job V2 tablolarına aktarır.

        - Sadece `jobs_v2` boşsa çalışır (tekrar tekrar kopyalamaz).
        - job_id olarak `legacy::<filename>` kullanır (benzersiz + deterministik).
        """
        try:
            cur = self.conn.cursor()

            # V2 tablolarında kayıt var mı?
            v2_cnt = cur.execute("SELECT COUNT(*) FROM jobs_v2").fetchone()[0]
            if v2_cnt and int(v2_cnt) > 0:
                return

            # Eski tablo var mı?
            legacy_exists = cur.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='jobs'"
            ).fetchone()
            if not legacy_exists:
                return

            rows = cur.execute(
                "SELECT filename, work_list, box_labels, count, box_size, last_updated FROM jobs"
            ).fetchall()
            if not rows:
                return

            for r in rows:
                try:
                    filename = (r[0] or "").strip()
                    if not filename:
                        continue
                    job_id = f"legacy::{filename}"

                    work_list_txt = r[1] or ""
                    box_labels_txt = r[2] or ""
                    done_count = int(r[3] or 0)
                    box_size = int(r[4] or 0)
                    last_updated = r[5] or ""

                    # legacy timestamp -> iso
                    upd_iso = ""
                    try:
                        ts = float(last_updated)
                        upd_iso = datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S")
                    except Exception:
                        upd_iso = str(last_updated)

                    # work_list parse
                    items_obj = None
                    try:
                        items_obj = json.loads(work_list_txt) if work_list_txt else None
                    except Exception:
                        items_obj = None
                    items_list = []
                    if isinstance(items_obj, dict) and isinstance(items_obj.get("list"), list):
                        items_list = items_obj.get("list") or []
                    elif isinstance(items_obj, list):
                        items_list = items_obj
                    total = len(items_list)

                    settings = {
                        "legacy": True,
                        "box_size": box_size,
                        "done_count": done_count,
                        "total_count": total,
                    }
                    settings_json = json.dumps(settings, ensure_ascii=False)

                    # header insert
                    cur.execute(
                        """
                        INSERT OR REPLACE INTO jobs_v2
                        (job_id, job_name, prod_file, box_file, status, created_at, updated_at, settings_json, current_koli_no)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            job_id,
                            filename,
                            filename,
                            "",
                            "LEGACY",
                            upd_iso,
                            upd_iso,
                            settings_json,
                            1,
                        ),
                    )

                    # items insert
                    cur.execute("DELETE FROM job_items_v2 WHERE job_id=?", (job_id,))
                    for it in items_list:
                        if not isinstance(it, dict):
                            continue
                        display_id = int(it.get("id") or 0)
                        raw = it.get("raw") or ""
                        raw_disp = it.get("raw_disp") or raw
                        status = it.get("status") or "PENDING"
                        koli_no = it.get("box")
                        if koli_no in (None, "", "-"):
                            koli_no = 0
                        try:
                            koli_no = int(koli_no)
                        except Exception:
                            koli_no = 0
                        koli_label = it.get("label") or "-"
                        read_at = it.get("read_at") or ""
                        reject_sent = 1 if int(it.get("reject_sent") or 0) else 0
                        in_box = it.get("in_box") or ""

                        cur.execute(
                            """
                            INSERT INTO job_items_v2
                            (job_id, display_id, barkod_raw, barkod_disp, status, koli_no, koli_label, read_at, reject_sent, in_box)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                            """,
                            (job_id, display_id, raw, raw_disp, status, koli_no, koli_label, read_at, reject_sent, in_box),
                        )
                except Exception:
                    # tek bir kayıtta hata olsa bile diğerlerini taşımaya çalış
                    continue

            self.conn.commit()
        except Exception:
            # migration hatası uygulamayı düşürmesin
            try:
                self.conn.rollback()
            except Exception:
                pass
            return


    def close(self) -> None:
        try:
            self.conn.close()
        except Exception:
            pass

    def _ensure_tables(self) -> None:
        cur = self.conn.cursor()
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS jobs_v2 (
                job_id TEXT PRIMARY KEY,
                job_name TEXT,
                prod_file TEXT,
                box_file TEXT,
                status TEXT,
                created_at TEXT,
                updated_at TEXT,
                settings_json TEXT,
                current_koli_no INTEGER DEFAULT 1
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS job_items_v2 (
                row_id INTEGER PRIMARY KEY AUTOINCREMENT,
                job_id TEXT,
                display_id INTEGER,
                barkod_raw TEXT,
                barkod_disp TEXT,
                status TEXT,
                koli_no INTEGER,
                koli_label TEXT,
                read_at TEXT,
                reject_sent INTEGER DEFAULT 0,
                in_box TEXT,
                FOREIGN KEY(job_id) REFERENCES jobs_v2(job_id)
            )
            """
        )
        cur.execute("CREATE INDEX IF NOT EXISTS idx_job_items_job ON job_items_v2(job_id)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_job_items_display ON job_items_v2(job_id, display_id)")
        self.conn.commit()

    # -------------------------------
    # Job CRUD
    # -------------------------------
    def create_job(
        self,
        job_name: str,
        prod_file: str,
        box_file: str,
        settings: Dict[str, Any],
        current_koli_no: int = 1,
    ) -> str:
        job_id = str(uuid.uuid4())
        now = _now_iso()
        cur = self.conn.cursor()
        cur.execute(
            """
            INSERT INTO jobs_v2
            (job_id, job_name, prod_file, box_file, status, created_at, updated_at, settings_json, current_koli_no)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                job_id,
                job_name,
                prod_file or "",
                box_file or "",
                "ACTIVE",
                now,
                now,
                json.dumps(settings, ensure_ascii=False),
                int(current_koli_no or 1),
            ),
        )
        self.conn.commit()
        return job_id

    def set_status(self, job_id: str, status: str) -> None:
        cur = self.conn.cursor()
        cur.execute(
            "UPDATE jobs_v2 SET status=?, updated_at=? WHERE job_id=?",
            (status, _now_iso(), job_id),
        )
        self.conn.commit()

    def set_active_job(self, job_id: str) -> None:
        # tek aktif job yaklaşımı: eski ACTIVE'leri PAUSED yap
        cur = self.conn.cursor()
        cur.execute("UPDATE jobs_v2 SET status='PAUSED', updated_at=? WHERE status='ACTIVE'", (_now_iso(),))
        cur.execute("UPDATE jobs_v2 SET status='ACTIVE', updated_at=? WHERE job_id=?", (_now_iso(), job_id))
        self.conn.commit()

    def update_header(self, job_id: str, settings: Optional[Dict[str, Any]] = None, current_koli_no: Optional[int] = None) -> None:
        cur = self.conn.cursor()
        if settings is not None and current_koli_no is not None:
            cur.execute(
                "UPDATE jobs_v2 SET settings_json=?, current_koli_no=?, updated_at=? WHERE job_id=?",
                (json.dumps(settings, ensure_ascii=False), int(current_koli_no), _now_iso(), job_id),
            )
        elif settings is not None:
            cur.execute(
                "UPDATE jobs_v2 SET settings_json=?, updated_at=? WHERE job_id=?",
                (json.dumps(settings, ensure_ascii=False), _now_iso(), job_id),
            )
        elif current_koli_no is not None:
            cur.execute(
                "UPDATE jobs_v2 SET current_koli_no=?, updated_at=? WHERE job_id=?",
                (int(current_koli_no), _now_iso(), job_id),
            )
        self.conn.commit()

    def list_jobs(self, status: Optional[str] = None, limit: int = 200) -> List[JobHeader]:
        cur = self.conn.cursor()
        if status:
            rows = cur.execute(
                "SELECT * FROM jobs_v2 WHERE status=? ORDER BY updated_at DESC LIMIT ?",
                (status, int(limit)),
            ).fetchall()
        else:
            rows = cur.execute(
                "SELECT * FROM jobs_v2 ORDER BY updated_at DESC LIMIT ?",
                (int(limit),),
            ).fetchall()
        out: List[JobHeader] = []
        for r in rows:
            out.append(
                JobHeader(
                    job_id=r["job_id"],
                    job_name=r["job_name"] or "",
                    prod_file=r["prod_file"] or "",
                    box_file=r["box_file"] or "",
                    status=r["status"] or "",
                    created_at=r["created_at"] or "",
                    updated_at=r["updated_at"] or "",
                    settings_json=r["settings_json"] or "{}",
                    current_koli_no=int(r["current_koli_no"] or 1),
                )
            )
        return out

    def load_job(self, job_id: str) -> Tuple[Optional[JobHeader], List[Dict[str, Any]]]:
        cur = self.conn.cursor()
        h = cur.execute("SELECT * FROM jobs_v2 WHERE job_id=?", (job_id,)).fetchone()
        if not h:
            return None, []
        header = JobHeader(
            job_id=h["job_id"],
            job_name=h["job_name"] or "",
            prod_file=h["prod_file"] or "",
            box_file=h["box_file"] or "",
            status=h["status"] or "",
            created_at=h["created_at"] or "",
            updated_at=h["updated_at"] or "",
            settings_json=h["settings_json"] or "{}",
            current_koli_no=int(h["current_koli_no"] or 1),
        )
        rows = cur.execute(
            "SELECT * FROM job_items_v2 WHERE job_id=? ORDER BY display_id ASC",
            (job_id,),
        ).fetchall()
        items: List[Dict[str, Any]] = []
        for r in rows:
            items.append(
                {
                    "id": int(r["display_id"] or 0),
                    "raw": r["barkod_raw"] or "",
                    "raw_disp": r["barkod_disp"] or "",
                    "status": r["status"] or "PENDING",
                    "box": r["koli_no"] if r["koli_no"] is not None else "-",
                    "label": r["koli_label"] or "-",
                    "in_box": r["in_box"] or "",
                }
            )
        return header, items

    # -------------------------------
    # Items
    # -------------------------------
    def upsert_items_from_work_list(self, job_id: str, work_list: List[Dict[str, Any]]) -> None:
        """UI'daki work_list'i DB'ye aynalar (silme/yeniden numara için en garanti yöntem)."""
        cur = self.conn.cursor()
        cur.execute("DELETE FROM job_items_v2 WHERE job_id=?", (job_id,))
        for it in work_list:
            display_id = int(it.get("id") or 0)
            raw = it.get("raw", "") or ""
            raw_disp = it.get("raw_disp", raw) or raw
            status = it.get("status", "PENDING") or "PENDING"
            koli_no = it.get("box", None)
            try:
                koli_no = int(koli_no) if koli_no not in ("", "-", None) else None
            except Exception:
                koli_no = None
            koli_label = it.get("label", "") or ""
            in_box = it.get("in_box", "") or ""
            cur.execute(
                """
                INSERT INTO job_items_v2
                (job_id, display_id, barkod_raw, barkod_disp, status, koli_no, koli_label, read_at, reject_sent, in_box)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (job_id, display_id, raw, raw_disp, status, koli_no, koli_label, None, 0, in_box),
            )
        self.conn.commit()

    def reset_read_for_ids(self, job_id: str, display_ids: List[int]) -> None:
        """Okunanı sil: kayıt kalsın, sadece okuma durumunu sıfırla."""
        if not display_ids:
            return
        cur = self.conn.cursor()
        q = ",".join("?" for _ in display_ids)
        cur.execute(
            f"""
            UPDATE job_items_v2
            SET status='PENDING', koli_no=NULL, koli_label='-', read_at=NULL, reject_sent=0, in_box=''
            WHERE job_id=? AND display_id IN ({q})
            """,
            [job_id] + [int(x) for x in display_ids],
        )
        self.conn.commit()

    def reset_read_all(self, job_id: str) -> None:
        cur = self.conn.cursor()
        cur.execute(
            """
            UPDATE job_items_v2
            SET status='PENDING', koli_no=NULL, koli_label='-', read_at=NULL, reject_sent=0, in_box=''
            WHERE job_id=?
            """,
            (job_id,),
        )
        self.conn.commit()
