from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

import obd


def _extract_metric(res: Any, val_type: type = int) -> Any:
    """Ekstrahuje wartość z odpowiedzi OBD (obsługuje obd.OBDResponse, pint.Quantity oraz typy prymitywne)."""
    if res is None:
        return None
    val = getattr(res, "value", res)
    if val is None:
        return None
    if hasattr(val, "magnitude"):
        return val_type(val.magnitude)
    return val_type(val)


@dataclass
class ConnectionConfig:
    """Parametry konfiguracyjne połączenia z adapterem OBD-II / ELM327."""

    connection_type: str = "auto"  # "bluetooth_mobile", "usb_laptop", "bluetooth_laptop", "auto"
    port: Optional[str] = None  # np. "/dev/ttyUSB0", "COM3", "OBDII", "00:1D:A5:68:98:8B"
    baudrate: Optional[int] = None  # np. 38400, 115200, 9600
    protocol: Optional[str] = None  # None (auto) lub identyfikator protokołu (np. "6")
    fast: bool = True
    timeout: float = 5.0


class OBDClient:
    def __init__(
        self,
        port: Optional[str] = None,
        connection: Any = None,
        baudrate: Optional[int] = None,
    ):
        self.connection = connection
        self.port = port
        self.baudrate = baudrate
        if connection is None and port is not None:
            self.connect(port=port, baudrate=baudrate)
        elif connection is None:
            try:
                self.connection = obd.OBD()
            except Exception:
                self.connection = None

    def connect(
        self,
        port: Optional[str] = None,
        baudrate: Optional[int] = None,
        protocol: Optional[str] = None,
        fast: bool = True,
        timeout: float = 5.0,
    ) -> bool:
        """Nawiązuje połączenie z adapterem ELM327 (USB / Bluetooth / Serial)."""
        self.disconnect()
        try:
            kwargs: dict[str, Any] = {"fast": fast, "timeout": timeout}
            target_port = port if port is not None else self.port
            if target_port:
                kwargs["portstr"] = target_port
                self.port = target_port
            target_baud = baudrate if baudrate is not None else self.baudrate
            if target_baud:
                kwargs["baudrate"] = int(target_baud)
                self.baudrate = int(target_baud)
            if protocol:
                kwargs["protocol"] = protocol

            self.connection = obd.OBD(**kwargs)
            return self.is_connected()
        except Exception:
            self.connection = None
            return False

    def disconnect(self) -> None:
        """Bezpiecznie zamyka aktywne połączenie z adapterem OBD."""
        if self.connection is not None:
            try:
                if hasattr(self.connection, "close"):
                    self.connection.close()
            except Exception:
                pass
            finally:
                self.connection = None

    def is_connected(self) -> bool:
        return self.connection is not None and self.connection.is_connected()

    def get_dtc(self) -> list[Any]:
        if not self.is_connected():
            return []
        res = self.connection.query(obd.commands.GET_DTC)
        return res.value if res and res.value else []

    def clear_dtc(self) -> bool:
        if not self.is_connected():
            return False
        res = self.connection.query(obd.commands.CLEAR_DTC)
        return bool(res and res.was_successful())

    def get_vin(self) -> Optional[str]:
        """Pobiera numer nadwozia VIN pojazdu (Mode 09 PID 02)."""
        if not self.is_connected():
            return None
        try:
            if hasattr(obd.commands, "VIN"):
                res = self.connection.query(obd.commands.VIN)
                if res and res.value:
                    return str(res.value).strip()
        except Exception:
            pass
        return None

    def get_ecu_name(self) -> Optional[str]:
        """Pobiera oznaczenie lub identyfikację sterownika ECU (Mode 09 PID 04 / 0A)."""
        if not self.is_connected():
            return None
        try:
            cmd = getattr(obd.commands, "CALIBRATION_ID", None) or getattr(obd.commands, "ECU_NAME", None)
            if cmd is not None:
                res = self.connection.query(cmd)
                if res and res.value:
                    if isinstance(res.value, (list, tuple)) and res.value:
                        return str(res.value[0]).strip()
                    return str(res.value).strip()
        except Exception:
            pass
        return None

    def get_telemetry(self) -> dict[str, Any]:
        """Zwraca znormalizowany słownik parametrów telemetrycznych."""
        if not self.is_connected():
            return {
                "rpm": 0,
                "speed": 0,
                "coolant_temp": 0,
                "voltage": 0.0,
            }

        telemetry: dict[str, Any] = {
            "rpm": 0,
            "speed": 0,
            "coolant_temp": 0,
            "voltage": 12.6,
        }

        try:
            rpm_res = self.connection.query(obd.commands.RPM)
            val = _extract_metric(rpm_res, int)
            if val is not None:
                telemetry["rpm"] = val
        except Exception:
            pass

        try:
            speed_res = self.connection.query(obd.commands.SPEED)
            val = _extract_metric(speed_res, int)
            if val is not None:
                telemetry["speed"] = val
        except Exception:
            pass

        try:
            coolant_res = self.connection.query(obd.commands.COOLANT_TEMP)
            val = _extract_metric(coolant_res, int)
            if val is not None:
                telemetry["coolant_temp"] = val
        except Exception:
            pass

        try:
            volt_res = self.connection.query(obd.commands.ELM_VOLTAGE)
            val = _extract_metric(volt_res, float)
            if val is not None:
                telemetry["voltage"] = val
        except Exception:
            pass

        return telemetry
