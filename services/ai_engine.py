from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from services.diagnostic_ai import DiagnosisReport, DiagnosticAI, RuleBasedDiagnosticAI
from services.llm_engine import LocalLLMEngine
from services.speech_service import VoiceDiagnosticAssistant


@dataclass
class Diagnosis:
    code: str
    summary: str
    urgency: str
    next_steps: list[str]


class AIEngine:
    def __init__(
        self,
        diagnostic_ai: Optional[DiagnosticAI] = None,
        llm_engine: Optional[LocalLLMEngine] = None,
        voice_assistant: Optional[VoiceDiagnosticAssistant] = None,
    ):
        self.diagnostic_ai = diagnostic_ai or RuleBasedDiagnosticAI()
        self.llm = llm_engine or LocalLLMEngine()
        self.voice = voice_assistant or VoiceDiagnosticAssistant(
            diagnostic_ai=self.diagnostic_ai,
            llm_engine=self.llm,
        )

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

    def ask_llm(self, query: str, vehicle_context: Optional[dict[str, Any]] = None) -> str:
        """Kieruje zapytanie do lokalnego modelu LLM z uwzględnieniem kontekstu pojazdu."""
        return self.llm.ask(query, vehicle_context=vehicle_context)

    def handle_voice_command(
        self,
        audio_data: bytes,
        vehicle_context: Optional[dict[str, Any]] = None,
    ) -> tuple[str, str, bytes]:
        """Przetwarza komendę głosową kierowcy (STT -> Analiza -> TTS)."""
        return self.voice.handle_voice_query(audio_data, vehicle_context=vehicle_context)

    def suggest_sensor_formula(self, sensor_description: str):
        if "oil" in sensor_description.lower():
            return {"pid": "221126", "formula": "(A*256 + B)/10", "unit": "°C"}
        return None
