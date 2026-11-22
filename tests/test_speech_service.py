from pathlib import Path
import pytest

from services.diagnostic_ai import RuleBasedDiagnosticAI
from services.llm_engine import LocalLLMEngine
from services.speech_service import (
    MockSTTBackend,
    MockTTSBackend,
    PiperTTSBackend,
    SpeechModelSpec,
    SpeechService,
    VoiceDiagnosticAssistant,
    WhisperONNXBackend,
)


def test_speech_models_specs():
    models = SpeechService.list_models()
    assert len(models) >= 4
    for model in models:
        assert isinstance(model, SpeechModelSpec)
        assert model.size_mb > 0
        assert model.ram_required_mb > 0
        assert model.type in ["stt", "tts"]
        assert model.format in ["onnx", "bin", "gguf"]


def test_speech_service_basic():
    service = SpeechService()
    assert service.speech_to_text(b"fake_audio") == "Czy mogę bezpiecznie jechać dalej?"
    assert service.speech_to_text(b"") == ""

    audio_out = service.text_to_speech("Przykładowy komunikat głosowy")
    assert len(audio_out) > 44  # poprawny nagłówek WAV
    assert service.text_to_speech("") == b""


def test_voice_assistant_empty_audio():
    assistant = VoiceDiagnosticAssistant()
    query, response, audio = assistant.handle_voice_query(b"")
    assert query == ""
    assert "Nie usłyszałem" in response
    assert len(audio) > 0


def test_voice_assistant_rejects_clearing_dtc_by_voice():
    assistant = VoiceDiagnosticAssistant(
        speech_service=SpeechService(stt_backend=MockSTTBackend("Skasuj błędy silnika"))
    )
    query, response, audio = assistant.handle_voice_query(b"voice_bytes")
    assert "Skasuj" in query
    assert "nie może być wykonane głosem" in response
    assert "manualne potwierdzenie" in response


def test_voice_assistant_safe_to_drive():
    assistant = VoiceDiagnosticAssistant(
        speech_service=SpeechService(stt_backend=MockSTTBackend("Czy mogę jechać dalej?"))
    )

    # Scenariusz bezpieczny
    _, resp_safe, _ = assistant.handle_voice_query(b"voice_bytes", vehicle_context={"dtc_codes": []})
    assert "Możesz kontynuować" in resp_safe

    # Scenariusz niebezpieczny (krytyczny)
    _, resp_unsafe, _ = assistant.handle_voice_query(
        b"voice_bytes",
        vehicle_context={"dtc_codes": ["P0300"], "coolant_temp": 125},
    )
    assert "Nie zalecam" in resp_unsafe or "Uwaga!" in resp_unsafe


def test_voice_assistant_dtc_status():
    assistant = VoiceDiagnosticAssistant(
        speech_service=SpeechService(stt_backend=MockSTTBackend("Jakie mam błędy?"))
    )
    _, response, _ = assistant.handle_voice_query(
        b"voice_bytes",
        vehicle_context={"dtc_codes": ["P0171"]},
    )
    assert "Raport diagnostyczny" in response
    assert "P0171" in response


def test_voice_assistant_general_llm_query():
    assistant = VoiceDiagnosticAssistant(
        speech_service=SpeechService(stt_backend=MockSTTBackend("Co oznacza kontrolka świec?"))
    )
    _, response, _ = assistant.handle_voice_query(b"voice_bytes")
    assert "pomocniczy" in response or "Uwaga" in response


def test_whisper_onnx_backend(tmp_path: Path):
    non_existent = tmp_path / "whisper.onnx"
    backend = WhisperONNXBackend(non_existent)
    assert backend.is_available() is False

    with pytest.raises(RuntimeError, match="Plik modelu STT nie istnieje"):
        backend.transcribe(b"dummy")

    # Gdy plik istnieje
    non_existent.touch()
    assert backend.is_available() is True
    assert "Whisper ONNX" in backend.transcribe(b"dummy")


def test_piper_tts_backend(tmp_path: Path):
    non_existent = tmp_path / "piper.onnx"
    backend = PiperTTSBackend(non_existent)
    assert backend.is_available() is False

    with pytest.raises(RuntimeError, match="Plik modelu TTS nie istnieje"):
        backend.synthesize("test")

    # Gdy plik istnieje
    non_existent.touch()
    assert backend.is_available() is True
    assert len(backend.synthesize("test")) > 0
