"""SQLite store for PSUR schedule data enforcing 30-day due dates."""
from __future__ import annotations

import csv
import json
import sqlite3
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

import pandas as pd

from .excel_utils import PSUR_SCHEDULE_PATH, canon_record, read_excel_auto

DB_PATH = Path(__file__).parent.parent / "data" / "psur_schedule.db"
EXPORTS_DIR = DB_PATH.parent / "exports"
EXPORTS_DIR.mkdir(exist_ok=True)

DUE_OFFSET_DAYS = 30

TABLE_SQL = """
    CREATE TABLE IF NOT EXISTS psur_reports (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        td_number TEXT NOT NULL,
        psur_number TEXT,
        type TEXT,
        product_name TEXT,
        catalog_number TEXT,
        writer TEXT,
        email TEXT,
        start_period TEXT,
        end_period TEXT,
        frequency TEXT,
        due_date TEXT,
        status TEXT,
        canada_needed TEXT,
        canada_status TEXT,
        comments TEXT,
        class TEXT,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
        version INTEGER DEFAULT 1
    )
"""

INDEX_SQL = (
    "CREATE INDEX IF NOT EXISTS idx_td_number ON psur_reports(td_number)",
    "CREATE INDEX IF NOT EXISTS idx_psur_number ON psur_reports(psur_number)",
    "CREATE INDEX IF NOT EXISTS idx_writer ON psur_reports(writer)",
    "CREATE INDEX IF NOT EXISTS idx_status ON psur_reports(status)",
    "CREATE INDEX IF NOT EXISTS idx_due_date ON psur_reports(due_date)",
)

COLUMN_LIST = (
    "td_number",
    "psur_number",
    "type",
    "product_name",
    "catalog_number",
    "writer",
    "email",
    "start_period",
    "end_period",
    "frequency",
    "due_date",
    "status",
    "canada_needed",
    "canada_status",
    "comments",
    "class",
    "created_at",
    "updated_at",
    "version",
)


def _parse_date(value: Any) -> Optional[date]:
    if not value:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value).strip()
    if not text:
        return None
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(text).date()
    except ValueError:
        return None


def _format_date(value: Optional[date]) -> str:
    return value.isoformat() if isinstance(value, date) else ""


def _compute_due(end_period: Any, *, offset_days: int = DUE_OFFSET_DAYS) -> Optional[date]:
    end = _parse_date(end_period)
    if not end:
        return None
    return end + timedelta(days=offset_days)


@dataclass
class ScheduleRecord:
    data: Dict[str, Any]

    def ensure_due(self) -> "ScheduleRecord":
        due = _compute_due(self.data.get("end_period"))
        self.data["due_date"] = _format_date(due)
        return self

    def to_dict(self) -> Dict[str, Any]:
        return dict(self.data)


class PSURDatabaseStore:
    """SQLite database store - single source of truth"""

    def __init__(self) -> None:
        self.db_path = DB_PATH
        self.db_path.parent.mkdir(exist_ok=True)
        self.metadata: Dict[str, Any] = {
            "source": str(PSUR_SCHEDULE_PATH),
            "due_offset_days": DUE_OFFSET_DAYS,
        }
        self.init_database()

    # ------------------------------------------------------------------
    # Database primitives
    # ------------------------------------------------------------------
    def get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def init_database(self) -> None:
        conn = self.get_connection()
        cur = conn.cursor()
        cur.execute(TABLE_SQL)
        for statement in INDEX_SQL:
            cur.execute(statement)
        conn.commit()
        conn.close()

        self._ensure_td_duplicates_supported()

        if self.count_records() == 0:
            self.import_from_excel()

    def _ensure_td_duplicates_supported(self) -> None:
        conn = self.get_connection()
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        cur.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='psur_reports'")
        row = cur.fetchone()
        table_sql = row["sql"] if row else None
        if table_sql and "td_number TEXT UNIQUE" in table_sql:
            conn.executescript(
                """
                BEGIN TRANSACTION;
                CREATE TABLE psur_reports_migrated (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    td_number TEXT NOT NULL,
                    psur_number TEXT,
                    type TEXT,
                    product_name TEXT,
                    catalog_number TEXT,
                    writer TEXT,
                    email TEXT,
                    start_period TEXT,
                    end_period TEXT,
                    frequency TEXT,
                    due_date TEXT,
                    status TEXT,
                    canada_needed TEXT,
                    canada_status TEXT,
                    comments TEXT,
                    class TEXT,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    version INTEGER DEFAULT 1
                );
                INSERT INTO psur_reports_migrated (
                    td_number,
                    psur_number,
                    type,
                    product_name,
                    catalog_number,
                    writer,
                    email,
                    start_period,
                    end_period,
                    frequency,
                    due_date,
                    status,
                    canada_needed,
                    canada_status,
                    comments,
                    class,
                    created_at,
                    updated_at,
                    version
                )
                SELECT
                    td_number,
                    psur_number,
                    type,
                    product_name,
                    catalog_number,
                    writer,
                    email,
                    start_period,
                    end_period,
                    frequency,
                    due_date,
                    status,
                    canada_needed,
                    canada_status,
                    comments,
                    class,
                    created_at,
                    updated_at,
                    version
                FROM psur_reports;
                DROP TABLE psur_reports;
                ALTER TABLE psur_reports_migrated RENAME TO psur_reports;
                COMMIT;
                """
            )
            for statement in INDEX_SQL:
                cur.execute(statement)
            conn.commit()
        conn.close()

    def _execute(self, query: str, params: Iterable[Any]) -> int:
        conn = self.get_connection()
        cur = conn.cursor()
        cur.execute(query, tuple(params))
        affected = cur.rowcount
        conn.commit()
        conn.close()
        return affected

    # ------------------------------------------------------------------
    # Import/export helpers
    # ------------------------------------------------------------------
    def import_from_excel(self) -> int:
        df, colmap = read_excel_auto(PSUR_SCHEDULE_PATH)
        conn = self.get_connection()
        cur = conn.cursor()
        cur.execute("DELETE FROM psur_reports")

        inserted = 0
        for _, row in df.iterrows():
            record = canon_record(row, colmap)
            due = _compute_due(record.get("end_period"))
            record["due_date"] = _format_date(due)
            cur.execute(
                """
                INSERT INTO psur_reports (
                    td_number, psur_number, type, product_name, catalog_number,
                    writer, email, start_period, end_period, frequency,
                    due_date, status, canada_needed, canada_status, comments, class
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record.get("td_number"),
                    record.get("psur_number"),
                    record.get("type"),
                    record.get("product_name"),
                    record.get("catalog_number"),
                    record.get("writer"),
                    record.get("email"),
                    record.get("start_period"),
                    record.get("end_period"),
                    record.get("frequency"),
                    record.get("due_date"),
                    record.get("status"),
                    record.get("canada_needed"),
                    record.get("canada_status"),
                    record.get("comments"),
                    record.get("class"),
                ),
            )
            inserted += 1

        conn.commit()
        conn.close()
        self.metadata["last_import"] = datetime.now().isoformat()
        return inserted

    def convert_from_excel(self) -> int:
        return self.import_from_excel()

    # ------------------------------------------------------------------
    # Row post-processing
    # ------------------------------------------------------------------
    def _row_to_record(self, row: sqlite3.Row, *, persist: bool = True) -> ScheduleRecord:
        record = ScheduleRecord(dict(row))
        original_due = record.data.get("due_date")
        record.ensure_due()
        computed_due = record.data.get("due_date")
        if persist and computed_due and original_due != computed_due:
            self._write_due(row["td_number"], computed_due)
        return record

    def _write_due(self, td_number: str, due_iso: str) -> None:
        self._execute(
            "UPDATE psur_reports SET due_date = ?, updated_at = ?, version = version + 1 WHERE td_number = ?",
            (due_iso, datetime.now().isoformat(), td_number),
        )

    def _refresh_due(self, td_number: str) -> None:
        self.find_by_td(td_number, persist=True)

    # ------------------------------------------------------------------
    # CRUD operations
    # ------------------------------------------------------------------
    def count_records(self) -> int:
        conn = self.get_connection()
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM psur_reports")
        count = cur.fetchone()[0]
        conn.close()
        return count

    def get_all(self, *, persist: bool = True) -> List[Dict[str, Any]]:
        conn = self.get_connection()
        cur = conn.cursor()
        cur.execute("SELECT * FROM psur_reports ORDER BY td_number")
        rows = cur.fetchall()
        conn.close()
        return [self._row_to_record(row, persist=persist).to_dict() for row in rows]

    def find_by_td(self, td_number: str, *, persist: bool = True) -> Optional[Dict[str, Any]]:
        conn = self.get_connection()
        cur = conn.cursor()
        cur.execute("SELECT * FROM psur_reports WHERE td_number = ?", (td_number,))
        row = cur.fetchone()
        conn.close()
        if not row:
            return None
        return self._row_to_record(row, persist=persist).to_dict()

    def find_all_by_td(self, td_number: str, *, persist: bool = True) -> List[Dict[str, Any]]:
        conn = self.get_connection()
        cur = conn.cursor()
        cur.execute("SELECT * FROM psur_reports WHERE td_number = ? ORDER BY id", (td_number,))
        rows = cur.fetchall()
        conn.close()
        return [self._row_to_record(row, persist=persist).to_dict() for row in rows]

    def find_by_psur(self, psur_number: str, *, persist: bool = True) -> Optional[Dict[str, Any]]:
        conn = self.get_connection()
        cur = conn.cursor()
        cur.execute("SELECT * FROM psur_reports WHERE psur_number = ?", (psur_number,))
        row = cur.fetchone()
        conn.close()
        if not row:
            return None
        return self._row_to_record(row, persist=persist).to_dict()

    def find_by_query(self, query: str, limit: int = 500) -> List[Dict[str, Any]]:
        like = f"%{query}%"
        conn = self.get_connection()
        cur = conn.cursor()
        cur.execute(
            """
            SELECT * FROM psur_reports
            WHERE td_number LIKE ?
               OR psur_number LIKE ?
               OR product_name LIKE ?
               OR catalog_number LIKE ?
               OR writer LIKE ?
               OR class LIKE ?
               OR status LIKE ?
            ORDER BY td_number
            LIMIT ?
            """,
            (like, like, like, like, like, like, like, limit),
        )
        rows = cur.fetchall()
        conn.close()
        return [self._row_to_record(row).to_dict() for row in rows]

    def filter_records(
        self,
        *,
        writer: Optional[str] = None,
        classification: Optional[str] = None,
        status: Optional[str] = None,
        within_days: Optional[int] = None,
        overdue_only: bool = False,
    ) -> List[Dict[str, Any]]:
        records = self.get_all()
        results = []
        today = datetime.now().date()
        window_end = today + timedelta(days=within_days) if within_days is not None else None

        for record in records:
            due = _parse_date(record.get("due_date"))

            if writer and writer.lower() not in (record.get("writer") or "").lower():
                continue
            if classification and classification.lower() not in (record.get("class") or "").lower():
                continue
            if status and status.lower() not in (record.get("status") or "").lower():
                continue
            if overdue_only:
                if not due or due >= today:
                    continue
            if within_days is not None:
                if not due:
                    continue
                if due < today or due > window_end:
                    continue

            results.append(record)

        results.sort(key=lambda r: (_parse_date(r.get("due_date")) or date.max, r.get("td_number", "")))
        return results

    def update_record(self, td_number: str, updates: Dict[str, Any]) -> bool:
        if not updates:
            return False

        allowed = {k: v for k, v in updates.items() if k not in {"id", "created_at", "updated_at", "version", "td_number"}}
        if not allowed:
            return False

        set_clauses = []
        params: List[Any] = []
        for key, value in allowed.items():
            set_clauses.append(f"{key} = ?")
            params.append(value)

        set_clauses.append("updated_at = ?")
        set_clauses.append("version = version + 1")
        params.append(datetime.now().isoformat())
        params.append(td_number)

        query = f"UPDATE psur_reports SET {', '.join(set_clauses)} WHERE td_number = ?"
        affected = self._execute(query, params)
        if affected:
            self._refresh_due(td_number)
        return affected > 0

    def add_record(self, record: Dict[str, Any]) -> str:
        conn = self.get_connection()
        cur = conn.cursor()

        td_number = record.get("td_number")
        if not td_number:
            cur.execute("SELECT td_number FROM psur_reports WHERE td_number LIKE 'TD%' ORDER BY td_number DESC LIMIT 1")
            row = cur.fetchone()
            if row:
                try:
                    num = int(row["td_number"][2:]) + 1
                except ValueError:
                    num = 1
            else:
                num = 1
            td_number = f"TD{num:03d}"
            record["td_number"] = td_number

        due = _compute_due(record.get("end_period"))
        record["due_date"] = _format_date(due)

        cur.execute(
            """
            INSERT INTO psur_reports (
                td_number, psur_number, type, product_name, catalog_number,
                writer, email, start_period, end_period, frequency,
                due_date, status, canada_needed, canada_status, comments, class
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                record.get("td_number"),
                record.get("psur_number"),
                record.get("type"),
                record.get("product_name"),
                record.get("catalog_number"),
                record.get("writer"),
                record.get("email"),
                record.get("start_period"),
                record.get("end_period"),
                record.get("frequency"),
                record.get("due_date"),
                record.get("status"),
                record.get("canada_needed"),
                record.get("canada_status"),
                record.get("comments"),
                record.get("class"),
            ),
        )
        conn.commit()
        conn.close()
        return td_number

    def delete_record(self, td_number: str) -> bool:
        affected = self._execute("DELETE FROM psur_reports WHERE td_number = ?", (td_number,))
        return affected > 0

    # ------------------------------------------------------------------
    # Higher-level utilities used by tools
    # ------------------------------------------------------------------
    def add_comment(self, td_number: str, comment: str) -> bool:
        record = self.find_by_td(td_number, persist=False)
        if not record:
            return False
        stamped = f"[{datetime.now().strftime('%Y-%m-%d %H:%M')}] {comment}"
        existing = record.get("comments") or ""
        combined = f"{existing}\n{stamped}" if existing else stamped
        return self.update_record(td_number, {"comments": combined})

    def link_references(self, td_number: str, mc_url: Optional[str], sp_url: Optional[str]) -> bool:
        parts = []
        if mc_url:
            parts.append(f"MC: {mc_url}")
        if sp_url:
            parts.append(f"SP: {sp_url}")
        if not parts:
            return False
        return self.add_comment(td_number, " | ".join(parts))

    def bulk_update_status(self, filters: Dict[str, Any], new_status: str) -> int:
        records = self.filter_records(
            writer=filters.get("writer"),
            classification=filters.get("class"),
            status=filters.get("status"),
            within_days=filters.get("within_days"),
            overdue_only=filters.get("overdue_only", False),
        )
        count = 0
        for record in records:
            if self.update_record(record["td_number"], {"status": new_status}):
                count += 1
        return count

    def find_missing_fields(self, fields: List[str]) -> List[Dict[str, Any]]:
        results = []
        for record in self.get_all():
            missing = [field for field in fields if not (record.get(field) or "").strip()]
            if missing:
                record_copy = dict(record)
                record_copy["missing_fields"] = missing
                results.append(record_copy)
        return results

    # ------------------------------------------------------------------
    # Scheduling + projections
    # ------------------------------------------------------------------
    def get_schedule_for_year(self, year: int) -> List[Dict[str, Any]]:
        records = self.get_all()
        selected: List[Dict[str, Any]] = []

        for record in records:
            due = _parse_date(record.get("due_date"))
            if not due:
                if year <= 2025:
                    selected.append(record)
                continue

            if year <= 2025 and due.year <= 2025:
                selected.append(record)
            elif year >= 2026 and due.year >= 2026:
                selected.append(record)

        selected.sort(key=lambda r: (_parse_date(r.get("due_date")) or date.max, r.get("td_number", "")))
        return selected

    # ------------------------------------------------------------------
    # Export helpers
    # ------------------------------------------------------------------
    def export_csv(self, filter_criteria: Optional[Dict[str, Any]], filename: str) -> str:
        records = self.filter_records(
            writer=(filter_criteria or {}).get("writer"),
            classification=(filter_criteria or {}).get("class"),
            status=(filter_criteria or {}).get("status"),
            within_days=(filter_criteria or {}).get("within_days"),
            overdue_only=(filter_criteria or {}).get("overdue_only", False),
        )
        path = EXPORTS_DIR / filename
        fieldnames = list(records[0].keys()) if records else ["td_number"]
        with path.open("w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(records)
        return str(path)

    def export_excel(self, records: Optional[List[Dict[str, Any]]], filename: str) -> str:
        if records is None:
            records = self.get_all()
        df = pd.DataFrame(records)
        path = EXPORTS_DIR / filename
        df.to_excel(path, index=False)
        return str(path)

    def export_calendar(self, filter_criteria: Optional[Dict[str, Any]], within_days: Optional[int], filename: str) -> str:
        records = self.filter_records(
            writer=(filter_criteria or {}).get("writer"),
            classification=(filter_criteria or {}).get("class"),
            status=(filter_criteria or {}).get("status"),
            within_days=within_days,
        )
        ics_lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//PSUR OPS//Schedule//EN"]
        for record in records:
            due = _parse_date(record.get("due_date")) or datetime.now().date()
            uid = f"{record.get('td_number')}@psur-ops"
            summary = f"{record.get('td_number')} {record.get('product_name', '')}"
            description = json.dumps(record, ensure_ascii=False)
            ics_lines.extend(
                [
                    "BEGIN:VEVENT",
                    f"UID:{uid}",
                    f"DTSTAMP:{datetime.utcnow().strftime('%Y%m%dT%H%M%SZ')}",
                    f"DTSTART;VALUE=DATE:{due.strftime('%Y%m%d')}",
                    f"SUMMARY:{summary}",
                    f"DESCRIPTION:{description}",
                    "END:VEVENT",
                ]
            )
        ics_lines.append("END:VCALENDAR")
        path = EXPORTS_DIR / filename
        path.write_text("\n".join(ics_lines), encoding="utf-8")
        return str(path)

    # ------------------------------------------------------------------
    # Diagnostics
    # ------------------------------------------------------------------
    def get_stats(self) -> Dict[str, Any]:
        records = self.get_all()
        stats: Dict[str, Any] = {
            "total_records": len(records),
            "by_status": {},
            "by_class": {},
            "by_writer": {},
            "overdue": 0,
            "due_soon": 0,
        }
        today = datetime.now().date()
        thirty = today + timedelta(days=30)

        for record in records:
            status = (record.get("status") or "Unknown").strip() or "Unknown"
            stats["by_status"][status] = stats["by_status"].get(status, 0) + 1

            klass = (record.get("class") or "Unknown").strip() or "Unknown"
            stats["by_class"][klass] = stats["by_class"].get(klass, 0) + 1

            writer = (record.get("writer") or "Unassigned").strip() or "Unassigned"
            stats["by_writer"][writer] = stats["by_writer"].get(writer, 0) + 1

            due = _parse_date(record.get("due_date"))
            if due and due < today:
                stats["overdue"] += 1
            if due and today <= due <= thirty:
                stats["due_soon"] += 1

        stats["duplicate_td_numbers"] = self.find_duplicate_td_numbers()

        return stats

    def find_duplicate_td_numbers(self) -> List[str]:
        conn = self.get_connection()
        cur = conn.cursor()
        cur.execute(
            """
            SELECT td_number
            FROM psur_reports
            WHERE td_number IS NOT NULL
            GROUP BY td_number
            HAVING COUNT(*) > 1
            ORDER BY td_number
            """
        )
        duplicates = [row[0] for row in cur.fetchall()]
        conn.close()
        return duplicates


_store: Optional[PSURDatabaseStore] = None


def get_store() -> PSURDatabaseStore:
    global _store
    if _store is None:
        _store = PSURDatabaseStore()
    return _store
