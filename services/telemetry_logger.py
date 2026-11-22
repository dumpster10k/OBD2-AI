from __future__ import annotations

import csv
import json
import sqlite3
import uuid
from collections.abc import Generator
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional


def mask_vin(vin: str) -> str:
    """Maskuje numer VIN w logach i bazach danych w celu ochrony prywatności (pkt 7 AGENTS.md)."""
    if not vin:
        return ""
    v = vin.strip()
    if len(v) < 11:
        return "***"
    return f"{v[:3]}***{v[-8:]}"


class TelemetryLogger:
    """Moduł zapisu historii przejazdów, logowania próbkowania telemetrii do bazy SQLite oraz eksportu do CSV."""

    def __init__(self, db_path: str | Path = "data/telemetry.db"):
        self.db_path = Path(db_path)
        if self.db_path.parent and not self.db_path.parent.exists():
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_database()

    @contextmanager
    def _connection(self) -> Generator[sqlite3.Connection, None, None]:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()

    def _init_database(self) -> None:
        """Inicjalizuje schemat bazy SQLite (sesje, próbki telemetrii, zdarzenia audytowe)."""
        with self._connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS sessions (
                    session_id TEXT PRIMARY KEY,
                    vehicle_name TEXT,
                    start_time TEXT,
                    end_time TEXT,
                    initial_dtcs TEXT,
                    final_dtcs TEXT,
                    notes TEXT
                );
                """
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS telemetry_samples (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT,
                    timestamp TEXT,
                    rpm REAL,
                    speed REAL,
                    coolant_temp REAL,
                    voltage REAL,
                    extra_data TEXT,
                    FOREIGN KEY (session_id) REFERENCES sessions (session_id)
                );
                """
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS audit_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT,
                    timestamp TEXT,
                    event_type TEXT,
                    details TEXT,
                    speed_at_event REAL,
                    FOREIGN KEY (session_id) REFERENCES sessions (session_id)
                );
                """
            )
            conn.commit()

    def start_session(
        self,
        vehicle_name: str = "Pojazd",
        initial_dtcs: Optional[list[str]] = None,
        notes: str = "",
    ) -> str:
        """Rozpoczyna nową sesję rejestracji telemetrii."""
        session_id = f"sess_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"
        now_iso = datetime.now(timezone.utc).isoformat()
        dtcs_json = json.dumps(initial_dtcs or [])

        with self._connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO sessions (session_id, vehicle_name, start_time, initial_dtcs, notes)
                VALUES (?, ?, ?, ?, ?);
                """,
                (session_id, vehicle_name, now_iso, dtcs_json, notes),
            )
            conn.commit()
        return session_id

    def log_sample(self, session_id: str, sample: dict[str, Any]) -> None:
        """Zapisuje pojedynczą próbkę telemetrii w bieżącej sesji."""
        now_iso = datetime.now(timezone.utc).isoformat()
        rpm = float(sample.get("rpm", 0))
        speed = float(sample.get("speed", 0))
        coolant = float(sample.get("coolant_temp", 0))
        voltage = float(sample.get("voltage", 0.0))

        extra = {k: v for k, v in sample.items() if k not in ["rpm", "speed", "coolant_temp", "voltage"]}
        extra_json = json.dumps(extra) if extra else "{}"

        with self._connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO telemetry_samples (session_id, timestamp, rpm, speed, coolant_temp, voltage, extra_data)
                VALUES (?, ?, ?, ?, ?, ?, ?);
                """,
                (session_id, now_iso, rpm, speed, coolant, voltage, extra_json),
            )
            conn.commit()

    def log_audit_event(
        self,
        session_id: str,
        event_type: str,
        details: str,
        speed: float = 0.0,
    ) -> None:
        """Zapisuje wpis audytowy (np. kasowanie błędów na postoju, przekroczenie temp)."""
        now_iso = datetime.now(timezone.utc).isoformat()
        with self._connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO audit_events (session_id, timestamp, event_type, details, speed_at_event)
                VALUES (?, ?, ?, ?, ?);
                """,
                (session_id, now_iso, event_type, details, float(speed)),
            )
            conn.commit()

    def end_session(self, session_id: str, final_dtcs: Optional[list[str]] = None) -> None:
        """Kończy sesję rejestracji."""
        now_iso = datetime.now(timezone.utc).isoformat()
        dtcs_json = json.dumps(final_dtcs or [])
        with self._connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                UPDATE sessions
                SET end_time = ?, final_dtcs = ?
                WHERE session_id = ?;
                """,
                (now_iso, dtcs_json, session_id),
            )
            conn.commit()

    def get_samples(self, session_id: str, limit: int = 10000) -> list[dict[str, Any]]:
        """Zwraca listę próbek dla danej sesji."""
        with self._connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT timestamp, rpm, speed, coolant_temp, voltage, extra_data
                FROM telemetry_samples
                WHERE session_id = ?
                ORDER BY id ASC
                LIMIT ?;
                """,
                (session_id, limit),
            )
            rows = cursor.fetchall()
            return [dict(row) for row in rows]

    def get_audit_events(self, session_id: str) -> list[dict[str, Any]]:
        """Zwraca listę zdarzeń audytowych dla danej sesji."""
        with self._connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT timestamp, event_type, details, speed_at_event
                FROM audit_events
                WHERE session_id = ?
                ORDER BY id ASC;
                """,
                (session_id,),
            )
            rows = cursor.fetchall()
            return [dict(row) for row in rows]

    def get_session_summary(self, session_id: str) -> dict[str, Any]:
        """Oblicza statystyki podsumowujące sesję przejazdu."""
        with self._connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT
                    COUNT(*) as sample_count,
                    AVG(rpm) as avg_rpm,
                    MAX(rpm) as max_rpm,
                    AVG(speed) as avg_speed,
                    MAX(speed) as max_speed,
                    MIN(coolant_temp) as min_coolant,
                    MAX(coolant_temp) as max_coolant,
                    MIN(voltage) as min_voltage,
                    MAX(voltage) as max_voltage
                FROM telemetry_samples
                WHERE session_id = ?;
                """,
                (session_id,),
            )
            row = cursor.fetchone()
            if not row or row["sample_count"] == 0:
                return {"sample_count": 0}

            return {
                "sample_count": row["sample_count"],
                "avg_rpm": round(row["avg_rpm"] or 0.0, 1),
                "max_rpm": row["max_rpm"] or 0,
                "avg_speed": round(row["avg_speed"] or 0.0, 1),
                "max_speed": row["max_speed"] or 0,
                "min_coolant": row["min_coolant"] or 0,
                "max_coolant": row["max_coolant"] or 0,
                "min_voltage": round(row["min_voltage"] or 0.0, 1),
                "max_voltage": round(row["max_voltage"] or 0.0, 1),
            }

    def list_sessions(self) -> list[dict[str, Any]]:
        """Zwraca listę wszystkich zarejestrowanych sesji."""
        with self._connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT session_id, vehicle_name, start_time, end_time, initial_dtcs, final_dtcs, notes
                FROM sessions
                ORDER BY start_time DESC;
                """
            )
            return [dict(row) for row in cursor.fetchall()]

    def export_to_csv(self, session_id: str, output_path: str | Path) -> Path:
        """Eksportuje próbki telemetrii do pliku CSV."""
        out = Path(output_path)
        if out.parent and not out.parent.exists():
            out.parent.mkdir(parents=True, exist_ok=True)

        samples = self.get_samples(session_id)
        fieldnames = ["timestamp", "rpm", "speed", "coolant_temp", "voltage"]

        with open(out, mode="w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
            writer.writeheader()
            for sample in samples:
                writer.writerow(sample)

        return out

    def export_audit_log_to_csv(self, session_id: str, output_path: str | Path) -> Path:
        """Eksportuje wpisy audytowe do pliku CSV."""
        out = Path(output_path)
        if out.parent and not out.parent.exists():
            out.parent.mkdir(parents=True, exist_ok=True)

        events = self.get_audit_events(session_id)
        fieldnames = ["timestamp", "event_type", "details", "speed_at_event"]

        with open(out, mode="w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for event in events:
                writer.writerow(event)

        return out
