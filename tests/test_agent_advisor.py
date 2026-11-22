from __future__ import annotations

from pathlib import Path

from services.agent_advisor import AgentAdvisor
from services.llm_engine import LocalLLMEngine, MockLLMBackend
from services.user_preferences import AgentAnalysisMode, UserPreferencesManager


def test_agent_advisor_modes(tmp_path: Path) -> None:
    prefs = UserPreferencesManager(config_path=tmp_path / "prefs.json")
    advisor = AgentAdvisor(preferences_manager=prefs)

    assert advisor.should_ask_user() is True
    prompt = advisor.get_mode_choice_prompt()
    assert "Wybór trybu" in prompt["title"]

    advisor.set_mode(AgentAnalysisMode.LIVE, remember=True)
    assert advisor.mode == AgentAnalysisMode.LIVE
    assert advisor.should_ask_user() is False


def test_agent_advisor_live_anomalies(tmp_path: Path) -> None:
    prefs = UserPreferencesManager(config_path=tmp_path / "prefs.json")
    advisor = AgentAdvisor(preferences_manager=prefs)
    advisor.set_mode(AgentAnalysisMode.LIVE)

    # 1. Normalna próbka - brak alertu
    sample_normal = {"rpm": 1500, "speed": 50, "coolant_temp": 90, "voltage": 14.2}
    alert = advisor.process_sample(sample_normal, current_time=100.0)
    assert alert is None

    # 2. Przegrzanie silnika (> 106°C)
    sample_overheat = {"rpm": 2000, "speed": 60, "coolant_temp": 118, "voltage": 13.8}
    alert = advisor.process_sample(sample_overheat, current_time=110.0)
    assert alert is not None
    assert "Bardzo wysoka temperatura" in alert

    # 3. Cooldown zapobiega powtórzeniu natychmiast
    alert_cd = advisor.process_sample(sample_overheat, current_time=112.0)
    assert alert_cd is None

    # 4. Awaria ładowania alternatora (< 12.0V przy RPM > 0) po upływie cooldownu
    sample_alt = {"rpm": 1800, "speed": 40, "coolant_temp": 90, "voltage": 11.5}
    alert_alt = advisor.process_sample(sample_alt, current_time=130.0)
    assert alert_alt is not None
    assert "Niskie napięcie" in alert_alt

    # 5. Piłowanie zimnego silnika (> 4500 RPM przy < 60°C)
    sample_cold_rev = {"rpm": 5000, "speed": 70, "coolant_temp": 45, "voltage": 14.1}
    alert_cold = advisor.process_sample(sample_cold_rev, current_time=150.0)
    assert alert_cold is not None
    assert "zimny" in alert_cold


def test_agent_advisor_eco_mode_ignores_live(tmp_path: Path) -> None:
    prefs = UserPreferencesManager(config_path=tmp_path / "prefs.json")
    advisor = AgentAdvisor(preferences_manager=prefs)
    advisor.set_mode(AgentAnalysisMode.POST_TRIP_ECO)

    # Nawet krytyczna próbka nie generuje alertu na żywo w trybie EKO
    sample_crit = {"rpm": 6000, "speed": 100, "coolant_temp": 120, "voltage": 10.0}
    alert = advisor.process_sample(sample_crit, current_time=100.0)
    assert alert is None


def test_agent_advisor_post_trip_report(tmp_path: Path) -> None:
    prefs = UserPreferencesManager(config_path=tmp_path / "prefs.json")
    llm = LocalLLMEngine(backend=MockLLMBackend())
    advisor = AgentAdvisor(llm_engine=llm, preferences_manager=prefs)

    # Puste próbki
    rep_empty = advisor.generate_post_trip_report(samples=[])
    assert "Brak zarejestrowanych próbek" in rep_empty

    samples = [
        {"rpm": 850, "speed": 0, "coolant_temp": 70, "voltage": 14.0},
        {"rpm": 2200, "speed": 60, "coolant_temp": 88, "voltage": 14.2},
        {"rpm": 2800, "speed": 110, "coolant_temp": 92, "voltage": 14.1},
    ]
    report = advisor.generate_post_trip_report(samples=samples)
    assert "PODSUMOWANIE" in report
    assert "110 km/h" in report
    assert "2800 RPM" in report
    assert "92°C" in report
