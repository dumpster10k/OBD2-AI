from services.sensor_manager import SensorDefinition, SensorManager
import pytest


def test_sensor_range_validation():
    manager = SensorManager()
    manager.add_sensor(SensorDefinition("Oil temp", "22", "1126", "A/10", "°C", 0, 180))
    assert manager.validate_value("Oil temp", 90)
    assert not manager.validate_value("Oil temp", 250)


def test_sensor_requires_definition_fields():
    with pytest.raises(ValueError):
        SensorManager().add_sensor(SensorDefinition("", "22", "1126", "A/10", "°C"))
