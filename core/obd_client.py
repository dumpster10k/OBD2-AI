from __future__ import annotations

from typing import Any
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


class OBDClient:
    def __init__(self, port=None, connection=None):
        self.connection = connection
        if connection is None:
            try:
                self.connection = obd.OBD(port)
            except Exception:
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
