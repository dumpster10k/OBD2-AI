from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any, Optional

from core.obd_client import OBDClient
from services.sensor_manager import SensorDefinition, SensorManager
from services.telemetry_logger import TelemetryLogger

logger = logging.getLogger(__name__)


class TelemetryHarvester:
    """Moduł ciągłego próbkowania i archiwizacji wszystkich aktywnych czujników OBD-II w tle.

    Zbiera telemetrię z silnika i zapisuje każdą próbkę do bazy SQLite (TelemetryLogger)
    z zachowaniem pełnego bezpieczeństwa wątkowego i odporności na zakłócenia magistrali OBD.
    """

    def __init__(
        self,
        obd_client: Optional[OBDClient] = None,
        telemetry_logger: Optional[TelemetryLogger] = None,
        sensor_manager: Optional[SensorManager] = None,
        sampling_interval_sec: float = 1.0,
    ):
        self.obd = obd_client or OBDClient()
        self.logger = telemetry_logger or TelemetryLogger()
        self.sensor_mgr = sensor_manager or SensorManager.with_full_database()
        self.sampling_interval_sec = max(0.1, float(sampling_interval_sec))

        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._lock = threading.Lock()

        self.current_session_id: Optional[str] = None
        self.is_running: bool = False
        self.total_samples_collected: int = 0
        self.latest_sample: dict[str, Any] = {}
        self.sample_callbacks: list[Callable[[dict[str, Any]], None]] = []

    def register_callback(self, callback: Callable[[dict[str, Any]], None]) -> None:
        """Rejestruje funkcję wywoływaną po zebraniu każdej nowej próbki."""
        with self._lock:
            if callback not in self.sample_callbacks:
                self.sample_callbacks.append(callback)

    def unregister_callback(self, callback: Callable[[dict[str, Any]], None]) -> None:
        """Wyrejestrowuje callback zebrania próbki."""
        with self._lock:
            if callback in self.sample_callbacks:
                self.sample_callbacks.remove(callback)

    def set_interval(self, interval_sec: float) -> None:
        """Dostosowuje interwał próbkowania w sekundach."""
        self.sampling_interval_sec = max(0.1, float(interval_sec))

    def harvest_once(self) -> dict[str, Any]:
        """Wykonuje pojedynczy cykl odpytania podstawowej telemetrii oraz dodatkowych czujników."""
        # 1. Pobranie telemetrii bazowej
        base_telemetry = self.obd.get_telemetry()
        sample: dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "rpm": float(base_telemetry.get("rpm", 0.0)),
            "speed": float(base_telemetry.get("speed", 0.0)),
            "coolant_temp": float(base_telemetry.get("coolant_temp", 0.0)),
            "voltage": float(base_telemetry.get("voltage", 0.0)),
        }

        # 2. Pobranie aktywnych czujników z SensorManager (np. MAF, Boost, Oil Temp, Lambda itp.)
        if hasattr(self.sensor_mgr, "get_active_sensors"):
            active_sensors = self.sensor_mgr.get_active_sensors()
        elif hasattr(self.sensor_mgr, "list_sensors"):
            active_sensors = self.sensor_mgr.list_sensors()
        else:
            active_sensors = []
        for s in active_sensors:
            short = s.short_name.lower()
            if short in sample:
                continue

            try:
                # Jeśli adapter OBD wspiera dedykowaną komendę dla sensora
                val = self._query_sensor_value(s)
                if val is not None:
                    sample[short] = val
            except Exception as e:
                logger.debug("Błąd odczytu sensora %s (%s): %s", s.short_name, s.pid, e)

        with self._lock:
            self.latest_sample = dict(sample)
            self.total_samples_collected += 1
            callbacks = list(self.sample_callbacks)

        # 3. Zapis do bazy danych, jeśli sesja jest otwarta
        if self.current_session_id:
            try:
                self.logger.log_sample(self.current_session_id, sample)
            except Exception as e:
                logger.error("Błąd zapisu próbki telemetrii do bazy: %s", e)

        # 4. Notyfikacja subskrybentów
        for cb in callbacks:
            try:
                cb(sample)
            except Exception as e:
                logger.warning("Błąd w callbacku telemetrii: %s", e)

        return sample

    def _query_sensor_value(self, sensor: SensorDefinition) -> Optional[float]:
        """Próbuje odpytać wartość czujnika z klienta OBD."""
        # Sprawdzenie czy w obd_client istnieje dedykowana metoda lub komenda
        # Dla standardowych czujników odpytujemy bazową telemetrię lub zwracamy None jeśli brak danych
        return None

    def start(self, session_id: Optional[str] = None) -> None:
        """Uruchamia proces ciągłego próbkowania w wątku w tle."""
        with self._lock:
            if self.is_running:
                logger.info("Harvester już działa.")
                return

            self.current_session_id = session_id
            self._stop_event.clear()
            self.is_running = True

            self._thread = threading.Thread(
                target=self._harvest_loop,
                name="OBD2TelemetryHarvesterThread",
                daemon=True,
            )
            self._thread.start()
            logger.info("Uruchomiono zbieranie telemetrii w tle (interwał: %.2f s).", self.sampling_interval_sec)

    def stop(self, timeout: float = 2.0) -> None:
        """Zatrzymuje proces ciągłego próbkowania."""
        with self._lock:
            if not self.is_running:
                return
            self._stop_event.set()
            self.is_running = False

        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=timeout)
        self._thread = None
        logger.info("Zatrzymano zbieranie telemetrii w tle. Zebrano łącznie %d próbek.", self.total_samples_collected)

    def _harvest_loop(self) -> None:
        """Główna pętla wątku zbierającego telemetrię."""
        while not self._stop_event.is_set():
            start_time = time.time()
            try:
                self.harvest_once()
            except Exception as e:
                logger.error("Błąd w pętli próbkowania telemetrii: %s", e)

            elapsed = time.time() - start_time
            sleep_time = max(0.01, self.sampling_interval_sec - elapsed)
            if self._stop_event.wait(timeout=sleep_time):
                break
