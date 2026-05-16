"""SQLite staging storage and optional MySQL synchronization."""

from __future__ import annotations

import json
import os
import sqlite3
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional


@dataclass(frozen=True)
class MySQLConfig:
    host: str
    port: int
    user: str
    password: str
    database: str
    charset: str = "utf8mb4"


class DatabaseService:
    def __init__(self, sqlite_path: str | Path = "data/intake_records.sqlite3") -> None:
        self.sqlite_path = Path(sqlite_path)
        self.sqlite_path.parent.mkdir(parents=True, exist_ok=True)
        self._session_record_ids: list[int] = []
        self._lock = threading.Lock()
        self._init_sqlite()

    def insert_local_record(self, record: dict[str, Any]) -> dict[str, Any]:
        now = time.strftime("%Y-%m-%d %H:%M:%S")
        intake_datetime = record.get("intake_datetime") or now
        intake_date = str(intake_datetime)[:10]
        values = {
            "batch_id": record.get("batch_id"),
            "product_name": record.get("product_name") or "",
            "weight": self._float_or_none(record.get("weight")),
            "unit": record.get("unit") or "kg",
            "recorder": record.get("recorder") or "web",
            "intake_datetime": intake_datetime,
            "intake_date": intake_date,
            "detection_model": record.get("detection_model") or "yolov11",
            "ocr_model": record.get("ocr_model") or "paddleocr",
            "trigger_type": record.get("trigger_type") or "manual",
            "frames_json": json.dumps(record.get("frames") or {}, ensure_ascii=False),
            "raw_result_json": json.dumps(record.get("raw_result") or {}, ensure_ascii=False),
            "notes": record.get("notes") or "",
            "created_at": now,
            "updated_at": now,
        }
        with self._connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO intake_records (
                    batch_id, product_name, weight, unit, recorder, intake_datetime,
                    intake_date, detection_model, ocr_model, trigger_type, frames_json,
                    raw_result_json, notes, upload_status, created_at, updated_at
                ) VALUES (
                    :batch_id, :product_name, :weight, :unit, :recorder, :intake_datetime,
                    :intake_date, :detection_model, :ocr_model, :trigger_type, :frames_json,
                    :raw_result_json, :notes, 'pending', :created_at, :updated_at
                )
                """,
                values,
            )
            record_id = int(cursor.lastrowid)
            conn.commit()

        with self._lock:
            self._session_record_ids.append(record_id)
        return self.get_local_record(record_id) or {}

    def get_local_record(self, record_id: int) -> Optional[dict[str, Any]]:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM intake_records WHERE id = ?", (record_id,)).fetchone()
        return self._row_to_dict(row) if row else None

    def list_session_records(self, pending_only: bool = True) -> list[dict[str, Any]]:
        with self._lock:
            ids = list(self._session_record_ids)
        if not ids:
            return []
        placeholders = ",".join("?" for _ in ids)
        query = f"SELECT * FROM intake_records WHERE id IN ({placeholders})"
        params: list[Any] = list(ids)
        if pending_only:
            query += " AND upload_status = 'pending'"
        query += " ORDER BY id DESC"
        with self._connect() as conn:
            rows = conn.execute(query, params).fetchall()
        return [self._row_to_dict(row) for row in rows]

    def upload_session_pending_to_mysql(self) -> dict[str, Any]:
        records = self.list_session_records(pending_only=True)
        if not records:
            return {"uploaded": 0, "message": "本地数据库暂无待上传数据"}

        mysql_config = self._mysql_config_from_env()
        if mysql_config is None:
            raise RuntimeError("MySQL is not configured. Set MYSQL_HOST, MYSQL_USER, MYSQL_PASSWORD and MYSQL_DATABASE.")

        self._insert_mysql_records(mysql_config, records)
        uploaded_at = time.strftime("%Y-%m-%d %H:%M:%S")
        ids = [record["id"] for record in records]
        placeholders = ",".join("?" for _ in ids)
        with self._connect() as conn:
            conn.execute(
                f"""
                UPDATE intake_records
                SET upload_status = 'uploaded', mysql_uploaded_at = ?, updated_at = ?
                WHERE id IN ({placeholders})
                """,
                [uploaded_at, uploaded_at, *ids],
            )
            conn.commit()
        return {"uploaded": len(records), "message": "数据已入库，本地数据库暂无待上传数据"}

    def list_mysql_records(self, intake_date: str) -> dict[str, Any]:
        mysql_config = self._mysql_config_from_env()
        if mysql_config is None:
            return {"configured": False, "records": [], "message": "MySQL is not configured"}

        try:
            import pymysql  # type: ignore
        except ImportError:
            return {"configured": False, "records": [], "message": "PyMySQL is not installed"}

        connection = pymysql.connect(
            host=mysql_config.host,
            port=mysql_config.port,
            user=mysql_config.user,
            password=mysql_config.password,
            database=mysql_config.database,
            charset=mysql_config.charset,
            cursorclass=pymysql.cursors.DictCursor,
        )
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT id, batch_id, product_name, weight, unit, recorder,
                           intake_datetime, intake_date, detection_model, ocr_model,
                           trigger_type, notes, created_at
                    FROM intake_records
                    WHERE intake_date = %s
                    ORDER BY intake_datetime DESC, id DESC
                    """,
                    (intake_date,),
                )
                return {"configured": True, "records": list(cursor.fetchall())}
        finally:
            connection.close()

    def _insert_mysql_records(self, config: MySQLConfig, records: list[dict[str, Any]]) -> None:
        try:
            import pymysql  # type: ignore
        except ImportError as exc:
            raise RuntimeError("PyMySQL is not installed. Run `pip install PyMySQL`.") from exc

        connection = pymysql.connect(
            host=config.host,
            port=config.port,
            user=config.user,
            password=config.password,
            database=config.database,
            charset=config.charset,
        )
        try:
            with connection.cursor() as cursor:
                cursor.executemany(
                    """
                    INSERT INTO intake_records (
                        batch_id, product_name, weight, unit, recorder, intake_datetime,
                        intake_date, detection_model, ocr_model, trigger_type, frames_json,
                        raw_result_json, notes, created_at, updated_at
                    ) VALUES (
                        %(batch_id)s, %(product_name)s, %(weight)s, %(unit)s, %(recorder)s,
                        %(intake_datetime)s, %(intake_date)s, %(detection_model)s,
                        %(ocr_model)s, %(trigger_type)s, %(frames_json)s,
                        %(raw_result_json)s, %(notes)s, %(created_at)s, %(updated_at)s
                    )
                    """,
                    records,
                )
            connection.commit()
        finally:
            connection.close()

    def _init_sqlite(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS intake_records (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    batch_id TEXT,
                    product_name TEXT NOT NULL,
                    weight REAL,
                    unit TEXT NOT NULL DEFAULT 'kg',
                    recorder TEXT,
                    intake_datetime TEXT NOT NULL,
                    intake_date TEXT NOT NULL,
                    detection_model TEXT,
                    ocr_model TEXT,
                    trigger_type TEXT,
                    frames_json TEXT,
                    raw_result_json TEXT,
                    notes TEXT,
                    upload_status TEXT NOT NULL DEFAULT 'pending',
                    mysql_uploaded_at TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_intake_records_date ON intake_records(intake_date)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_intake_records_upload ON intake_records(upload_status)")
            conn.commit()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.sqlite_path)
        connection.row_factory = sqlite3.Row
        return connection

    @staticmethod
    def _row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
        result = dict(row)
        for key in ("frames_json", "raw_result_json"):
            if result.get(key):
                result[key.replace("_json", "")] = json.loads(result[key])
        return result

    @staticmethod
    def _mysql_config_from_env() -> Optional[MySQLConfig]:
        host = os.getenv("MYSQL_HOST")
        user = os.getenv("MYSQL_USER")
        password = os.getenv("MYSQL_PASSWORD")
        database = os.getenv("MYSQL_DATABASE")
        if not all([host, user, password, database]):
            return None
        return MySQLConfig(
            host=host or "",
            port=int(os.getenv("MYSQL_PORT", "3306")),
            user=user or "",
            password=password or "",
            database=database or "",
            charset=os.getenv("MYSQL_CHARSET", "utf8mb4"),
        )

    @staticmethod
    def _float_or_none(value: Any) -> Optional[float]:
        if value in (None, ""):
            return None
        return float(value)
