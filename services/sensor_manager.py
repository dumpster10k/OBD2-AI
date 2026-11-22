from __future__ import annotations

import ast
import operator
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Optional

_SAFE_OPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Pow: operator.pow,
    ast.USub: operator.neg,
    ast.UAdd: operator.pos,
}


@dataclass
class SensorDefinition:
    name: str
    mode: str
    pid: str
    formula: str
    unit: str
    min_value: Optional[float] = None
    max_value: Optional[float] = None
    description: str = ""
    ecu_target: str = "7E0"
    vendor: str = "Standard"
    category: str = "engine"
    standard: str = "SAE_J1979"
    short_name: str = ""


class SensorManager:
    """Zarządza definicjami czujników OBD-II, obliczeniami formuł i walidacją zakresów."""

    def __init__(self):
        self.sensors: dict[str, SensorDefinition] = {}

    @classmethod
    def with_defaults(cls) -> SensorManager:
        """Fabryka inicjalizująca menedżera z pełną bazą sensorów standardowych OBD-II oraz VAG."""
        return cls.with_full_database()

    @classmethod
    def with_standard_obd2(cls) -> SensorManager:
        """Fabryka inicjalizująca wyłącznie czujniki standardowe SAE J1979 Mode 01."""
        from services.sensor_database import get_standard_obd2_sensors

        manager = cls()
        for sensor in get_standard_obd2_sensors():
            manager.add_sensor(sensor)
        return manager

    @classmethod
    def with_vag_sensors(cls) -> SensorManager:
        """Fabryka inicjalizująca wyłącznie czujniki specyficzne dla pojazdów VAG (KWP1281 / UDS)."""
        from services.sensor_database import get_vag_sensors

        manager = cls()
        for sensor in get_vag_sensors():
            manager.add_sensor(sensor)
        return manager

    @classmethod
    def with_full_database(cls) -> SensorManager:
        """Fabryka inicjalizująca bazę standardową OBD-II oraz dedykowaną dla grupy VAG."""
        from services.sensor_database import get_standard_obd2_sensors, get_vag_sensors

        manager = cls()
        for sensor in get_standard_obd2_sensors():
            manager.add_sensor(sensor)
        for sensor in get_vag_sensors():
            manager.add_sensor(sensor)
        return manager

    def add_sensor(self, sensor: SensorDefinition) -> None:
        if not all([sensor.name, sensor.mode, sensor.pid, sensor.formula]):
            raise ValueError("Nazwa, tryb, PID i formuła są wymagane")
        self.sensors[sensor.name] = sensor

    def get_sensor(self, sensor_name: str) -> Optional[SensorDefinition]:
        return self.sensors.get(sensor_name)

    def get_by_pid(self, pid: str, mode: Optional[str] = None) -> Optional[SensorDefinition]:
        """Wyszukuje sensor po identyfikatorze PID (oraz opcjonalnie trybie Mode)."""
        pid_norm = pid.upper().strip()
        mode_norm = mode.upper().strip() if mode else None

        for sensor in self.sensors.values():
            if sensor.pid.upper() == pid_norm:
                if mode_norm is None or sensor.mode.upper() == mode_norm:
                    return sensor
        return None

    def get_by_short_name(self, short_name: str) -> Optional[SensorDefinition]:
        """Wyszukuje sensor po skróconej nazwie technicznej (np. 'RPM', 'ECT', 'VAG_EOT')."""
        sn_norm = short_name.upper().strip()
        for sensor in self.sensors.values():
            if sensor.short_name and sensor.short_name.upper() == sn_norm:
                return sensor
        return None

    def find_sensors(
        self,
        vendor: Optional[str] = None,
        category: Optional[str] = None,
        standard: Optional[str] = None,
        mode: Optional[str] = None,
    ) -> list[SensorDefinition]:
        """Filtruje zarejestrowane sensory według kryteriów producenta, kategorii lub standardu."""
        results: list[SensorDefinition] = []
        for sensor in self.sensors.values():
            if vendor and sensor.vendor.lower() != vendor.lower():
                continue
            if category and sensor.category.lower() != category.lower():
                continue
            if standard and sensor.standard.lower() != standard.lower():
                continue
            if mode and sensor.mode.lower() != mode.lower():
                continue
            results.append(sensor)
        return results

    def list_sensors(self) -> list[SensorDefinition]:
        return list(self.sensors.values())

    def get_active_sensors(self) -> list[SensorDefinition]:
        """Zwraca listę wszystkich zarejestrowanych czujników."""
        return self.list_sensors()

    def list_vendors(self) -> list[str]:
        """Zwraca unikalną listę producentów reprezentowanych w bazie sensorów."""
        return sorted({s.vendor for s in self.sensors.values()})

    def list_categories(self) -> list[str]:
        """Zwraca unikalną listę kategorii parametrów."""
        return sorted({s.category for s in self.sensors.values()})

    def validate_value(self, sensor_name: str, value: float) -> bool:
        sensor = self.sensors.get(sensor_name)
        if not sensor:
            return False
        if sensor.min_value is not None and value < sensor.min_value:
            return False
        if sensor.max_value is not None and value > sensor.max_value:
            return False
        return True

    def evaluate_formula(self, formula: str, data_bytes: Sequence[int]) -> float:
        """Bezpiecznie oblicza wartość liczbową formuły OBD-II z podstawieniem bajtów A, B, C, D."""
        byte_map: dict[str, float] = {
            "A": float(data_bytes[0]) if len(data_bytes) > 0 else 0.0,
            "B": float(data_bytes[1]) if len(data_bytes) > 1 else 0.0,
            "C": float(data_bytes[2]) if len(data_bytes) > 2 else 0.0,
            "D": float(data_bytes[3]) if len(data_bytes) > 3 else 0.0,
        }

        parsed = ast.parse(formula, mode="eval")

        def _eval_node(node: ast.AST) -> float:
            if isinstance(node, ast.Expression):
                return _eval_node(node.body)
            if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
                return float(node.value)
            if isinstance(node, ast.Name):
                var = node.id.upper()
                if var in byte_map:
                    return byte_map[var]
                raise ValueError(f"Nieznana zmienna w formule: {node.id}")
            if isinstance(node, ast.BinOp):
                left = _eval_node(node.left)
                right = _eval_node(node.right)
                op_fn = _SAFE_OPS.get(type(node.op))
                if op_fn is None:
                    raise ValueError(f"Niedozwolony operator: {type(node.op)}")
                return float(op_fn(left, right))
            if isinstance(node, ast.UnaryOp):
                operand = _eval_node(node.operand)
                op_fn = _SAFE_OPS.get(type(node.op))
                if op_fn is None:
                    raise ValueError(f"Niedozwolony operator jednoargumentowy: {type(node.op)}")
                return float(op_fn(operand))
            raise ValueError(f"Niedozwolony węzeł składniowy w formule: {type(node)}")

        return _eval_node(parsed)

    def evaluate_raw(self, name_or_sensor: str | SensorDefinition, data_bytes: Sequence[int]) -> float:
        """Oblicza wartość czujnika z surowych bajtów."""
        if isinstance(name_or_sensor, str):
            if name_or_sensor not in self.sensors:
                raise KeyError(f"Czujnik '{name_or_sensor}' nie jest zarejestrowany.")
            sensor = self.sensors[name_or_sensor]
        else:
            sensor = name_or_sensor

        return self.evaluate_formula(sensor.formula, data_bytes)
