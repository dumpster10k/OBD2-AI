from pathlib import Path

import pytest

from services.diagnostic_ai import LocalDiagnosticAI
from services.llm_engine import (
    DISCLAIMER_TEXT,
    LlamaCppBackend,
    LLMModelSpec,
    LocalLLMEngine,
    MockLLMBackend,
)


def test_recommended_models_specs():
    models = LocalLLMEngine.list_available_models()
    assert len(models) >= 3
    for model in models:
        assert isinstance(model, LLMModelSpec)
        assert model.size_mb > 0
        assert model.ram_required_mb > 0
        assert model.format in ["gguf", "onnx"]
        assert model.quantization.startswith("Q")
        assert model.context_window >= 2048


def test_mock_llm_backend_default_responses():
    backend = MockLLMBackend()
    assert backend.is_available() is True

    # P0300 prompt
    resp_p0300 = backend.generate("Błąd P0300 wypadanie zapłonu")
    assert "świec" in resp_p0300.lower()
    assert DISCLAIMER_TEXT in resp_p0300

    # P0171 prompt
    resp_p0171 = backend.generate("Mieszanka zbyt uboga P0171")
    assert "przepływomierz" in resp_p0171.lower()

    # Safe to drive prompt
    resp_drive = backend.generate("Czy bezpiecznie mogę jechać?")
    assert "Check Engine" in resp_drive

    # General prompt
    resp_general = backend.generate("Jakie jest prawidłowe ciśnienie?")
    assert DISCLAIMER_TEXT in resp_general


def test_mock_llm_backend_custom_generator():
    backend = MockLLMBackend(response_generator=lambda p: "Niestandardowa diagnoza testowa")
    assert backend.generate("dowolne zapytanie") == "Niestandardowa diagnoza testowa"


def test_local_llm_engine_prompt_formatting():
    engine = LocalLLMEngine()
    prompt = engine.format_diagnostic_prompt(
        query="Co oznacza ten błąd?",
        vehicle_context={"dtc_codes": ["P0300"], "rpm": 2500, "coolant_temp": 95, "speed": 80},
    )
    assert "<|im_start|>system" in prompt
    assert "P0300" in prompt
    assert "RPM=2500" in prompt
    assert "<|im_start|>user\nCo oznacza ten błąd?<|im_end|>" in prompt


def test_local_llm_engine_ask():
    engine = LocalLLMEngine()
    response = engine.ask("P0300 wypadanie zapłonu", vehicle_context={"dtc_codes": ["P0300"]})
    assert DISCLAIMER_TEXT in response


def test_local_llm_engine_explain_finding():
    engine = LocalLLMEngine()
    explanation = engine.explain_finding(
        dtc_code="P0300",
        title="Wypadanie zapłonów",
        description="Wielokrotne wypadanie zapłonów",
    )
    assert "P0300" in explanation
    assert DISCLAIMER_TEXT in explanation


def test_local_llm_engine_backend_failure_handling():
    class BrokenBackend(MockLLMBackend):
        def generate(self, prompt: str, max_tokens: int = 200, temperature: float = 0.2) -> str:
            raise RuntimeError("Błąd symulowany silnika")

    engine = LocalLLMEngine(backend=BrokenBackend())
    response = engine.ask("Jakiekolwiek pytanie")
    assert "Nie udało się uzyskać odpowiedzi" in response
    assert DISCLAIMER_TEXT in response


def test_llama_cpp_backend_missing_file(tmp_path: Path):
    non_existent = tmp_path / "model.gguf"
    backend = LlamaCppBackend(model_path=non_existent)
    assert backend.is_available() is False

    with pytest.raises(RuntimeError, match="Plik modelu nie istnieje"):
        backend.generate("Test prompt")


def test_local_diagnostic_ai_with_llm_engine():
    engine = LocalLLMEngine()
    local_ai = LocalDiagnosticAI(llm_engine=engine)
    report = local_ai.analyze({"dtc_codes": ["P0300"], "coolant_temp": 90})
    assert report.metadata.get("llm_processed") is True
    assert "[Lokalny Asystent AI]" in report.summary
