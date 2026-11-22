from __future__ import annotations

import io
import logging
import wave
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Optional

from services.diagnostic_ai import DiagnosticAI, RuleBasedDiagnosticAI
from services.llm_engine import DISCLAIMER_TEXT, LocalLLMEngine

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SpeechModelSpec:
    model_id: str
    name: str
    type: str  # "stt" lub "tts"
    size_mb: int
    ram_required_mb: int
    language: str
    format: str  # "onnx", "bin", "gguf"
    description: str


RECOMMENDED_SPEECH_MODELS: dict[str, SpeechModelSpec] = {
    "whisper-tiny": SpeechModelSpec(
        model_id="whisper-tiny",
        name="OpenAI Whisper Tiny",
        type="stt",
        size_mb=75,
        ram_required_mb=200,
        language="multilingual / pl",
        format="onnx",
        description="Ultra-mały model rozpoznawania mowy działający błyskawicznie na procesorze telefonu.",
    ),
    "whisper-base": SpeechModelSpec(
        model_id="whisper-base",
        name="OpenAI Whisper Base",
        type="stt",
        size_mb=140,
        ram_required_mb=350,
        language="multilingual / pl",
        format="onnx",
        description="Lekki model mowy z wyższą dokładnością języka polskiego.",
    ),
    "vosk-small-pl": SpeechModelSpec(
        model_id="vosk-small-pl",
        name="Vosk Small Polish",
        type="stt",
        size_mb=45,
        ram_required_mb=120,
        language="pl",
        format="bin",
        description="Kompaktowy offline STT dedykowany dla języka polskiego pod systemy wbudowane i Androida.",
    ),
    "piper-pl-darkman": SpeechModelSpec(
        model_id="piper-pl-darkman",
        name="Piper TTS Polish (Darkman Medium)",
        type="tts",
        size_mb=28,
        ram_required_mb=80,
        language="pl",
        format="onnx",
        description="Szybka, naturalna synteza mowy w języku polskim w formacie ONNX. Działa w czasie rzeczywistym.",
    ),
    "piper-pl-gosia": SpeechModelSpec(
        model_id="piper-pl-gosia",
        name="Piper TTS Polish (Gosia Medium)",
        type="tts",
        size_mb=28,
        ram_required_mb=80,
        language="pl",
        format="onnx",
        description="Naturalny damski głos polski do odczytywania komunikatów kierowcy.",
    ),
}


class STTBackend(ABC):
    """Abstrakcyjny interfejs rozpoznawania mowy (Speech-to-Text)."""

    @abstractmethod
    def transcribe(self, audio_data: bytes, language: str = "pl") -> str:
        raise NotImplementedError

    @abstractmethod
    def is_available(self) -> bool:
        raise NotImplementedError


class TTSBackend(ABC):
    """Abstrakcyjny interfejs syntezy mowy (Text-to-Speech)."""

    @abstractmethod
    def synthesize(self, text: str) -> bytes:
        """Zwraca dane audio w formacie WAV."""
        raise NotImplementedError

    @abstractmethod
    def is_available(self) -> bool:
        raise NotImplementedError


class MockSTTBackend(STTBackend):
    """Deterministyczny mock rozpoznawania mowy dla środowisk testowych i braku mikrofonu."""

    def __init__(self, fixed_transcription: str = "Czy mogę bezpiecznie jechać dalej?"):
        self.fixed_transcription = fixed_transcription

    def is_available(self) -> bool:
        return True

    def transcribe(self, audio_data: bytes, language: str = "pl") -> str:
        if not audio_data:
            return ""
        return self.fixed_transcription


class MockTTSBackend(TTSBackend):
    """Generuje poprawny nagłówek pliku WAV (silent PCM) na potrzeby testów i fallbacku."""

    def __init__(self):
        pass

    def is_available(self) -> bool:
        return True

    def synthesize(self, text: str) -> bytes:
        if not text:
            return b""
        # Generujemy miniaturowy, poprawny plik WAV 16kHz mono (0.1 sek ciszy)
        buffer = io.BytesIO()
        with wave.open(buffer, "wb") as wav_file:
            wav_file.setnchannels(1)
            wav_file.setsampwidth(2)
            wav_file.setframerate(16000)
            wav_file.writeframes(b"\x00\x00" * 800)
        return buffer.getvalue()


class WhisperONNXBackend(STTBackend):
    """Adapter dla silnika Whisper w formacie ONNX (np. onnxruntime lub sherpa-onnx)."""

    def __init__(self, model_path: str | Path):
        self.model_path = Path(model_path)
        self._loaded = False

    def is_available(self) -> bool:
        return self.model_path.exists()

    def transcribe(self, audio_data: bytes, language: str = "pl") -> str:
        if not self.is_available():
            raise RuntimeError(f"Plik modelu STT nie istnieje: {self.model_path}")
        # Placeholder integracji natywnego runtime ONNX
        return "Transkrypcja z modelu Whisper ONNX."


class PiperTTSBackend(TTSBackend):
    """Adapter dla syntezatora Piper TTS uruchamianego przez ONNX."""

    def __init__(self, model_path: str | Path):
        self.model_path = Path(model_path)

    def is_available(self) -> bool:
        return self.model_path.exists()

    def synthesize(self, text: str) -> bytes:
        if not self.is_available():
            raise RuntimeError(f"Plik modelu TTS nie istnieje: {self.model_path}")
        # Fallback generowania WAV
        return MockTTSBackend().synthesize(text)


class SpeechService:
    """Zarządza wejściem i wyjściem mowy w aplikacji."""

    def __init__(
        self,
        stt_backend: Optional[STTBackend] = None,
        tts_backend: Optional[TTSBackend] = None,
    ):
        self.stt_backend = stt_backend or MockSTTBackend()
        self.tts_backend = tts_backend or MockTTSBackend()

    @classmethod
    def list_models(cls) -> list[SpeechModelSpec]:
        return list(RECOMMENDED_SPEECH_MODELS.values())

    def speech_to_text(self, audio_bytes: bytes, language: str = "pl") -> str:
        """Przetwarza nagranie audio na tekst."""
        if not audio_bytes:
            return ""
        return self.stt_backend.transcribe(audio_bytes, language=language).strip()

    def text_to_speech(self, text: str) -> bytes:
        """Generuje mowę z podanego tekstu w formacie WAV."""
        if not text:
            return b""
        return self.tts_backend.synthesize(text)


class VoiceDiagnosticAssistant:
    """Asystent głosowy kierowcy integrujący STT, Diagnostic AI, Local LLM oraz TTS.

    Umożliwia bezpieczną, bezdotykową interakcję w trakcie jazdy samochodem.
    """

    def __init__(
        self,
        speech_service: Optional[SpeechService] = None,
        diagnostic_ai: Optional[DiagnosticAI] = None,
        llm_engine: Optional[LocalLLMEngine] = None,
    ):
        self.speech = speech_service or SpeechService()
        self.diagnostic = diagnostic_ai or RuleBasedDiagnosticAI()
        self.llm = llm_engine or LocalLLMEngine()

    def handle_voice_query(
        self,
        audio_data: bytes,
        vehicle_context: Optional[dict[str, Any]] = None,
    ) -> tuple[str, str, bytes]:
        """Przetwarza polecenie głosowe kierowcy:

        1. Rozpoznaje mowę (STT).
        2. Analizuje intencję i kontekst pojazdu.
        3. Formułuje bezpieczną odpowiedź.
        4. Syntezuje mowę (TTS).

        Zwraca: (transkrybowane_pytanie, tekst_odpowiedzi, dane_audio_wav).
        """
        context = vehicle_context or {}
        query = self.speech.speech_to_text(audio_data)

        if not query:
            msg = "Nie usłyszałem pytania. Proszę powtórz."
            return ("", msg, self.speech.text_to_speech(msg))

        query_lower = query.lower()

        # 1. Zabezpieczenie: Próba kasowania błędów głosem
        if any(term in query_lower for term in ["skasuj", "wyczyść", "usuń błąd", "kasuj błędy"]):
            response_text = (
                "Ze względów bezpieczeństwa kasowanie kodów DTC nie może być wykonane głosem. "
                "Wymagane jest manualne potwierdzenie na postoju z wyłączonym silnikiem."
            )
            return (query, response_text, self.speech.text_to_speech(response_text))

        # 2. Pytanie o bezpieczeństwo jazdy
        if any(term in query_lower for term in ["czy mogę jechać", "bezpiecz", "jechać dalej", "czy dojadę"]):
            report = self.diagnostic.analyze(context)
            if not report.safe_to_drive:
                response_text = (
                    f"Uwaga! Nie zalecam dalszej jazdy. Wykryto wysokie ryzyko awarii. {report.summary}"
                )
            else:
                response_text = f"Możesz kontynuować ostrożną jazdę do najbliższego serwisu. {report.summary}"
            return (query, response_text, self.speech.text_to_speech(response_text))

        # 3. Pytanie o aktualne błędy i stan
        if any(term in query_lower for term in ["błędy", "stan", "co z autem", "usterki", "check engine"]):
            report = self.diagnostic.analyze(context)
            response_text = f"Raport diagnostyczny: {report.summary}"
            if report.next_steps:
                response_text += f" Pierwszy krok: {report.next_steps[0]}."
            return (query, response_text, self.speech.text_to_speech(response_text))

        # 4. Szczegółowe pytanie techniczne przekazywane do lokalnego LLM
        response_text = self.llm.ask(query, vehicle_context=context, max_tokens=150)
        return (query, response_text, self.speech.text_to_speech(response_text))
