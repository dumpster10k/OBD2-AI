from __future__ import annotations

import ast
import operator
from dataclasses import dataclass
from typing import Any, Optional, Sequence

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


class SensorManager:
    """Zarządza definicjami czujników OBD-II, obliczeniami formuł i walidacją zakresów."""

    def __init__(self):
        self.sensors: dict[str, SensorDefinition] = {}

    @classmethod
    def with_defaults(cls) -> SensorManager:
        """Fabryka inicjalizująca menedżera z bazą popularnych sensorów niestandardowych (UDS Mode 22)."""
        manager = cls()
        manager.add_sensor(
            SensorDefinition(
                name="Engine Oil Temp",
                mode="22",
                pid="1126",
                formula="(A*256 + B)/10",
                unit="°C",
                min_value=-40,
                max_value=160,
                description="Temperatura oleju silnikowego (UDS Mode 22)",
            )
        )
        manager.add_sensor(
            SensorDefinition(
                name="Boost Pressure",
                mode="22",
                pid="1155",
                formula="(A*256 + B)*0.01",
                unit="bar",
                min_value=0.0,
                max_value=3.5,
                description="Rzeczywiste ciśnienie doładowania turbosprężarki",
            )
        )
        manager.add_sensor(
            SensorDefinition(
                name="Transmission Fluid Temp",
                mode="22",
                pid="1E50",
                formula="A - 40",
                unit="°C",
                min_value=-40,
                max_value=150,
                description="Temperatura oleju w automatycznej skrzyni biegów",
            )
        )
        manager.add_sensor(
            SensorDefinition(
                name="DPF Soot Mass",
                mode="22",
                pid="2010",
                formula="(A*256 + B)*0.01",
                unit="g",
                min_value=0.0,
                max_value=80.0,
                description="Masa sadzy w filtrze cząstek stałych (DPF)",
            )
        )
        return manager

    def add_sensor(self, sensor: SensorDefinition) -> None:
        if not all([sensor.name, sensor.mode, sensor.pid, sensor.formula]):
            raise ValueError("Nazwa, tryb, PID i formuła są wymagane")
        self.sensors[sensor.name] = sensor

    def get_sensor(self, sensor_name: str) -> Optional[SensorDefinition]:
        return self.sensors.get(sensor_name)

    def list_sensors(self) -> list[SensorDefinition]:
        return list(self.sensors.values())

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
