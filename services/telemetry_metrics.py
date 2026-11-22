from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class MetricThresholds:
    name: str
    unit: str
    min_limit: float
    max_limit: float
    optimal_range: tuple[float, float]
    warning_low: Optional[float] = None
    warning_high: Optional[float] = None
    critical_low: Optional[float] = None
    critical_high: Optional[float] = None

    def evaluate(self, value: float) -> str:
        """Ocenia status wartości: 'optimal', 'warning', 'critical'."""
        val = float(value)

        # 1. Sprawdzenie progów krytycznych
        if self.critical_low is not None and val <= self.critical_low:
            return "critical"
        if self.critical_high is not None and val >= self.critical_high:
            return "critical"

        # 2. Sprawdzenie zakresu optymalnego
        opt_min, opt_max = self.optimal_range
        if opt_min <= val <= opt_max:
            return "optimal"

        # 3. Sprawdzenie progów ostrzegawczych
        if self.warning_low is not None and val <= self.warning_low:
            return "warning"
        if self.warning_high is not None and val >= self.warning_high:
            return "warning"

        # Wartości pomiędzy optymalnym a krytycznym/ostrzegawczym
        if val < opt_min:
            return "warning" if self.warning_low is not None else "optimal"
        if val > opt_max:
            return "warning" if self.warning_high is not None else "optimal"

        return "optimal"


STANDARD_METRIC_THRESHOLDS: dict[str, MetricThresholds] = {
    "coolant_temp": MetricThresholds(
        name="Temperatura cieczy chłodzącej",
        unit="°C",
        min_limit=-40.0,
        max_limit=140.0,
        optimal_range=(85.0, 98.0),
        warning_high=99.0,
        critical_high=115.0,
    ),
    "voltage": MetricThresholds(
        name="Napięcie instalacji / akumulatora",
        unit="V",
        min_limit=8.0,
        max_limit=18.0,
        optimal_range=(13.6, 14.6),
        warning_low=11.8,
        warning_high=14.8,
        critical_low=10.5,
        critical_high=15.5,
    ),
    "rpm": MetricThresholds(
        name="Prędkość obrotowa silnika",
        unit="RPM",
        min_limit=0.0,
        max_limit=8000.0,
        optimal_range=(750.0, 3200.0),
        warning_high=5500.0,
        critical_high=6500.0,
    ),
    "speed": MetricThresholds(
        name="Prędkość pojazdu",
        unit="km/h",
        min_limit=0.0,
        max_limit=260.0,
        optimal_range=(0.0, 140.0),
        warning_high=141.0,
        critical_high=200.0,
    ),
    "oil_temp": MetricThresholds(
        name="Temperatura oleju silnikowego",
        unit="°C",
        min_limit=-40.0,
        max_limit=160.0,
        optimal_range=(85.0, 105.0),
        warning_low=70.0,
        warning_high=115.0,
        critical_high=130.0,
    ),
    "boost_pressure": MetricThresholds(
        name="Ciśnienie doładowania",
        unit="bar",
        min_limit=0.0,
        max_limit=3.5,
        optimal_range=(0.0, 1.6),
        warning_high=1.8,
        critical_high=2.2,
    ),
}


def calculate_series_stats(samples: Sequence[float]) -> dict[str, float]:
    """Oblicza podstawowe statystyki serii próbkowania (średnia, min, max, bieżąca)."""
    if not samples:
        return {
            "count": 0,
            "avg": 0.0,
            "min": 0.0,
            "max": 0.0,
            "current": 0.0,
        }

    valid_samples = [float(s) for s in samples]
    return {
        "count": len(valid_samples),
        "avg": round(sum(valid_samples) / len(valid_samples), 1),
        "min": min(valid_samples),
        "max": max(valid_samples),
        "current": valid_samples[-1],
    }


def value_to_gauge_angle(
    value: float,
    min_val: float,
    max_val: float,
    start_angle: float = -135.0,
    sweep_angle: float = 270.0,
) -> float:
    """Konwertuje wartość fizyczną na kąt wskazówki tarczy zegarowej (domyślnie -135° do +135°)."""
    if max_val <= min_val:
        return start_angle

    clamped = max(min_val, min(float(value), max_val))
    ratio = (clamped - min_val) / (max_val - min_val)
    return round(start_angle + (ratio * sweep_angle), 1)


def evaluate_metric_status(param_name: str, value: float) -> str:
    """Zwraca status parametru ('optimal', 'warning', 'critical') lub 'undetermined' dla nieznanych PID."""
    thresholds = STANDARD_METRIC_THRESHOLDS.get(param_name)
    if not thresholds:
        return "undetermined"
    return thresholds.evaluate(value)
