from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)


class AgentAnalysisMode(str, Enum):
    """Tryby działania i analizy telemetrii przez asystenta AI."""

    LIVE = "live"  # Bieżąca analiza parametrów w czasie rzeczywistym podczas jazdy
    POST_TRIP_ECO = "post_trip_eco"  # Oszczędzanie baterii - analiza dopiero po zakończeniu jazdy
    ASK_USER = "ask_user"  # Zapytaj kierowcę przed jazdą


@dataclass
class UserPreferenceProfile:
    """Profil preferencji użytkownika w aplikacji OBD2-AI."""

    agent_analysis_mode: str = AgentAnalysisMode.ASK_USER.value
    battery_saver_enabled: bool = False
    harvest_interval_sec: float = 1.0
    auto_harvest_on_connect: bool = True
    remember_agent_mode_choice: bool = False
    voice_alerts_during_drive: bool = True
    preferred_model_id: str = "qwen3.5-9b-mtp"
    lm_studio_endpoint: str = "http://172.31.208.1:1234/v1"
    user_decision_history: list[dict[str, Any]] = None  # type: ignore

    def __post_init__(self) -> None:
        if self.user_decision_history is None:
            self.user_decision_history = []


class UserPreferencesManager:
    """Zarządza trwałym zapisem i odczytem preferencji użytkownika."""

    def __init__(self, config_path: Optional[str | Path] = None):
        if config_path:
            self.config_path = Path(config_path)
        else:
            self.config_path = Path.home() / ".config" / "obd2_ai" / "preferences.json"

        self.profile = UserPreferenceProfile()
        self.load()

    def load(self) -> UserPreferenceProfile:
        """Wczytuje preferencje z pliku konfiguracyjnego."""
        if not self.config_path.exists():
            return self.profile

        try:
            with open(self.config_path, encoding="utf-8") as f:
                data = json.load(f)
            self.profile = UserPreferenceProfile(
                agent_analysis_mode=data.get("agent_analysis_mode", AgentAnalysisMode.ASK_USER.value),
                battery_saver_enabled=bool(data.get("battery_saver_enabled", False)),
                harvest_interval_sec=float(data.get("harvest_interval_sec", 1.0)),
                auto_harvest_on_connect=bool(data.get("auto_harvest_on_connect", True)),
                remember_agent_mode_choice=bool(data.get("remember_agent_mode_choice", False)),
                voice_alerts_during_drive=bool(data.get("voice_alerts_during_drive", True)),
                preferred_model_id=str(data.get("preferred_model_id", "qwen3.5-9b-mtp")),
                lm_studio_endpoint=str(data.get("lm_studio_endpoint", "http://172.31.208.1:1234/v1")),
                user_decision_history=list(data.get("user_decision_history", [])),
            )
        except Exception as e:
            logger.warning("Nie udało się odczytać preferencji z %s: %s. Użyto domyślnych.", self.config_path, e)
        return self.profile

    def save(self) -> bool:
        """Zapisuje bieżący profil preferencji do pliku konfiguracyjnego."""
        try:
            self.config_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.config_path, "w", encoding="utf-8") as f:
                json.dump(asdict(self.profile), f, indent=2, ensure_ascii=False)
            return True
        except Exception as e:
            logger.error("Błąd zapisu preferencji do %s: %s", self.config_path, e)
            return False

    def set_agent_analysis_mode(self, mode: AgentAnalysisMode | str, remember: bool = False) -> None:
        """Aktualizuje tryb analizy agenta oraz opcjonalnie zapamiętuje wybór."""
        val = mode.value if isinstance(mode, AgentAnalysisMode) else str(mode)
        self.profile.agent_analysis_mode = val
        if remember:
            self.profile.remember_agent_mode_choice = True
        self.profile.user_decision_history.append(
            {
                "action": "set_agent_mode",
                "mode": val,
                "remembered": remember,
            }
        )
        self.save()

    def record_user_preference_choice(self, decision_type: str, details: dict[str, Any]) -> None:
        """Rejestruje wybór użytkownika w celu adaptacji asystenta."""
        self.profile.user_decision_history.append(
            {
                "type": decision_type,
                "details": details,
            }
        )
        self.save()
