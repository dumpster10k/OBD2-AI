from services.ai_engine import AIEngine, Diagnosis


def test_analyze_error():
    result = AIEngine().analyze_error("P0300", {"rpm": 2000})
    assert isinstance(result, Diagnosis)
    assert result.urgency == "warning"


def test_sensor_suggestion():
    result = AIEngine().suggest_sensor_formula("engine oil temperature")
    assert result["pid"] == "221126"
