from dataclasses import dataclass
from typing import Optional


@dataclass
class SensorDefinition:
    name: str
    mode: str
    pid: str
    formula: str
    unit: str
    min_value: Optional[float] = None
    max_value: Optional[float] = None


class SensorManager:
    def __init__(self):
        self.sensors = {}

    def add_sensor(self, sensor: SensorDefinition):
        if not all([sensor.name, sensor.mode, sensor.pid, sensor.formula]):
            raise ValueError("Nazwa, tryb, PID i formuła są wymagane")
        self.sensors[sensor.name] = sensor

    def validate_value(self, sensor_name, value):
        sensor = self.sensors[sensor_name]
        if sensor.min_value is not None and value < sensor.min_value:
            return False
        if sensor.max_value is not None and value > sensor.max_value:
            return False
        return True
