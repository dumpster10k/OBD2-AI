from __future__ import annotations

import pytest

from services.sensor_manager import SensorDefinition, SensorManager


def test_sensor_range_validation():
    manager = SensorManager()
    manager.add_sensor(SensorDefinition("Oil temp", "22", "1126", "A/10", "°C", 0, 180))
    assert manager.validate_value("Oil temp", 90)
    assert not manager.validate_value("Oil temp", 250)
    assert not manager.validate_value("Oil temp", -10)


def test_sensor_requires_definition_fields():
    with pytest.raises(ValueError):
        SensorManager().add_sensor(SensorDefinition("", "22", "1126", "A/10", "°C"))
    with pytest.raises(ValueError):
        SensorManager().add_sensor(SensorDefinition("Test", "", "1126", "A/10", "°C"))


def test_sensor_formula_evaluation():
    manager = SensorManager()

    # Formuła prosta A
    assert manager.evaluate_formula("A", [50]) == 50.0

    # Formuła dwubajtowa (A*256 + B)/4 - 40
    # A=0x01 (1), B=0x2C (44) -> (256 + 44)/4 - 40 = 300/4 - 40 = 75 - 40 = 35.0
    val = manager.evaluate_formula("(A*256 + B)/4 - 40", [0x01, 0x2C])
    assert val == 35.0

    # Formuła z mnożnikiem i dzielnikiem (A*256 + B)/10
    # A=3, B=232 -> (768 + 232)/10 = 1000/10 = 100.0
    assert manager.evaluate_formula("(A*256 + B)/10", [3, 232]) == 100.0

    # Formuła z 4 bajtami
    assert manager.evaluate_formula("A + B + C + D", [10, 20, 30, 40]) == 100.0


def test_sensor_manager_evaluate_raw():
    manager = SensorManager()
    sensor = SensorDefinition(
        name="Engine Oil Temp",
        mode="22",
        pid="1126",
        formula="(A*256 + B)/10",
        unit="°C",
        min_value=-40,
        max_value=160,
    )
    manager.add_sensor(sensor)

    # Przekazanie nazwy sensora
    res = manager.evaluate_raw("Engine Oil Temp", [3, 144])  # (768+144)/10 = 91.2
    assert abs(res - 91.2) < 1e-4

    # Przekazanie obiektu SensorDefinition
    res2 = manager.evaluate_raw(sensor, [3, 144])
    assert abs(res2 - 91.2) < 1e-4

    # Nieznany sensor
    with pytest.raises(KeyError):
        manager.evaluate_raw("Unknown", [1, 2])


def test_sensor_manager_defaults_and_lookup():
    manager = SensorManager.with_defaults()
    sensors = manager.list_sensors()
    assert len(sensors) >= 4

    names = [s.name for s in sensors]
    assert "Engine Oil Temp" in names
    assert "Boost Pressure" in names
    assert "Transmission Fluid Temp" in names

    oil_sensor = manager.get_sensor("Engine Oil Temp")
    assert oil_sensor is not None
    assert oil_sensor.unit == "°C"
    assert manager.validate_value("Engine Oil Temp", 95) is True
