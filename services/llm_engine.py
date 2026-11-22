from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.request
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
    "qwen3.5-9b-mtp": LLMModelSpec(
        model_id="qwen3.5-9b-mtp",
        name="Qwen 3.5 9B MTP (LM Studio)",
        size_mb=5800,
        ram_required_mb=8192,
        format="gguf",
        quantization="Q4_K_M",
        context_window=32768,
        recommended_for="desktop_lm_studio",
        description="Zaawansowany model 9B z predykcją wielo-tokenową (MTP), hostowany w LM Studio.",
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


class OpenAICompatibleBackend(LLMBackend):
    """Adapter dla lokalnych serwerów LLM zgodnych z API OpenAI (LM Studio, vLLM, Ollama, llama-server)."""

    def __init__(
        self,
        endpoint: str = "http://localhost:1234/v1",
        model_name: str = "qwen3.5-9b-mtp",
        timeout: float = 15.0,
    ):
        self.endpoint = endpoint.rstrip("/")
        self.model_name = model_name
        self.timeout = timeout

    def is_available(self) -> bool:
        """Sprawdza dostępność serwera wykonując szybkie zapytanie GET /models."""
        try:
            req = urllib.request.Request(f"{self.endpoint}/models", method="GET")
            with urllib.request.urlopen(req, timeout=1.5) as resp:
                if resp.status == 200:
                    data = json.loads(resp.read().decode("utf-8"))
                    return "data" in data or "models" in data
        except Exception:
            return False
        return False

    def generate(self, prompt: str, max_tokens: int = 300, temperature: float = 0.2) -> str:
        """Przesyła prompt do serwera przez Chat Completions API."""
        url = f"{self.endpoint}/chat/completions"
        payload = {
            "model": self.model_name,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        body = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                choices = data.get("choices", [])
                if not choices:
                    raise RuntimeError("Brak wygenerowanych odpowiedzi z serwera LLM.")
                msg = choices[0].get("message", {})
                text = msg.get("content") or ""
                # W przypadku modeli myślących (Qwen/DeepSeek), gdy content jest pusty z powodu długiego myślenia
                if not text.strip() and "reasoning_content" in msg:
                    text = msg.get("reasoning_content", "").strip()

                text = text.strip()
                if DISCLAIMER_TEXT not in text:
                    text = f"{text}\n\n{DISCLAIMER_TEXT}"
                return text
        except Exception as e:
            raise RuntimeError(f"Błąd komunikacji z serwerem LLM ({self.endpoint}): {e}") from e


class LMStudioBackend(OpenAICompatibleBackend):
    """Specjalizowany backend dla LM Studio z automatyczną detekcją hosta w WSL2 i localhost."""

    DEFAULT_CANDIDATES = [
        "http://172.31.208.1:1234/v1",  # Brama WSL2
        "http://localhost:1234/v1",
        "http://127.0.0.1:1234/v1",
    ]

    def __init__(
        self,
        endpoint: Optional[str] = None,
        model_name: str = "qwen3.5-9b-mtp",
        timeout: float = 20.0,
    ):
        target_endpoint = endpoint or os.environ.get("LM_STUDIO_URL")
        if not target_endpoint:
            target_endpoint = self._detect_best_endpoint()

        super().__init__(endpoint=target_endpoint, model_name=model_name, timeout=timeout)

    @classmethod
    def _detect_best_endpoint(cls) -> str:
        """Skanuje znane adresy nasłuchu LM Studio i wybiera pierwszy aktywny."""
        candidates = list(cls.DEFAULT_CANDIDATES)
        env_url = os.environ.get("LM_STUDIO_URL")
        if env_url:
            candidates.insert(0, env_url)

        for ep in candidates:
            try:
                req = urllib.request.Request(f"{ep.rstrip('/')}/models", method="GET")
                with urllib.request.urlopen(req, timeout=1.0) as resp:
                    if resp.status == 200:
                        return ep
            except Exception:
                continue
        return "http://localhost:1234/v1"


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

    @classmethod
    def create_auto_engine(cls, preferred_model_id: str = "qwen3.5-9b-mtp") -> LocalLLMEngine:
        """Automatycznie tworzy silnik LLM próbując najpierw podłączyć działające LM Studio."""
        lm_backend = LMStudioBackend(model_name=preferred_model_id)
        if lm_backend.is_available():
            spec = RECOMMENDED_LLM_MODELS.get(preferred_model_id) or RECOMMENDED_LLM_MODELS["qwen3.5-9b-mtp"]
            return cls(model_spec=spec, backend=lm_backend)
        return cls()

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
