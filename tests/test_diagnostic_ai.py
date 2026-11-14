from __future__ import annotations

import pytest

from services.ai_engine import AIEngine
from services.diagnostic_ai import (
    DiagnosisReport,
    DiagnosticAI,
    DTCFinding,
    LocalDiagnosticAI,
    RuleBasedDiagnosticAI,
)


def test_rule_based_known_dtc():
    engine = RuleBasedDiagnosticAI()
    report = engine.analyze({"dtc_codes": ["P0300"], "rpm": 1200})
    assert isinstance(report, DiagnosisReport)
    assert len(report.dtc_findings) == 1
    assert report.dtc_findings[0].code == "P0300"
    assert "Wielokrotne" in report.dtc_findings[0].title
    assert report.overall_urgency == "warning"
    assert report.safe_to_drive is True


def test_rule_based_single_code_backward_compat():
    engine = RuleBasedDiagnosticAI()
    report = engine.analyze({"dtc_code": "P0171"})
    assert len(report.dtc_findings) == 1
    assert report.dtc_findings[0].code == "P0171"
    assert report.overall_urgency == "warning"


def test_rule_based_unknown_dtc_fallback():
    engine = RuleBasedDiagnosticAI()
    report = engine.analyze({"dtc_codes": ["P9999", "U0100"]})
    assert len(report.dtc_findings) == 2
    assert report.dtc_findings[0].code == "P9999"
    assert "Układ napędowy" in report.dtc_findings[0].description
    assert "Sterownik pojazdu" in report.dtc_findings[1].description
    assert report.overall_urgency == "info"


def test_telemetry_triage_critical_coolant():
    engine = RuleBasedDiagnosticAI()
    report = engine.analyze({"dtc_codes": ["P0115"], "coolant_temp_c": 118})
    assert report.safe_to_drive is False
    assert report.overall_urgency == "critical"
    assert any("przekracza próg bezpieczeństwa" in w for w in report.safety_warnings)
    assert any("Zatrzymaj pojazd" in step for step in report.next_steps)


def test_telemetry_triage_warning_coolant():
    engine = RuleBasedDiagnosticAI()
    report = engine.analyze({"coolant_c": 107})
    assert report.safe_to_drive is True
    assert report.overall_urgency == "warning"
    assert any("Podwyższona temperatura cieczy" in w for w in report.safety_warnings)


def test_telemetry_triage_critical_oil_temp():
    engine = RuleBasedDiagnosticAI()
    report = engine.analyze({"oil_temp_c": 135})
    assert report.safe_to_drive is False
    assert report.overall_urgency == "critical"
    assert any("zerwaniem filmu olejowego" in w for w in report.safety_warnings)


def test_telemetry_triage_misfire_high_rpm():
    engine = RuleBasedDiagnosticAI()
    report = engine.analyze({"dtc_codes": ["P0302"], "rpm": 3200})
    assert report.safe_to_drive is False
    assert report.overall_urgency == "critical"
    assert any("zniszczeniem katalizatora" in w for w in report.safety_warnings)


def test_telemetry_triage_battery_voltage():
    engine = RuleBasedDiagnosticAI()
    # Warning voltage
    warn_report = engine.analyze({"battery_voltage": 11.2})
    assert warn_report.overall_urgency == "warning"
    assert warn_report.safe_to_drive is True
    assert any("Niskie napięcie" in w for w in warn_report.safety_warnings)

    # Critical voltage
    crit_report = engine.analyze({"voltage": 10.1})
    assert crit_report.overall_urgency == "critical"
    assert crit_report.safe_to_drive is False
    assert any("krytycznie niskie" in w for w in crit_report.safety_warnings)


def test_critical_dtc_p0600():
    engine = RuleBasedDiagnosticAI()
    report = engine.analyze({"dtc_codes": ["P0600"]})
    assert report.overall_urgency == "critical"
    assert report.safe_to_drive is False


def test_no_dtc_normal():
    engine = RuleBasedDiagnosticAI()
    report = engine.analyze({})
    assert report.dtc_findings == []
    assert report.overall_urgency == "info"
    assert report.safe_to_drive is True
    assert "Brak aktywnych błędów DTC" in report.summary


def test_no_dtc_critical_telemetry():
    engine = RuleBasedDiagnosticAI()
    report = engine.analyze({"coolant_temp_c": 125})
    assert report.overall_urgency == "critical"
    assert report.safe_to_drive is False
    assert "parametry telemetryczne wskazują stan krytyczny" in report.summary


def test_custom_dtc_database():
    custom_db = {
        "P0001": {
            "title": "Regulator objętości paliwa",
            "description": "Obwód sterowania otwarty",
            "urgency": "warning",
            "causes": ["Przerwany przewód"],
            "actions": ["Sprawdź oporność zaworu"],
        }
    }
    engine = RuleBasedDiagnosticAI(dtc_database=custom_db)
    report = engine.analyze({"dtc_codes": ["P0001"]})
    assert report.dtc_findings[0].title == "Regulator objętości paliwa"


def test_local_ai_fallback():
    local_ai = LocalDiagnosticAI()
    report = local_ai.analyze({"dtc_codes": ["P0420"]})
    assert report.overall_urgency == "info"
    assert report.safe_to_drive is True


def test_local_ai_runner_success():
    def mock_runner(_prompt: str) -> str:
        return "Zalecana wymiana sondy lambda po teście emisji spalin."

    local_ai = LocalDiagnosticAI(model_runner=mock_runner)
    report = local_ai.analyze({"dtc_codes": ["P0420"]})
    assert "[Lokalny Asystent AI]" in report.summary
    assert report.metadata.get("llm_processed") is True


def test_local_ai_runner_exception():
    def broken_runner(_prompt: str) -> str:
        raise RuntimeError("Inference timeout")

    local_ai = LocalDiagnosticAI(model_runner=broken_runner)
    report = local_ai.analyze({"dtc_codes": ["P0420"]})
    assert report.metadata.get("llm_error") is True
    assert report.overall_urgency == "info"


def test_ai_engine_integration():
    engine = AIEngine()
    report = engine.analyze_context({"dtc_codes": ["P0300"], "rpm": 1000})
    assert isinstance(report, DiagnosisReport)
    assert report.dtc_findings[0].code == "P0300"


def test_abstract_diagnostic_ai():
    class DummyAI(DiagnosticAI):
        def analyze(self, vehicle_context):
            return super().analyze(vehicle_context)

    with pytest.raises(NotImplementedError):
        DummyAI().analyze({})

