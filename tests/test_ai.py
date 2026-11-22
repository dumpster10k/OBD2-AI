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


def test_ai_engine_analyze_context():
    engine = AIEngine()
    report = engine.analyze_context({"dtc_codes": ["P0300"], "coolant_temp": 90})
    assert report.overall_urgency in ["warning", "critical", "info"]


def test_ai_engine_ask_llm():
    engine = AIEngine()
    response = engine.ask_llm("Co oznacza wypadanie zapłonu?")
    assert "pomocniczy" in response or "Uwaga" in response


def test_ai_engine_handle_voice_command():
    engine = AIEngine()
    query, response, audio = engine.handle_voice_command(b"test_audio_bytes")
    assert len(response) > 0
    assert len(audio) > 0
