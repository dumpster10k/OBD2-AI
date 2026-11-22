from __future__ import annotations

import hashlib
import logging
import threading
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


class DownloadStatus(str, Enum):
    """Status pobierania modelu."""

    IDLE = "idle"
    DOWNLOADING = "downloading"
    VERIFYING = "verifying"
    INSTALLED = "installed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass(frozen=True)
class ModelDownloadInfo:
    """Informacje o zdalnym pliku modelu w repozytorium Hugging Face lub CDN."""

    model_id: str
    name: str
    repo_id: str
    filename: str
    url: str
    expected_size_bytes: int
    format: str  # "gguf", "onnx", "bin", "zip"
    sha256_hash: Optional[str] = None
    description: str = ""


# Rejestr oficjalnych wag modeli na Hugging Face i serwisach mowy
HUGGINGFACE_MODEL_REGISTRY: dict[str, ModelDownloadInfo] = {
    # Modele LLM (GGUF)
    "smollm2-360m": ModelDownloadInfo(
        model_id="smollm2-360m",
        name="SmolLM2 360M Instruct (GGUF Q4_K_M)",
        repo_id="HuggingFaceTB/SmolLM2-360M-Instruct-GGUF",
        filename="smollm2-360m-instruct-q4_k_m.gguf",
        url="https://huggingface.co/HuggingFaceTB/SmolLM2-360M-Instruct-GGUF/resolve/main/smollm2-360m-instruct-q4_k_m.gguf",
        expected_size_bytes=241_237_920,
        format="gguf",
        description="Ultra-lekki model dla słabszych telefonów z minimalnym zużyciem RAM (~230 MB).",
    ),
    "qwen2.5-0.5b": ModelDownloadInfo(
        model_id="qwen2.5-0.5b",
        name="Qwen2.5 0.5B Instruct (GGUF Q4_K_M)",
        repo_id="Qwen/Qwen2.5-0.5B-Instruct-GGUF",
        filename="qwen2.5-0.5b-instruct-q4_k_m.gguf",
        url="https://huggingface.co/Qwen/Qwen2.5-0.5B-Instruct-GGUF/resolve/main/qwen2.5-0.5b-instruct-q4_k_m.gguf",
        expected_size_bytes=367_120_384,
        format="gguf",
        description="Domyślny lekki model mobilny o wysokiej kulturze technicznej (~350 MB).",
    ),
    "qwen2.5-1.5b": ModelDownloadInfo(
        model_id="qwen2.5-1.5b",
        name="Qwen2.5 1.5B Instruct (GGUF Q4_K_M)",
        repo_id="Qwen/Qwen2.5-1.5B-Instruct-GGUF",
        filename="qwen2.5-1.5b-instruct-q4_k_m.gguf",
        url="https://huggingface.co/Qwen/Qwen2.5-1.5B-Instruct-GGUF/resolve/main/qwen2.5-1.5b-instruct-q4_k_m.gguf",
        expected_size_bytes=986_560_000,
        format="gguf",
        description="Główny model dla standardowych smartfonów i laptopów z bogatym słownictwem PL (~980 MB).",
    ),
    # Modele rozpoznawania mowy (STT - ONNX / bin)
    "whisper-tiny": ModelDownloadInfo(
        model_id="whisper-tiny",
        name="OpenAI Whisper Tiny (ONNX Quantized)",
        repo_id="onnx-community/whisper-tiny",
        filename="whisper-tiny-quantized.onnx",
        url="https://huggingface.co/onnx-community/whisper-tiny/resolve/main/onnx/model_quantized.onnx",
        expected_size_bytes=78_643_200,
        format="onnx",
        description="Ultra-mały model STT działający błyskawicznie na procesorze urządzenia (~75 MB).",
    ),
    "whisper-base": ModelDownloadInfo(
        model_id="whisper-base",
        name="OpenAI Whisper Base (ONNX Quantized)",
        repo_id="onnx-community/whisper-base",
        filename="whisper-base-quantized.onnx",
        url="https://huggingface.co/onnx-community/whisper-base/resolve/main/onnx/model_quantized.onnx",
        expected_size_bytes=145_752_064,
        format="onnx",
        description="Lekki model mowy z wyższą dokładnością języka polskiego (~140 MB).",
    ),
    "vosk-small-pl": ModelDownloadInfo(
        model_id="vosk-small-pl",
        name="Vosk Small Polish",
        repo_id="alphacep/vosk-model-small-pl-0.22",
        filename="vosk-model-small-pl-0.22.zip",
        url="https://alphacephei.com/vosk/models/vosk-model-small-pl-0.22.zip",
        expected_size_bytes=47_185_920,
        format="zip",
        description="Kompaktowy offline STT dedykowany dla języka polskiego (~45 MB).",
    ),
    # Modele syntezy mowy (TTS - ONNX)
    "piper-pl-darkman": ModelDownloadInfo(
        model_id="piper-pl-darkman",
        name="Piper TTS Polish (Darkman Medium ONNX)",
        repo_id="rhasspy/piper-voices",
        filename="pl_PL-darkman-medium.onnx",
        url="https://huggingface.co/rhasspy/piper-voices/resolve/main/pl/pl_PL/darkman/medium/pl_PL-darkman-medium.onnx",
        expected_size_bytes=29_360_128,
        format="onnx",
        description="Naturalna męska synteza mowy w języku polskim w czasie rzeczywistym (~28 MB).",
    ),
    "piper-pl-gosia": ModelDownloadInfo(
        model_id="piper-pl-gosia",
        name="Piper TTS Polish (Gosia Medium ONNX)",
        repo_id="rhasspy/piper-voices",
        filename="pl_PL-gosia-medium.onnx",
        url="https://huggingface.co/rhasspy/piper-voices/resolve/main/pl/pl_PL/gosia/medium/pl_PL-gosia-medium.onnx",
        expected_size_bytes=29_360_128,
        format="onnx",
        description="Naturalna żeńska synteza mowy w języku polskim w czasie rzeczywistym (~28 MB).",
    ),
}


class ModelDownloader:
    """Zarządza bezpiecznym pobieraniem wag modeli AI z Hugging Face.

    Cechy:
    - Pobieranie strumieniowe w kawałkach (chunked download).
    - Bezpieczny zapis do pliku tymczasowego *.part z atomowym przeniesieniem po ukończeniu.
    - Wznawianie pobierania za pomocą nagłówka HTTP Range.
    - Obliczanie i weryfikacja sumy kontrolnej SHA256.
    - Raportowanie postępu (procent, pobrane bajty, prędkość transferu KB/s).
    - Asynchroniczne pobieranie w tle z obsługą anulowania.
    """

    def __init__(
        self,
        target_dir: Optional[Path | str] = None,
        registry: Optional[dict[str, ModelDownloadInfo]] = None,
    ):
        if target_dir:
            self.target_dir = Path(target_dir)
        else:
            self.target_dir = Path.home() / ".cache" / "obd2_ai" / "models"

        self.target_dir.mkdir(parents=True, exist_ok=True)
        self.registry = registry if registry is not None else dict(HUGGINGFACE_MODEL_REGISTRY)

        self._status: dict[str, DownloadStatus] = {}
        self._progress: dict[str, tuple[int, int, float, float]] = {}  # (bytes, total, pct, kbps)
        self._cancel_flags: dict[str, bool] = {}
        self._last_error: dict[str, str] = {}
        self._threads: dict[str, threading.Thread] = {}
        self._lock = threading.Lock()

    def get_model_path(self, model_id: str) -> Path:
        """Zwraca docelową ścieżkę pliku dla danego modelu."""
        if model_id not in self.registry:
            raise KeyError(f"Nieznany model: {model_id}. Dostępne: {list(self.registry.keys())}")
        return self.target_dir / self.registry[model_id].filename

    def is_model_installed(self, model_id: str) -> bool:
        """Sprawdza, czy plik modelu istnieje lokalnie i ma niezerowy rozmiar."""
        if model_id not in self.registry:
            return False
        p = self.get_model_path(model_id)
        return p.is_file() and p.stat().st_size > 0

    def get_installed_models(self) -> dict[str, Path]:
        """Zwraca mapę zainstalowanych modeli {model_id: path}."""
        installed: dict[str, Path] = {}
        for mid in self.registry:
            if self.is_model_installed(mid):
                installed[mid] = self.get_model_path(mid)
        return installed

    def delete_model(self, model_id: str) -> bool:
        """Usuwa zainstalowany plik modelu."""
        try:
            path = self.get_model_path(model_id)
            part_path = Path(str(path) + ".part")
            deleted = False
            if path.exists():
                path.unlink()
                deleted = True
            if part_path.exists():
                part_path.unlink()
                deleted = True
            with self._lock:
                self._status[model_id] = DownloadStatus.IDLE
                self._progress.pop(model_id, None)
            return deleted
        except Exception as e:
            logger.error("Błąd podczas usuwania modelu %s: %s", model_id, e)
            return False

    def get_status(self, model_id: str) -> DownloadStatus:
        """Zwraca aktualny status modelu."""
        if self.is_model_installed(model_id):
            return DownloadStatus.INSTALLED
        with self._lock:
            return self._status.get(model_id, DownloadStatus.IDLE)

    def get_progress(self, model_id: str) -> tuple[int, int, float, float]:
        """Zwraca (pobrane_bajty, łączne_bajty, procent, prędkość_KB_s)."""
        if self.is_model_installed(model_id):
            size = self.get_model_path(model_id).stat().st_size
            return (size, size, 100.0, 0.0)
        with self._lock:
            return self._progress.get(model_id, (0, 0, 0.0, 0.0))

    def get_last_error(self, model_id: str) -> Optional[str]:
        """Zwraca ostatni komunikat błędu dla modelu."""
        with self._lock:
            return self._last_error.get(model_id)

    def cancel_download(self, model_id: str) -> None:
        """Ustawia flagę przerwania pobierania."""
        with self._lock:
            self._cancel_flags[model_id] = True
            self._status[model_id] = DownloadStatus.CANCELLED

    def calculate_sha256(self, file_path: Path) -> str:
        """Oblicza sumę kontrolną SHA256 pliku."""
        hasher = hashlib.sha256()
        with open(file_path, "rb") as f:
            while chunk := f.read(131072):
                hasher.update(chunk)
        return hasher.hexdigest()

    def download_model(
        self,
        model_id: str,
        progress_callback: Optional[Callable[[int, int, float, float], None]] = None,
        allow_resume: bool = True,
        timeout: float = 30.0,
        chunk_size: int = 65536,
    ) -> Path:
        """Pobiera model synchronicznie.

        Args:
            model_id: Identyfikator modelu z rejestru.
            progress_callback: Funkcja zwrotna (pobrane, łączne, procent, prędkość_kbps).
            allow_resume: Czy próbować wznawiać pobieranie nagłówkiem Range.
            timeout: Timeout sieciowy w sekundach.
            chunk_size: Rozmiar bufora pobierania w bajtach.

        Returns:
            Path do gotowego pliku modelu.
        """
        if model_id not in self.registry:
            raise KeyError(f"Model {model_id} nie występuje w rejestrze.")

        info = self.registry[model_id]
        target_path = self.get_model_path(model_id)
        part_path = Path(str(target_path) + ".part")

        if target_path.exists() and target_path.stat().st_size > 0:
            with self._lock:
                self._status[model_id] = DownloadStatus.INSTALLED
            return target_path

        with self._lock:
            self._status[model_id] = DownloadStatus.DOWNLOADING
            self._cancel_flags[model_id] = False
            self._last_error.pop(model_id, None)

        existing_bytes = 0
        headers: dict[str, str] = {
            "User-Agent": "OBD2-AI-ModelDownloader/1.0",
        }

        if allow_resume and part_path.exists():
            existing_bytes = part_path.stat().st_size
            if existing_bytes > 0:
                headers["Range"] = f"bytes={existing_bytes}-"

        req = urllib.request.Request(info.url, headers=headers)

        try:
            with urllib.request.urlopen(req, timeout=timeout) as response:
                status_code = getattr(response, "status", 200)

                if status_code == 206:  # Partial Content
                    mode = "ab"
                    downloaded_bytes = existing_bytes
                    content_len_header = response.headers.get("Content-Length")
                    if content_len_header:
                        total_bytes = downloaded_bytes + int(content_len_header)
                    else:
                        total_bytes = info.expected_size_bytes
                else:  # Pełna odpowiedź 200
                    mode = "wb"
                    downloaded_bytes = 0
                    content_len_header = response.headers.get("Content-Length")
                    total_bytes = int(content_len_header) if content_len_header else info.expected_size_bytes

                start_time = time.time()
                last_time = start_time
                bytes_since_last = 0

                with open(part_path, mode) as out_f:
                    while True:
                        if self._cancel_flags.get(model_id, False):
                            logger.info("Pobieranie modelu %s przerwane przez użytkownika.", model_id)
                            with self._lock:
                                self._status[model_id] = DownloadStatus.CANCELLED
                            raise InterruptedError("Pobieranie zostało anulowane.")

                        chunk = response.read(chunk_size)
                        if not chunk:
                            break

                        out_f.write(chunk)
                        chunk_len = len(chunk)
                        downloaded_bytes += chunk_len
                        bytes_since_last += chunk_len

                        now = time.time()
                        dt = now - last_time
                        if dt >= 0.05 or chunk_size <= 4096:
                            speed_kbps = (bytes_since_last / 1024.0) / dt if dt > 0 else 0.0
                            pct = (downloaded_bytes / total_bytes * 100.0) if total_bytes > 0 else 0.0
                            pct = min(100.0, pct)

                            with self._lock:
                                self._progress[model_id] = (downloaded_bytes, total_bytes, pct, speed_kbps)

                            if progress_callback:
                                try:
                                    progress_callback(downloaded_bytes, total_bytes, pct, speed_kbps)
                                except Exception as cb_err:
                                    logger.debug("Błąd progress_callback: %s", cb_err)

                            last_time = now
                            bytes_since_last = 0

                        if self._cancel_flags.get(model_id, False):
                            logger.info("Pobieranie modelu %s przerwane przez użytkownika.", model_id)
                            with self._lock:
                                self._status[model_id] = DownloadStatus.CANCELLED
                            raise InterruptedError("Pobieranie zostało anulowane.")

            # Weryfikacja sumy kontrolnej lub rozmiaru
            with self._lock:
                self._status[model_id] = DownloadStatus.VERIFYING

            if info.sha256_hash:
                actual_sha = self.calculate_sha256(part_path)
                if actual_sha.lower() != info.sha256_hash.lower():
                    raise ValueError(
                        f"Niezgodność sumy kontrolnej SHA256 dla {model_id}: "
                        f"oczekiwano {info.sha256_hash}, obliczono {actual_sha}"
                    )

            # Atomowe przeniesienie
            if target_path.exists():
                target_path.unlink()
            part_path.rename(target_path)

            final_size = target_path.stat().st_size
            with self._lock:
                self._status[model_id] = DownloadStatus.INSTALLED
                self._progress[model_id] = (final_size, final_size, 100.0, 0.0)

            if progress_callback:
                progress_callback(final_size, final_size, 100.0, 0.0)

            logger.info("Model %s pobrany pomyślnie do: %s", model_id, target_path)
            return target_path

        except Exception as err:
            logger.error("Błąd podczas pobierania modelu %s: %s", model_id, err)
            with self._lock:
                if not self._cancel_flags.get(model_id, False):
                    self._status[model_id] = DownloadStatus.FAILED
                    self._last_error[model_id] = str(err)
            raise

    def download_in_background(
        self,
        model_id: str,
        progress_callback: Optional[Callable[[int, int, float, float], None]] = None,
        completion_callback: Optional[Callable[[bool, Optional[str], Optional[Path]], None]] = None,
        allow_resume: bool = True,
    ) -> threading.Thread:
        """Uruchamia pobieranie modelu w dedykowanym wątku w tle."""

        def _worker() -> None:
            try:
                path = self.download_model(
                    model_id=model_id,
                    progress_callback=progress_callback,
                    allow_resume=allow_resume,
                )
                if completion_callback:
                    completion_callback(True, None, path)
            except Exception as e:
                if completion_callback:
                    completion_callback(False, str(e), None)

        thread = threading.Thread(target=_worker, name=f"ModelDownloader-{model_id}", daemon=True)
        with self._lock:
            self._threads[model_id] = thread
        thread.start()
        return thread
