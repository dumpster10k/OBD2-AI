from __future__ import annotations

import pytest

from services.sensor_database import get_standard_obd2_sensors, get_vag_sensors
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


def test_standard_obd2_sensor_database():
    sensors = get_standard_obd2_sensors()
    assert len(sensors) >= 20

    manager = SensorManager.with_standard_obd2()
    assert len(manager.list_sensors()) == len(sensors)

    # Weryfikacja RPM (Mode 01 PID 0C): (A*256 + B) / 4
    # A=0x0F (15), B=0xA0 (160) -> (3840 + 160)/4 = 4000/4 = 1000 RPM
    rpm_val = manager.evaluate_raw("Engine RPM", [0x0F, 0xA0])
    assert rpm_val == 1000.0
    assert manager.validate_value("Engine RPM", rpm_val) is True

    # Weryfikacja Coolant Temp (Mode 01 PID 05): A - 40
    # A=130 -> 130 - 40 = 90 °C
    ect_val = manager.evaluate_raw("Engine Coolant Temp", [130])
    assert ect_val == 90.0
    assert manager.validate_value("Engine Coolant Temp", ect_val) is True

    # Weryfikacja Napięcia ECU (Mode 01 PID 42): (A*256 + B)/1000
    # A=0x36 (54), B=0xB0 (176) -> (13824 + 176)/1000 = 14.0 V
    volt_val = manager.evaluate_raw("Control Module Voltage", [0x36, 0xB0])
    assert abs(volt_val - 14.0) < 1e-3

    # Weryfikacja wyszukiwania po PID
    rpm_sensor = manager.get_by_pid("0C", mode="01")
    assert rpm_sensor is not None
    assert rpm_sensor.name == "Engine RPM"

    # Weryfikacja wyszukiwania po short_name
    speed_sensor = manager.get_by_short_name("SPEED")
    assert speed_sensor is not None
    assert speed_sensor.pid == "0D"


def test_vag_sensor_database_kwp_and_uds():
    sensors = get_vag_sensors()
    assert len(sensors) >= 20

    manager = SensorManager.with_vag_sensors()
    assert len(manager.list_sensors()) == len(sensors)

    # 1. KWP1281: Torsion Value (kąt synchronizacji wałka rozrządu w 1.9/2.0 TDI PD)
    # Formuła: (A - 128) * 0.1
    # A = 128 -> 0.0 °KW
    torsion_zero = manager.evaluate_raw("VAG Torsion Value", [128])
    assert abs(torsion_zero - 0.0) < 1e-4

    # A = 138 -> +1.0 °KW
    torsion_plus = manager.evaluate_raw("VAG Torsion Value", [138])
    assert abs(torsion_plus - 1.0) < 1e-4

    # 2. KWP1281: N75 Valve Duty Cycle
    # Formuła: A / 2.55
    # A = 255 -> 100%
    n75_max = manager.evaluate_raw("VAG N75 Valve Duty Cycle", [255])
    assert abs(n75_max - 100.0) < 1e-2

    # 3. KWP1281: Knock Retard Cyl 1
    # Formuła: A * 0.75
    # A = 4 -> 3.0 °KW
    knock_val = manager.evaluate_raw("VAG Knock Retard Cyl 1", [4])
    assert abs(knock_val - 3.0) < 1e-4

    # 4. UDS: DPF Differential Pressure (Delta-P)
    # Formuła: (A*256 + B) * 0.1
    # A = 1, B = 44 (300) -> 30.0 hPa
    dpf_diff = manager.evaluate_raw("DPF Differential Pressure", [1, 44])
    assert abs(dpf_diff - 30.0) < 1e-4

    # 5. UDS: EGT Temp pre Turbo
    # Formuła: (A*256 + B) / 10 - 40
    # A = 25, B = 0 (6400) -> 640.0 - 40 = 600.0 °C
    egt_val = manager.evaluate_raw("EGT Temp pre Turbo", [25, 0])
    assert abs(egt_val - 600.0) < 1e-4

    # Wyszukiwanie VAG po short_name
    torsion_sensor = manager.get_by_short_name("VAG_TORSION")
    assert torsion_sensor is not None
    assert torsion_sensor.unit == "°KW"
    assert torsion_sensor.standard == "VAG_KWP1281"


def test_sensor_manager_filtering_and_categories():
    manager = SensorManager.with_full_database()

    # Filtrowanie po vendorze
    vag_list = manager.find_sensors(vendor="VAG")
    std_list = manager.find_sensors(vendor="Standard")
    assert len(vag_list) > 0
    assert len(std_list) > 0

    # Filtrowanie po kategorii
    turbo_list = manager.find_sensors(category="turbo")
    assert len(turbo_list) >= 4
    for s in turbo_list:
        assert s.category == "turbo"

    # Filtrowanie po standardzie
    kwp_list = manager.find_sensors(standard="VAG_KWP1281")
    assert len(kwp_list) >= 10

    # Listowanie dostępnych vendorów i kategorii
    vendors = manager.list_vendors()
    assert "Standard" in vendors
    assert "VAG" in vendors

    categories = manager.list_categories()
    assert "engine" in categories
    assert "turbo" in categories
    assert "fuel" in categories
    assert "exhaust" in categories
    assert "transmission" in categories
