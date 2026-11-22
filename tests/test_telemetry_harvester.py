from __future__ import annotations

import time
from typing import Any
from unittest.mock import MagicMock

from services.telemetry_harvester import TelemetryHarvester


class DummyOBD:
    def __init__(self, rpm: float = 850.0, speed: float = 0.0):
        self.rpm = rpm
        self.speed = speed

    def get_telemetry(self) -> dict[str, Any]:
        return {
            "rpm": self.rpm,
            "speed": self.speed,
            "coolant_temp": 89.0,
            "voltage": 14.1,
        }


def test_telemetry_harvester_single_harvest() -> None:
    obd = DummyOBD(rpm=1200, speed=45)
    mock_logger = MagicMock()
    harvester = TelemetryHarvester(
        obd_client=obd,  # type: ignore
        telemetry_logger=mock_logger,
        sampling_interval_sec=0.1,
    )

    sample = harvester.harvest_once()
    assert sample["rpm"] == 1200.0
    assert sample["speed"] == 45.0
    assert sample["coolant_temp"] == 89.0
    assert sample["voltage"] == 14.1
    assert "timestamp" in sample
    assert harvester.total_samples_collected == 1
    # Ponieważ brak session_id, log_sample nie jest wołany
    mock_logger.log_sample.assert_not_called()


def test_telemetry_harvester_with_session() -> None:
    obd = DummyOBD()
    mock_logger = MagicMock()
    harvester = TelemetryHarvester(
        obd_client=obd,  # type: ignore
        telemetry_logger=mock_logger,
    )
    harvester.current_session_id = "test_sess_001"

    sample = harvester.harvest_once()
    mock_logger.log_sample.assert_called_once_with("test_sess_001", sample)


def test_telemetry_harvester_callbacks() -> None:
    obd = DummyOBD()
    harvester = TelemetryHarvester(obd_client=obd)  # type: ignore

    received: list[dict[str, Any]] = []

    def cb(s: dict[str, Any]) -> None:
        received.append(s)

    harvester.register_callback(cb)
    harvester.harvest_once()
    assert len(received) == 1

    harvester.unregister_callback(cb)
    harvester.harvest_once()
    assert len(received) == 1


def test_telemetry_harvester_background_thread() -> None:
    obd = DummyOBD()
    mock_logger = MagicMock()
    harvester = TelemetryHarvester(
        obd_client=obd,  # type: ignore
        telemetry_logger=mock_logger,
        sampling_interval_sec=0.05,
    )

    harvester.start(session_id="sess_live")
    assert harvester.is_running is True

    # Ponowne wywołanie start nie tworzy drugiego wątku
    harvester.start(session_id="sess_live")

    time.sleep(0.15)
    harvester.stop(timeout=1.0)

    assert harvester.is_running is False
    assert harvester.total_samples_collected >= 1
    assert mock_logger.log_sample.call_count >= 1
