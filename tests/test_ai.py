from services.ai_engine import AIEngine, Diagnosis


def test_analyze_error():
    result = AIEngine().analyze_error("P0300", {"rpm": 2000})
    assert isinstance(result, Diagnosis)
    assert result.urgency == "warning"


def test_analyze_unknown_error():
    result = AIEngine().analyze_error("P0420", {})
    assert result.urgency == "info"


def test_sensor_suggestion():
    result = AIEngine().suggest_sensor_formula("engine oil temperature")
    assert result["pid"] == "221126"


def test_unknown_sensor_suggestion():
    assert AIEngine().suggest_sensor_formula("brake pressure") is None
