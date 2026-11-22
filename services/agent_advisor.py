from __future__ import annotations

import logging
from typing import Any, Optional

from services.llm_engine import DISCLAIMER_TEXT, LocalLLMEngine
from services.user_preferences import AgentAnalysisMode, UserPreferencesManager

logger = logging.getLogger(__name__)


class AgentAdvisor:
    """Doradca i asystent jazdy OBD-II realizujący elastyczne strategie analizy telemetrii."""

    def __init__(
        self,
        llm_engine: Optional[LocalLLMEngine] = None,
        preferences_manager: Optional[UserPreferencesManager] = None,
    ):
        self.llm = llm_engine or LocalLLMEngine()
        self.prefs_mgr = preferences_manager or UserPreferencesManager()
        self.last_alert_time: float = 0.0
        self.cooldown_sec: float = 15.0  # Nie zalewaj kierowcy komunikatami co sekundę
        self.buffered_samples: list[dict[str, Any]] = []

    @property
    def mode(self) -> AgentAnalysisMode:
        mode_str = self.prefs_mgr.profile.agent_analysis_mode
        try:
            return AgentAnalysisMode(mode_str)
        except Exception:
            return AgentAnalysisMode.ASK_USER

    def set_mode(self, mode: AgentAnalysisMode | str, remember: bool = False) -> None:
        self.prefs_mgr.set_agent_analysis_mode(mode, remember=remember)

    def should_ask_user(self) -> bool:
        """Sprawdza, czy należy zapytać kierowcę o preferowany tryb analizy."""
        if self.prefs_mgr.profile.remember_agent_mode_choice:
            return False
        return self.mode == AgentAnalysisMode.ASK_USER

    def get_mode_choice_prompt(self) -> dict[str, Any]:
        """Zwraca treść zapytania dla interfejsu użytkownika."""
        return {
            "title": "Wybór trybu pracy asystenta AI",
            "message": (
                "Czy asystent ma analizować parametry na bieżąco podczas jazdy (ostrzeżenia na żywo), "
                "czy wolisz tryb EKO (maksymalna oszczędność baterii, pełny raport po zgaszeniu silnika)?"
            ),
            "options": [
                {"id": AgentAnalysisMode.LIVE.value, "label": "🔴 Na żywo (Live Telemetry Alerts)"},
                {
                    "id": AgentAnalysisMode.POST_TRIP_ECO.value,
                    "label": "🔋 EKO (Oszczędzanie baterii + raport po jeździe)",
                },
            ],
            "can_remember": True,
        }

    def process_sample(self, sample: dict[str, Any], current_time: float) -> Optional[str]:
        """Przetwarza próbkę telemetrii zgodnie z aktualnym trybem pracy."""
        self.buffered_samples.append(sample)
        if len(self.buffered_samples) > 2000:
            self.buffered_samples = self.buffered_samples[-2000:]

        # Jeśli tryb EKO lub brak decyzji - nie obciążaj procesora ani baterii podczas jazdy
        if self.mode != AgentAnalysisMode.LIVE:
            return None

        # Tryb LIVE: sprawdzamy krytyczne anomalie z zachowaniem cooldownu
        if current_time - self.last_alert_time < self.cooldown_sec:
            return None

        alert = self._detect_live_anomaly(sample)
        if alert:
            self.last_alert_time = current_time
            return alert
        return None

    def _detect_live_anomaly(self, sample: dict[str, Any]) -> Optional[str]:
        """Sprawdza regułowo najgroźniejsze anomalie w czasie rzeczywistym."""
        coolant = float(sample.get("coolant_temp", 0.0))
        rpm = float(sample.get("rpm", 0.0))
        volt = float(sample.get("voltage", 0.0))

        if coolant >= 115:
            return f"Uwaga! Bardzo wysoka temperatura płynu chłodzącego: {int(coolant)}°C! Sprawdź poziom płynu i nie przeciążaj silnika."
        if coolant >= 106:
            return f"Ostrzeżenie: Podwyższona temperatura silnika: {int(coolant)}°C."

        if rpm > 0 and 0 < volt < 12.0:
            return f"Ostrzeżenie: Niskie napięcie instalacji podczas pracy silnika ({volt:.1f} V). Możliwa awaria ładowania alternatora."

        if coolant < 60 and rpm > 4500:
            return f"Wskazówka: Silnik jest jeszcze zimny ({int(coolant)}°C). Zaleca się unikanie wysokich obrotów powyżej 4000 RPM."

        return None

    def generate_post_trip_report(
        self,
        samples: Optional[list[dict[str, Any]]] = None,
        notes: str = "",
    ) -> str:
        """Generuje kompleksowe podsumowanie zakończonej jazdy (tryb EKO / po jeździe)."""
        data = samples if samples is not None else self.buffered_samples
        if not data:
            return f"Brak zarejestrowanych próbek telemetrii dla tej sesji. {DISCLAIMER_TEXT}"

        rpms = [float(s.get("rpm", 0.0)) for s in data if float(s.get("rpm", 0.0)) > 0]
        speeds = [float(s.get("speed", 0.0)) for s in data]
        coolants = [float(s.get("coolant_temp", 0.0)) for s in data if float(s.get("coolant_temp", 0.0)) > 0]
        volts = [float(s.get("voltage", 0.0)) for s in data if float(s.get("voltage", 0.0)) > 0]

        max_speed = max(speeds) if speeds else 0.0
        avg_speed = sum(speeds) / len(speeds) if speeds else 0.0
        max_rpm = max(rpms) if rpms else 0.0
        avg_rpm = sum(rpms) / len(rpms) if rpms else 0.0
        max_coolant = max(coolants) if coolants else 0.0
        min_volt = min(volts) if volts else 0.0
        max_volt = max(volts) if volts else 0.0

        # Wnioski i ocena termiki / zasilania
        observations: list[str] = []
        if max_coolant >= 105:
            observations.append(f"Zarejestrowano epizod wysokiej temperatury cieczy chłodzącej: {int(max_coolant)}°C.")
        elif max_coolant >= 85:
            observations.append(f"Układ chłodzenia utrzymał optymalną temperaturę roboczą (max {int(max_coolant)}°C).")
        else:
            observations.append(f"Silnik pracował poniżej pełnej temperatury roboczej (max {int(max_coolant)}°C).")

        if min_volt > 0 and min_volt < 12.2:
            observations.append(f"Odnotowano spadek napięcia akumulatora do {min_volt:.2f} V.")
        elif max_volt >= 13.6:
            observations.append(f"Układ ładowania sprawny (napięcie robocze {max_volt:.2f} V).")

        query = (
            f"Oto podsumowanie trasy (próbek: {len(data)}):\n"
            f"- Prędkość: max {int(max_speed)} km/h, średnia {int(avg_speed)} km/h\n"
            f"- Obroty: max {int(max_rpm)} RPM, średnia {int(avg_rpm)} RPM\n"
            f"- Temperatura cieczy: max {int(max_coolant)}°C\n"
            f"- Napięcie instalacji: {min_volt:.2f} V - {max_volt:.2f} V\n"
            f"Wnioski: {'; '.join(observations)}\n"
            f"Przygotuj zwięzłą ocenę stanu pojazdu i stylu jazdy po tej trasie."
        )

        try:
            explanation = self.llm.ask(query)
            return (
                f"📊 **PODSUMOWANIE ZAKOŃCZONEJ TRASY (TRYB EKO)**\n\n"
                f"• Czas/Liczba próbek: {len(data)}\n"
                f"• Prędkość maksymalna: {int(max_speed)} km/h (średnia: {int(avg_speed)} km/h)\n"
                f"• Obroty maksymalne: {int(max_rpm)} RPM (średnia: {int(avg_rpm)} RPM)\n"
                f"• Maksymalna temperatura płynu: {int(max_coolant)}°C\n"
                f"• Zakres napięcia: {min_volt:.2f} V – {max_volt:.2f} V\n\n"
                f"**Ocena asystenta AI:**\n{explanation}"
            )
        except Exception as e:
            logger.warning("Błąd generowania podsumowania przez LLM: %s", e)
            return (
                f"📊 **PODSUMOWANIE TRASY (RAPORT STANDARDOWY)**\n\n"
                f"• Liczba zebranych próbek: {len(data)}\n"
                f"• Prędkość: max {int(max_speed)} km/h, średnia {int(avg_speed)} km/h\n"
                f"• Obroty: max {int(max_rpm)} RPM, średnia {int(avg_rpm)} RPM\n"
                f"• Temperatura maksymalna: {int(max_coolant)}°C\n"
                f"• Napięcie: {min_volt:.2f} V – {max_volt:.2f} V\n"
                f"• Obserwacje: {'; '.join(observations)}\n\n"
                f"{DISCLAIMER_TEXT}"
            )
