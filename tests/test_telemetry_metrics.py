from __future__ import annotations

from services.telemetry_metrics import (
    STANDARD_METRIC_THRESHOLDS,
    calculate_series_stats,
    evaluate_metric_status,
    value_to_gauge_angle,
)


def test_metric_thresholds_evaluation():
    coolant = STANDARD_METRIC_THRESHOLDS["coolant_temp"]

    # Optymalna (85-98)
    assert coolant.evaluate(90) == "optimal"
    assert coolant.evaluate(85) == "optimal"
    assert coolant.evaluate(98) == "optimal"

    # Ostrzegawcza podwyższona (99-114)
    assert coolant.evaluate(108) == "warning"

    # Krytyczna (>= 115)
    assert coolant.evaluate(116) == "critical"
    assert coolant.evaluate(125) == "critical"


def test_voltage_thresholds_evaluation():
    volt = STANDARD_METRIC_THRESHOLDS["voltage"]

    # Prawidłowe ładowanie (13.6 - 14.6)
    assert volt.evaluate(14.2) == "optimal"

    # Niskie napięcie (ostrzeżenie)
    assert volt.evaluate(11.5) == "warning"

    # Krytycznie niskie (< 10.5)
    assert volt.evaluate(10.2) == "critical"

    # Krytycznie wysokie (przeładowanie > 15.5)
    assert volt.evaluate(15.8) == "critical"


def test_oil_temp_and_rpm_thresholds():
    oil = STANDARD_METRIC_THRESHOLDS["oil_temp"]
    assert oil.evaluate(95) == "optimal"
    assert oil.evaluate(120) == "warning"
    assert oil.evaluate(135) == "critical"

    rpm = STANDARD_METRIC_THRESHOLDS["rpm"]
    assert rpm.evaluate(850) == "optimal"
    assert rpm.evaluate(2200) == "optimal"
    assert rpm.evaluate(5800) == "warning"
    assert rpm.evaluate(6800) == "critical"


def test_calculate_series_stats():
    # Pusta lista próbek
    empty_stats = calculate_series_stats([])
    assert empty_stats["count"] == 0
    assert empty_stats["avg"] == 0.0

    # Próbki z wartościami
    samples = [80.0, 90.0, 100.0]
    stats = calculate_series_stats(samples)
    assert stats["count"] == 3
    assert stats["avg"] == 90.0
    assert stats["min"] == 80.0
    assert stats["max"] == 100.0
    assert stats["current"] == 100.0


def test_value_to_gauge_angle():
    # 0% wartości -> kąt początkowy -135
    assert value_to_gauge_angle(0, min_val=0, max_val=100) == -135.0

    # 100% wartości -> kąt końcowy 135
    assert value_to_gauge_angle(100, min_val=0, max_val=100) == 135.0

    # 50% wartości -> kąt środkowy 0
    assert value_to_gauge_angle(50, min_val=0, max_val=100) == 0.0

    # Ograniczenie wartości poza zakresem (clamping)
    assert value_to_gauge_angle(-20, min_val=0, max_val=100) == -135.0
    assert value_to_gauge_angle(150, min_val=0, max_val=100) == 135.0


def test_evaluate_metric_status_helper():
    assert evaluate_metric_status("coolant_temp", 92) == "optimal"
    assert evaluate_metric_status("coolant_temp", 118) == "critical"
    # Nieznany parametr zwraca 'undetermined'
    assert evaluate_metric_status("unknown_pid", 50) == "undetermined"
