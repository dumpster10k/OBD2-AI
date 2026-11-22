from pathlib import Path

import pytest

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
    assistant = VoiceDiagnosticAssistant(speech_service=SpeechService(stt_backend=MockSTTBackend("Jakie mam błędy?")))
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


def test_voice_assistant_coolant_temp_intents():
    assistant = VoiceDiagnosticAssistant()

    # Normalna temperatura
    _, resp_norm, _ = assistant.handle_text_query("Jaka jest temperatura płynu chłodzącego?", {"coolant_temp": 90})
    assert "90°C" in resp_norm
    assert "w normie" in resp_norm

    # Podwyższona temperatura
    _, resp_warn, _ = assistant.handle_text_query("Ile stopni ma płyn?", {"coolant_temp": 110})
    assert "110°C" in resp_warn
    assert "Podwyższona" in resp_warn

    # Krytyczna temperatura
    _, resp_crit, _ = assistant.handle_text_query("Czy silnik się grzeje?", {"coolant_temp": 120})
    assert "120°C" in resp_crit
    assert "Krytyczna" in resp_crit or "zatrzymaj" in resp_crit

    # Brak odczytu
    _, resp_none, _ = assistant.handle_text_query("temperatura cieczy", {"coolant_temp": 0})
    assert "Brak" in resp_none


def test_voice_assistant_voltage_intents():
    assistant = VoiceDiagnosticAssistant()

    # Prawidłowe napięcie
    _, resp_ok, _ = assistant.handle_text_query("Jakie jest napięcie akumulatora?", {"voltage": 14.2})
    assert "14.2 V" in resp_ok
    assert "prawidłowe" in resp_ok

    # Niskie napięcie
    _, resp_low, _ = assistant.handle_text_query("Stan baterii?", {"voltage": 11.2})
    assert "11.2 V" in resp_low
    assert "Niskie" in resp_low

    # Przeładowanie
    _, resp_high, _ = assistant.handle_text_query("Napięcie ładowania?", {"voltage": 15.6})
    assert "15.6 V" in resp_high
    assert "Zbyt wysokie" in resp_high

    # Brak odczytu
    _, resp_zero, _ = assistant.handle_text_query("Napięcie", {"voltage": 0.0})
    assert "Brak" in resp_zero


def test_voice_assistant_speed_and_rpm_intent():
    assistant = VoiceDiagnosticAssistant()
    _, resp, _ = assistant.handle_text_query("Z jaką prędkością jadę i jakie mam obroty?", {"speed": 75, "rpm": 2400})
    assert "75 km/h" in resp
    assert "2400 RPM" in resp


def test_voice_assistant_dtc_explanation():
    assistant = VoiceDiagnosticAssistant()

    # Znany kod błędu z bazy
    _, resp_known, _ = assistant.handle_text_query("Wyjaśnij błąd P0300")
    assert "P0300" in resp_known
    assert "wypadanie zapłonów" in resp_known.lower() or "zapłon" in resp_known.lower()

    # Nieznany kod błędu (fallback do LLM)
    _, resp_unknown, _ = assistant.handle_text_query("Co oznacza kod P9999?")
    assert len(resp_unknown) > 10


def test_voice_assistant_help_intent():
    assistant = VoiceDiagnosticAssistant()
    _, resp, _ = assistant.handle_text_query("Pomoc - jakie komendy mogę wydać?")
    assert "Dostępne polecenia" in resp
    assert "Czy mogę jechać" in resp


def test_voice_assistant_no_dtcs_status():
    assistant = VoiceDiagnosticAssistant()
    _, resp, _ = assistant.handle_text_query("Jakie mam błędy?", {"dtc_codes": []})
    assert "Brak zarejestrowanych błędów" in resp


def test_voice_assistant_vehicle_health_summary():
    assistant = VoiceDiagnosticAssistant()
    _, resp, _ = assistant.handle_text_query("Co z autem?", {"dtc_codes": [], "coolant_temp": 88, "voltage": 14.1})
    assert "Raport stanu pojazdu" in resp


def test_audio_recorder_and_speech_service():
    from services.speech_service import MockAudioRecorder

    recorder = MockAudioRecorder()
    assert recorder.is_available() is True
    audio = recorder.record(duration_sec=1.0)
    assert len(audio) > 44  # Poprawny nagłówek WAV

    service = SpeechService(recorder=recorder)
    rec_audio = service.record_audio(duration_sec=0.5)
    assert len(rec_audio) > 44

    # Przełączanie backendów
    service.set_stt_backend(MockSTTBackend("Nowy tekst"))
    assert service.speech_to_text(b"audio") == "Nowy tekst"

    service.set_tts_backend(MockTTSBackend())
    assert len(service.text_to_speech("Witaj")) > 44

    custom_rec = MockAudioRecorder(simulated_wav=b"custom_wav_data_1234567890")
    service.set_recorder(custom_rec)
    assert service.record_audio() == b"custom_wav_data_1234567890"


def test_ai_engine_voice_text_command():
    from services.ai_engine import AIEngine

    ai = AIEngine()
    q, resp, audio = ai.handle_voice_text_command("Czy mogę jechać dalej?", {"dtc_codes": []})
    assert q == "Czy mogę jechać dalej?"
    assert "Możesz kontynuować" in resp
    assert len(audio) > 44
