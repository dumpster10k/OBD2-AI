from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

DISCLAIMER_TEXT = "Uwaga: Diagnoza ma charakter pomocniczy i wymaga weryfikacji warsztatowej."


@dataclass(frozen=True)
class LLMModelSpec:
    model_id: str
    name: str
    size_mb: int
    ram_required_mb: int
    format: str  # "gguf", "onnx"
    quantization: str
    context_window: int
    recommended_for: str  # "mobile_ultra_light", "mobile_standard", "desktop"
    description: str


# Rekomendowane malutkie modele LLM do działania offline na telefonie/laptopie
RECOMMENDED_LLM_MODELS: dict[str, LLMModelSpec] = {
    "smollm2-360m": LLMModelSpec(
        model_id="smollm2-360m",
        name="SmolLM2 360M Instruct",
        size_mb=230,
        ram_required_mb=512,
        format="gguf",
        quantization="Q4_K_M",
        context_window=2048,
        recommended_for="mobile_ultra_light",
        description="Ultra-lekki model dla słabszych telefonów z minimalnym zużyciem RAM.",
    ),
    "qwen2.5-0.5b": LLMModelSpec(
        model_id="qwen2.5-0.5b",
        name="Qwen2.5 0.5B Instruct",
        size_mb=350,
        ram_required_mb=700,
        format="gguf",
        quantization="Q4_K_M",
        context_window=4096,
        recommended_for="mobile_standard",
        description="Bardzo mały model o wysokiej precyzji w krótkich objaśnieniach technicznych.",
    ),
    "qwen2.5-1.5b": LLMModelSpec(
        model_id="qwen2.5-1.5b",
        name="Qwen2.5 1.5B Instruct",
        size_mb=980,
        ram_required_mb=1800,
        format="gguf",
        quantization="Q4_K_M",
        context_window=4096,
        recommended_for="mobile_high_end",
        description="Rekomendowany model główny dla standardowych smartfonów. Znakomity język polski.",
    ),
}


class LLMBackend(ABC):
    """Abstrakcyjny interfejs backendu wykonawczego dla lokalnego LLM."""

    @abstractmethod
    def generate(self, prompt: str, max_tokens: int = 200, temperature: float = 0.2) -> str:
        raise NotImplementedError

    @abstractmethod
    def is_available(self) -> bool:
        raise NotImplementedError


class MockLLMBackend(LLMBackend):
    """Deterministyczny backend zastępczy do testów i trybu offline bez pobranych wag."""

    def __init__(self, response_generator: Optional[Callable[[str], str]] = None):
        self.response_generator = response_generator

    def is_available(self) -> bool:
        return True

    def generate(self, prompt: str, max_tokens: int = 200, temperature: float = 0.2) -> str:
        if self.response_generator:
            return self.response_generator(prompt)

        prompt_lower = prompt.lower()
        if "p0300" in prompt_lower or "wypadanie zapłonu" in prompt_lower:
            return (
                "Dla kodu P0300: wypadanie zapłonów może wynikać ze zużytych świec, uszkodzonej cewki lub lewego powietrza. "
                "Zalecam kontrolę świec zapłonowych oraz pomiar ciśnienia sprężania. "
                f"{DISCLAIMER_TEXT}"
            )
        if "p0171" in prompt_lower or "uboga" in prompt_lower:
            return (
                "Zbyt uboga mieszanka paliwowa. Najczęstsze przyczyny to nieszczelny dolot lub zabrudzony przepływomierz MAF. "
                f"{DISCLAIMER_TEXT}"
            )
        if "bezpiecz" in prompt_lower or "jechać" in prompt_lower:
            return (
                "Jeśli kontrolka Check Engine mruga, nie należy kontynuować jazdy. "
                "W przypadku stałego świecenia bez objawów spadku mocy można ostrożnie dojechać do serwisu. "
                f"{DISCLAIMER_TEXT}"
            )

        return f"Odpowiedź asystenta diagnostycznego na zapytanie. {DISCLAIMER_TEXT}"


class LlamaCppBackend(LLMBackend):
    """Adapter dla biblioteki llama.cpp (llama-cpp-python) uruchamiającej modele GGUF."""

    def __init__(self, model_path: str | Path, n_threads: int = 4, n_ctx: int = 2048):
        self.model_path = Path(model_path)
        self.n_threads = n_threads
        self.n_ctx = n_ctx
        self._llm = None
        self._init_error = None

    def _ensure_loaded(self) -> bool:
        if self._llm is not None:
            return True
        if not self.model_path.exists():
            self._init_error = f"Plik modelu nie istnieje: {self.model_path}"
            return False

        try:
            import llama_cpp  # type: ignore

            self._llm = llama_cpp.Llama(
                model_path=str(self.model_path),
                n_threads=self.n_threads,
                n_ctx=self.n_ctx,
                verbose=False,
            )
            return True
        except ImportError:
            self._init_error = "Biblioteka llama-cpp-python nie jest zainstalowana."
            return False
        except Exception as e:
            self._init_error = f"Błąd inicjalizacji modelu GGUF: {e}"
            return False

    def is_available(self) -> bool:
        return self._ensure_loaded()

    def generate(self, prompt: str, max_tokens: int = 200, temperature: float = 0.2) -> str:
        if not self._ensure_loaded():
            raise RuntimeError(self._init_error or "Model LLM nie jest dostępny.")

        output = self._llm(  # type: ignore
            prompt,
            max_tokens=max_tokens,
            temperature=temperature,
            stop=["<|im_end|>", "User:", "\n\nKierowca:"],
        )
        text = output["choices"][0]["text"].strip()
        if DISCLAIMER_TEXT not in text:
            text = f"{text}\n\n{DISCLAIMER_TEXT}"
        return text


class LocalLLMEngine:
    """Główny silnik zarządzający małym lokalnym modelem AI."""

    def __init__(
        self,
        model_spec: Optional[LLMModelSpec] = None,
        backend: Optional[LLMBackend] = None,
        model_dir: Optional[Path] = None,
    ):
        self.model_spec = model_spec or RECOMMENDED_LLM_MODELS["qwen2.5-0.5b"]
        self.model_dir = model_dir or Path.home() / ".cache" / "obd2_ai" / "models"
        self.backend = backend or MockLLMBackend()

    @classmethod
    def list_available_models(cls) -> list[LLMModelSpec]:
        """Zwraca listę rekomendowanych modeli wbudowanych/obsługiwanych."""
        return list(RECOMMENDED_LLM_MODELS.values())

    def set_backend(self, backend: LLMBackend) -> None:
        self.backend = backend

    def format_diagnostic_prompt(
        self,
        query: str,
        vehicle_context: Optional[dict[str, Any]] = None,
    ) -> str:
        """Formatuje prompt w standardzie ChatML z zachowaniem rygorystycznych zasad bezpieczeństwa."""
        context = vehicle_context or {}
        dtc_codes = context.get("dtc_codes", [])
        rpm = context.get("rpm", "brak danych")
        coolant_temp = context.get("coolant_temp", "brak danych")
        speed = context.get("speed", "brak danych")

        system_instruction = (
            "Jesteś profesjonalnym, ostrożnym asystentem diagnostycznym OBD-II dla kierowcy. "
            "Twoje analizy mają wyłącznie charakter hipotez pomocniczych. "
            "NIGDY nie sugeruj samodzielnego kasowania błędów podczas jazdy ani ignorowania czerwonych kontrolek. "
            "Odpowiadaj zwięźle, konkretnie po polsku."
        )

        context_info = (
            f"Kody DTC: {', '.join(dtc_codes) if dtc_codes else 'Brak'}\n"
            f"Telemetria: RPM={rpm}, Płyn chłodzący={coolant_temp}°C, Prędkość={speed} km/h"
        )

        return (
            f"<|im_start|>system\n{system_instruction}\nKontekst pojazdu:\n{context_info}<|im_end|>\n"
            f"<|im_start|>user\n{query}<|im_end|>\n"
            f"<|im_start|>assistant\n"
        )

    def ask(
        self,
        query: str,
        vehicle_context: Optional[dict[str, Any]] = None,
        max_tokens: int = 250,
    ) -> str:
        """Przesyła zapytanie kierowcy do modelu wraz z kontekstem telemetrycznym."""
        prompt = self.format_diagnostic_prompt(query, vehicle_context)
        try:
            response = self.backend.generate(prompt, max_tokens=max_tokens)
            if DISCLAIMER_TEXT not in response:
                response = f"{response}\n\n{DISCLAIMER_TEXT}"
            return response
        except Exception as e:
            logger.warning("Błąd generowania przez LLM: %s. Użycie bezpiecznego fallbacku.", e)
            return (
                f"Nie udało się uzyskać odpowiedzi z modelu lokalnego ({e}). "
                f"Skorzystaj z raportu regułowego DTC. {DISCLAIMER_TEXT}"
            )

    def explain_finding(self, dtc_code: str, title: str, description: str) -> str:
        """Generuje przystępne wyjaśnienie usterki dla kierowcy."""
        query = f"Co oznacza błąd {dtc_code} ({title})? Wyjaśnij prostym językiem przyczynę i co powinienem zrobić."
        context = {"dtc_codes": [dtc_code]}
        return self.ask(query, vehicle_context=context)
