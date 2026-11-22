from __future__ import annotations

import csv
import sqlite3
from pathlib import Path
import pytest

from services.telemetry_logger import TelemetryLogger, mask_vin
from ui.main import DashboardController
from core.obd_client import OBDClient


class FakeConnectionForLogger:
    def __init__(self, dtc=None, rpm=2000, speed=50, coolant=90, voltage=14.0):
        self.dtc = dtc or []
        self.rpm = rpm
        self.speed = speed
        self.coolant = coolant
        self.voltage = voltage

    def is_connected(self):
        return True

    def query(self, cmd):
        name = getattr(cmd, "name", "")
        if "GET_DTC" in name:
            class DTCRes:
                value = self.dtc
            return DTCRes()
        if "CLEAR_DTC" in name:
            self.dtc = []
            class ClearRes:
                def was_successful(self):
                    return True
            return ClearRes()
        if "RPM" in name:
            return type("Res", (), {"value": type("Val", (), {"magnitude": self.rpm})()})()
        if "SPEED" in name:
            return type("Res", (), {"value": type("Val", (), {"magnitude": self.speed})()})()
        if "COOLANT" in name:
            return type("Res", (), {"value": type("Val", (), {"magnitude": self.coolant})()})()
        if "VOLTAGE" in name:
            return type("Res", (), {"value": type("Val", (), {"magnitude": self.voltage})()})()
        return None


def test_telemetry_logger_init_and_tables(tmp_path: Path):
    db_file = tmp_path / "test_telemetry.db"
    logger = TelemetryLogger(db_path=db_file)
    assert db_file.exists()

    with sqlite3.connect(db_file) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = {row[0] for row in cursor.fetchall()}
        assert "sessions" in tables
        assert "telemetry_samples" in tables
        assert "audit_events" in tables


def test_telemetry_logger_session_lifecycle(tmp_path: Path):
    db_file = tmp_path / "test_lifecycle.db"
    logger = TelemetryLogger(db_path=db_file)

    session_id = logger.start_session(vehicle_name="Golf VII", initial_dtcs=["P0300"])
    assert session_id is not None
    assert len(session_id) > 5

    logger.log_sample(
        session_id=session_id,
        sample={"rpm": 2500, "speed": 60, "coolant_temp": 89, "voltage": 14.1},
    )
    logger.log_sample(
        session_id=session_id,
        sample={"rpm": 3000, "speed": 75, "coolant_temp": 92, "voltage": 14.2},
    )

    samples = logger.get_samples(session_id=session_id)
    assert len(samples) == 2
    assert samples[0]["rpm"] == 2500
    assert samples[1]["speed"] == 75

    logger.end_session(session_id=session_id, final_dtcs=[])
    sessions = logger.list_sessions()
    assert len(sessions) == 1
    assert sessions[0]["session_id"] == session_id
    assert sessions[0]["end_time"] is not None


def test_telemetry_logger_audit_event_logging(tmp_path: Path):
    logger = TelemetryLogger(db_path=tmp_path / "test_audit.db")
    session_id = logger.start_session()

    logger.log_audit_event(
        session_id=session_id,
        event_type="DTC_CLEARED",
        details="Kasowanie kodów P0300 na postoju",
        speed=0.0,
    )

    events = logger.get_audit_events(session_id=session_id)
    assert len(events) == 1
    assert events[0]["event_type"] == "DTC_CLEARED"
    assert events[0]["speed_at_event"] == 0.0
    assert "P0300" in events[0]["details"]


def test_telemetry_logger_session_summary(tmp_path: Path):
    logger = TelemetryLogger(db_path=tmp_path / "test_summary.db")
    session_id = logger.start_session()

    logger.log_sample(session_id, {"rpm": 1000, "speed": 20, "coolant_temp": 80, "voltage": 13.5})
    logger.log_sample(session_id, {"rpm": 3000, "speed": 80, "coolant_temp": 95, "voltage": 14.5})

    summary = logger.get_session_summary(session_id)
    assert summary["sample_count"] == 2
    assert summary["avg_rpm"] == 2000.0
    assert summary["max_rpm"] == 3000
    assert summary["avg_speed"] == 50.0
    assert summary["max_speed"] == 80
    assert summary["min_coolant"] == 80
    assert summary["max_coolant"] == 95
    assert summary["min_voltage"] == 13.5
    assert summary["max_voltage"] == 14.5


def test_telemetry_logger_export_to_csv(tmp_path: Path):
    logger = TelemetryLogger(db_path=tmp_path / "test_export.db")
    session_id = logger.start_session()

    logger.log_sample(session_id, {"rpm": 1500, "speed": 40, "coolant_temp": 85, "voltage": 14.0})
    logger.log_sample(session_id, {"rpm": 2200, "speed": 60, "coolant_temp": 88, "voltage": 14.1})

    csv_path = tmp_path / "telemetry_export.csv"
    exported = logger.export_to_csv(session_id, csv_path)
    assert exported.exists()

    with open(csv_path, newline="", encoding="utf-8") as f:
        reader = list(csv.DictReader(f))
        assert len(reader) == 2
        assert float(reader[0]["rpm"]) == 1500
        assert float(reader[1]["speed"]) == 60
        assert float(reader[0]["voltage"]) == 14.0


def test_telemetry_logger_export_audit_to_csv(tmp_path: Path):
    logger = TelemetryLogger(db_path=tmp_path / "test_audit_export.db")
    session_id = logger.start_session()

    logger.log_audit_event(session_id, "TEST_EVENT", "Szczegóły zdarzenia testowego", speed=0.0)
    csv_path = tmp_path / "audit_export.csv"
    exported = logger.export_audit_log_to_csv(session_id, csv_path)
    assert exported.exists()

    with open(csv_path, newline="", encoding="utf-8") as f:
        reader = list(csv.DictReader(f))
        assert len(reader) == 1
        assert reader[0]["event_type"] == "TEST_EVENT"


def test_telemetry_logger_empty_session_export(tmp_path: Path):
    logger = TelemetryLogger(db_path=tmp_path / "test_empty.db")
    session_id = logger.start_session()

    csv_path = tmp_path / "empty_export.csv"
    exported = logger.export_to_csv(session_id, csv_path)
    assert exported.exists()

    with open(csv_path, newline="", encoding="utf-8") as f:
        reader = list(csv.DictReader(f))
        assert len(reader) == 0


def test_mask_vin():
    assert mask_vin("WAUZZZ8K9BA123456") == "WAU***BA123456"
    assert mask_vin("SHORT") == "***"
    assert mask_vin("") == ""


def test_dashboard_controller_telemetry_logging_and_export(tmp_path: Path):
    db_file = tmp_path / "controller_telemetry.db"
    logger = TelemetryLogger(db_path=db_file)

    fake_conn = FakeConnectionForLogger(dtc=["P0300"], rpm=2100, speed=50, coolant=90, voltage=14.0)
    client = OBDClient(connection=fake_conn)
    controller = DashboardController(obd_client=client, telemetry_logger=logger)

    # Domyślnie nagrywanie sesji wyłączone
    assert controller.is_logging is False

    # Włącz nagrywanie
    sess_id = controller.start_telemetry_logging(vehicle_name="Audi A4")
    assert controller.is_logging is True
    assert sess_id is not None

    # Odświeżenie telemetrii automatycznie zapisuje próbkę
    controller.refresh_telemetry()
    samples = logger.get_samples(sess_id)
    assert len(samples) == 1
    assert samples[0]["rpm"] == 2100

    # Kasowanie kodów na postoju loguje zdarzenie audytowe
    fake_conn.speed = 0
    controller.refresh_telemetry()
    controller.request_clear_dtc()
    controller.confirm_clear_dtc()

    events = logger.get_audit_events(sess_id)
    assert len(events) >= 1
    assert any("DTC_CLEARED" in e["event_type"] for e in events)

    # Eksport CSV z poziomu kontrolera
    out_csv = tmp_path / "exported_from_controller.csv"
    res = controller.export_telemetry_csv(str(out_csv))
    assert res["success"] is True
    assert out_csv.exists()

    # Zatrzymanie nagrywania
    controller.stop_telemetry_logging()
    assert controller.is_logging is False
