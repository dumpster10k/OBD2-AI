from __future__ import annotations

import io
import logging
import re
import wave
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Optional

from services.diagnostic_ai import (
    STANDARD_DTC_DATABASE,
    DiagnosticAI,
    RuleBasedDiagnosticAI,
)
from services.llm_engine import LocalLLMEngine

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


class VoiceIntent(str, Enum):
    """Zidentyfikowana intencja polecenia głosowego kierowcy."""

    CLEAR_DTC = "clear_dtc"
    SAFE_TO_DRIVE = "safe_to_drive"
    DTC_STATUS = "dtc_status"
    DTC_EXPLAIN = "dtc_explain"
    COOLANT_TEMP = "coolant_temp"
    VOLTAGE = "voltage"
    SPEED_RPM = "speed_rpm"
    HELP = "help"
    VEHICLE_HEALTH = "vehicle_health"
    GENERAL_LLM = "general_llm"


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


class AudioRecorder(ABC):
    """Abstrakcyjny interfejs nagrywania dźwięku z mikrofonu."""

    @abstractmethod
    def record(self, duration_sec: float = 3.0, sample_rate: int = 16000) -> bytes:
        """Nagrywa dźwięk z mikrofonu i zwraca bajty pliku WAV."""
        raise NotImplementedError

    @abstractmethod
    def is_available(self) -> bool:
        raise NotImplementedError


class LiveAudioRecorder(AudioRecorder):
    """Rejestruje dźwięk z fizycznego mikrofonu za pomocą biblioteki sounddevice."""

    def __init__(self, device: Optional[int | str] = None):
        self.device = device
        self.device_name = self._detect_device_name()

    def _detect_device_name(self) -> str:
        try:
            import sounddevice as sd

            if self.device is not None:
                info = sd.query_devices(self.device)
                if isinstance(info, list) and info:
                    info = info[0]
                if isinstance(info, dict):
                    return str(info.get("name", f"Urządzenie {self.device}"))
            devices = sd.query_devices()
            if isinstance(devices, list):
                for d in devices:
                    if d.get("max_input_channels", 0) > 0:
                        return str(d.get("name", "Domyślny mikrofon"))
            elif isinstance(devices, dict):
                return str(devices.get("name", "Domyślny mikrofon"))
            return "Fizyczny mikrofon"
        except Exception:
            return "Fizyczny mikrofon"

    @classmethod
    def is_available(cls) -> bool:
        """Sprawdza, czy sounddevice jest zainstalowane i czy dostępne jest urządzenie wejściowe."""
        try:
            import sounddevice as sd

            devices = sd.query_devices()
            if isinstance(devices, dict):
                return bool(devices.get("max_input_channels", 0) > 0)
            for d in devices:
                if d.get("max_input_channels", 0) > 0:
                    return True
            return False
        except Exception:
            return False

    def record(self, duration_sec: float = 3.0, sample_rate: int = 16000) -> bytes:
        raw_bytes: bytes
        try:
            import sounddevice as sd

            frames_count = int(duration_sec * sample_rate)
            recording = sd.rec(frames_count, samplerate=sample_rate, channels=1, dtype="int16", device=self.device)
            sd.wait()
            raw_bytes = recording.tobytes()
        except Exception as e:
            logger.warning("Błąd nagrywania fizycznego mikrofonu: %s", e)
            raw_bytes = b"\x00\x00" * int(duration_sec * sample_rate)

        buffer = io.BytesIO()
        with wave.open(buffer, "wb") as wav_file:
            wav_file.setnchannels(1)
            wav_file.setsampwidth(2)
            wav_file.setframerate(sample_rate)
            wav_file.writeframes(raw_bytes)
        return buffer.getvalue()


class MockAudioRecorder(AudioRecorder):
    """Deterministyczny mock nagrywania mikrofonu dla testów i środowisk headless."""

    def __init__(self, simulated_wav: Optional[bytes] = None):
        self.simulated_wav = simulated_wav

    def is_available(self) -> bool:
        return True

    def record(self, duration_sec: float = 3.0, sample_rate: int = 16000) -> bytes:
        if self.simulated_wav:
            return self.simulated_wav
        buffer = io.BytesIO()
        with wave.open(buffer, "wb") as wav_file:
            wav_file.setnchannels(1)
            wav_file.setsampwidth(2)
            wav_file.setframerate(sample_rate)
            frames_count = int(duration_sec * sample_rate)
            wav_file.writeframes(b"\x00\x00" * frames_count)
        return buffer.getvalue()


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
        recorder: Optional[AudioRecorder] = None,
    ):
        self.stt_backend = stt_backend or MockSTTBackend()
        self.tts_backend = tts_backend or MockTTSBackend()
        if recorder is not None:
            self.recorder = recorder
        elif LiveAudioRecorder.is_available():
            self.recorder = LiveAudioRecorder()
        else:
            self.recorder = MockAudioRecorder()

    def get_microphone_status(self) -> dict[str, Any]:
        """Zwraca stan dostępności fizycznego mikrofonu w systemie."""
        is_live = isinstance(self.recorder, LiveAudioRecorder) and self.recorder.is_available()
        dev_name = getattr(self.recorder, "device_name", "Mock Recorder")
        return {
            "is_available": self.recorder.is_available(),
            "is_live": is_live,
            "device_name": dev_name if is_live else "Brak fizycznego urządzenia",
            "message": (
                f"Fizyczny mikrofon aktywny: {dev_name}"
                if is_live
                else "Brak fizycznego mikrofonu lub biblioteki sounddevice. Użyj pola tekstowego."
            ),
        }

    @classmethod
    def list_models(cls) -> list[SpeechModelSpec]:
        return list(RECOMMENDED_SPEECH_MODELS.values())

    def set_stt_backend(self, backend: STTBackend) -> None:
        self.stt_backend = backend

    def set_tts_backend(self, backend: TTSBackend) -> None:
        self.tts_backend = backend

    def set_recorder(self, recorder: AudioRecorder) -> None:
        self.recorder = recorder

    def record_audio(self, duration_sec: float = 3.0) -> bytes:
        """Nagrywa dźwięk z mikrofonu przez skonfigurowany recorder."""
        return self.recorder.record(duration_sec=duration_sec)

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

    def detect_intent(self, query: str) -> tuple[VoiceIntent, dict[str, Any]]:
        """Klasyfikuje intencję zapytania kierowcy oraz wyodrębnia parametry (np. kod DTC)."""
        q = query.lower().strip()

        # 1. Bezwzględna ochrona: próba kasowania błędów głosem
        if any(
            term in q
            for term in ["skasuj", "wyczyść", "usuń błąd", "kasuj błędy", "resetuj błędy", "skasować", "kasowani"]
        ):
            return (VoiceIntent.CLEAR_DTC, {})

        # 2. Pomoc i lista komend
        if any(term in q for term in ["pomoc", "co potrafisz", "komend", "jakie komendy", "instrukcj", "opcje"]):
            return (VoiceIntent.HELP, {})

        # 3. Wyjaśnienie konkretnego kodu błędu (np. "wyjaśnij P0300", "co oznacza błąd P0171", lub sam kod "P0171")
        dtc_match = re.search(r"\b([PBUCpbuc][0-3]\d{3})\b", query)
        if dtc_match:
            if (
                any(term in q for term in ["wyjaśnij", "co oznacza", "co to jest", "opis", "błąd", "kod"])
                or len(q.split()) <= 2
            ):
                return (VoiceIntent.DTC_EXPLAIN, {"code": dtc_match.group(1).upper()})

        # 4. Temperatura cieczy chłodzącej / silnika
        if any(term in q for term in ["temperatur", "ile stopni", "płyn chłodząc", "ciecz", "grzeje"]):
            return (VoiceIntent.COOLANT_TEMP, {})

        # 5. Napięcie akumulatora / ładowanie
        if any(term in q for term in ["napięci", "napięć", "akumulator", "bater", "ładowani", "alternator", "volt"]):
            return (VoiceIntent.VOLTAGE, {})

        # 6. Prędkość i obroty silnika
        if any(term in q for term in ["obrot", "prędkoś", "ile jadę", "szybkoś", "rpm", "km/h"]):
            return (VoiceIntent.SPEED_RPM, {})

        # 7. Odczyt kodów błędów DTC
        if any(term in q for term in ["błąd", "błędy", "błędów", "usterk", "check engine", "kody"]):
            return (VoiceIntent.DTC_STATUS, {})

        # 8. Pytanie o bezpieczeństwo jazdy
        if any(term in q for term in ["czy mogę jechać", "bezpiecz", "jechać dalej", "czy dojadę", "dalsza jazda"]):
            return (VoiceIntent.SAFE_TO_DRIVE, {})

        # 9. Ogólny stan auta / podsumowanie
        if any(term in q for term in ["co z autem", "stan auta", "jaki stan", "ogólny stan", "podsumuj"]):
            return (VoiceIntent.VEHICLE_HEALTH, {})

        # 10. Zapytanie ogólne -> Local LLM
        return (VoiceIntent.GENERAL_LLM, {})

    def handle_text_query(
        self,
        query: str,
        vehicle_context: Optional[dict[str, Any]] = None,
    ) -> tuple[str, str, bytes]:
        """Przetwarza tekstowe zapytanie kierowcy bez konieczności transkrypcji STT."""
        context = vehicle_context or {}
        cleaned_query = query.strip()

        if not cleaned_query:
            msg = "Nie usłyszałem pytania. Proszę powtórz."
            return ("", msg, self.speech.text_to_speech(msg))

        intent, params = self.detect_intent(cleaned_query)

        if intent == VoiceIntent.CLEAR_DTC:
            response_text = (
                "Ze względów bezpieczeństwa kasowanie kodów DTC nie może być wykonane głosem. "
                "Wymagane jest manualne potwierdzenie na postoju z wyłączonym silnikiem."
            )
        elif intent == VoiceIntent.HELP:
            response_text = (
                "Dostępne polecenia głosowe: 'Czy mogę jechać?', 'Jakie mam błędy?', "
                "'Jaka jest temperatura?', 'Napięcie akumulatora', 'Prędkość i obroty', "
                "'Wyjaśnij błąd P0300' lub dowolne pytanie diagnostyczne."
            )
        elif intent == VoiceIntent.COOLANT_TEMP:
            temp = context.get("coolant_temp", 0)
            if temp >= 115:
                response_text = (
                    f"Krytyczna temperatura cieczy chłodzącej: {temp}°C! Natychmiast zatrzymaj pojazd i wyłącz silnik."
                )
            elif temp >= 105:
                response_text = f"Podwyższona temperatura cieczy chłodzącej: {temp}°C. Zredukuj obciążenie silnika i obserwuj wskaźnik."
            elif temp <= 0:
                response_text = "Brak aktywnego odczytu temperatury cieczy chłodzącej z magistrali OBD."
            else:
                response_text = f"Temperatura cieczy chłodzącej wynosi {temp}°C. Parametr w normie roboczej."
        elif intent == VoiceIntent.VOLTAGE:
            voltage = float(context.get("voltage", 0.0))
            if 0 < voltage < 11.8:
                response_text = f"Niskie napięcie instalacji: {voltage:.1f} V. Możliwe rozładowanie akumulatora lub awaria alternatora."
            elif voltage > 15.0:
                response_text = f"Zbyt wysokie napięcie: {voltage:.1f} V. Ryzyko przeładowania akumulatora i uszkodzenia elektroniki."
            elif voltage >= 11.8:
                response_text = (
                    f"Napięcie instalacji wynosi {voltage:.1f} V. Ładowanie i stan akumulatora są prawidłowe."
                )
            else:
                response_text = "Brak odczytu napięcia z adaptera OBD-II."
        elif intent == VoiceIntent.SPEED_RPM:
            speed = context.get("speed", 0)
            rpm = context.get("rpm", 0)
            response_text = f"Bieżąca prędkość pojazdu to {speed} km/h, a prędkość obrotowa wynosi {rpm} RPM."
        elif intent == VoiceIntent.DTC_EXPLAIN:
            code = params.get("code", "")
            if code in STANDARD_DTC_DATABASE:
                entry = STANDARD_DTC_DATABASE[code]
                action_text = f" Zalecany krok: {entry['actions'][0]}." if entry.get("actions") else ""
                response_text = f"Kod {code}: {entry['title']}. {entry['description']}{action_text}"
            else:
                response_text = self.llm.ask(
                    f"Wyjaśnij krótko kod błędu {code}", vehicle_context=context, max_tokens=120
                )
        elif intent == VoiceIntent.DTC_STATUS:
            dtc_codes = context.get("dtc_codes", [])
            if not dtc_codes:
                response_text = (
                    "Brak zarejestrowanych błędów w sterowniku silnika. Wszystkie układy działają poprawnie."
                )
            else:
                report = self.diagnostic.analyze(context)
                step = f" Pierwszy krok: {report.next_steps[0]}." if report.next_steps else ""
                response_text = (
                    f"Wykryto kody błędów {', '.join(dtc_codes)}. Raport diagnostyczny: {report.summary}.{step}"
                )
        elif intent == VoiceIntent.SAFE_TO_DRIVE:
            report = self.diagnostic.analyze(context)
            if not report.safe_to_drive:
                response_text = f"Uwaga! Nie zalecam dalszej jazdy. Wykryto wysokie ryzyko awarii. {report.summary}"
            else:
                response_text = f"Możesz kontynuować ostrożną jazdę do najbliższego serwisu. {report.summary}"
        elif intent == VoiceIntent.VEHICLE_HEALTH:
            report = self.diagnostic.analyze(context)
            response_text = f"Raport stanu pojazdu: {report.summary} Poziom pilności: {report.overall_urgency.upper()}."
        else:
            # Ogólne zapytanie techniczne do LLM
            response_text = self.llm.ask(cleaned_query, vehicle_context=context, max_tokens=150)

        audio_bytes = self.speech.text_to_speech(response_text)
        return (cleaned_query, response_text, audio_bytes)

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
        if not audio_data:
            msg = "Nie usłyszałem pytania. Proszę powtórz."
            return ("", msg, self.speech.text_to_speech(msg))

        query = self.speech.speech_to_text(audio_data)
        return self.handle_text_query(query, vehicle_context=vehicle_context)
