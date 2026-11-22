from __future__ import annotations

from pathlib import Path

from services.user_preferences import (
    AgentAnalysisMode,
    UserPreferencesManager,
)


def test_user_preferences_default(tmp_path: Path) -> None:
    cfg = tmp_path / "prefs.json"
    mgr = UserPreferencesManager(config_path=cfg)

    assert mgr.profile.agent_analysis_mode == AgentAnalysisMode.ASK_USER.value
    assert mgr.profile.battery_saver_enabled is False
    assert mgr.profile.preferred_model_id == "qwen3.5-9b-mtp"


def test_user_preferences_save_and_load(tmp_path: Path) -> None:
    cfg = tmp_path / "subdir" / "prefs.json"
    mgr = UserPreferencesManager(config_path=cfg)

    mgr.set_agent_analysis_mode(AgentAnalysisMode.POST_TRIP_ECO, remember=True)
    mgr.record_user_preference_choice("test_action", {"val": 123})

    assert cfg.exists()

    mgr2 = UserPreferencesManager(config_path=cfg)
    assert mgr2.profile.agent_analysis_mode == AgentAnalysisMode.POST_TRIP_ECO.value
    assert mgr2.profile.remember_agent_mode_choice is True
    assert len(mgr2.profile.user_decision_history) == 2


def test_user_preferences_corrupted_file(tmp_path: Path) -> None:
    cfg = tmp_path / "corrupt.json"
    cfg.write_text("{broken json", encoding="utf-8")

    mgr = UserPreferencesManager(config_path=cfg)
    assert mgr.profile.agent_analysis_mode == AgentAnalysisMode.ASK_USER.value
