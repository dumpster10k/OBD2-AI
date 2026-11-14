from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from services.diagnostic_ai import DiagnosisReport, RuleBasedDiagnosticAI


@dataclass
class Diagnosis:
    code: str
    summary: str
    urgency: str
    next_steps: list[str]


class AIEngine:
    def __init__(self, diagnostic_ai: Optional[RuleBasedDiagnosticAI] = None):
        self.diagnostic_ai = diagnostic_ai or RuleBasedDiagnosticAI()

    def analyze_error(self, dtc_code: str, telemetry_data: dict[str, Any]) -> Diagnosis:
        if dtc_code == "P0300" and telemetry_data.get("rpm", 0) > 1500:
            return Diagnosis(
                dtc_code,
                "Możliwe wypadanie zapłonu przy wyższych obrotach.",
                "warning",
                ["Sprawdź świece", "Sprawdź cewki"],
            )
        return Diagnosis(
            dtc_code,
            "Kod wymaga dalszej diagnostyki.",
            "info",
            ["Zapisz freeze-frame", "Sprawdź dokumentację pojazdu"],
        )

    def analyze_context(self, vehicle_context: dict[str, Any]) -> DiagnosisReport:
        return self.diagnostic_ai.analyze(vehicle_context)

    def suggest_sensor_formula(self, sensor_description: str):
        if "oil" in sensor_description.lower():
            return {"pid": "221126", "formula": "(A*256 + B)/10", "unit": "°C"}
        return None
