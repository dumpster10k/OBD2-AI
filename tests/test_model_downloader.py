from __future__ import annotations

import io
import threading
import time
import urllib.error
from pathlib import Path
from unittest.mock import patch

import pytest

from core.obd_client import OBDClient
from services.model_downloader import (
    HUGGINGFACE_MODEL_REGISTRY,
    DownloadStatus,
    ModelDownloader,
    ModelDownloadInfo,
)
from tests.test_ui import FakeOBDConnection
from ui.main import CarDoctorUI, DashboardController


class FakeHTTPResponse:
    """Mock dla odpowiedzi urllib.request.urlopen."""

    def __init__(
        self,
        data: bytes,
        status: int = 200,
        headers: dict[str, str] | None = None,
        chunk_size: int = 4096,
    ):
        self.data_stream = io.BytesIO(data)
        self.status = status
        self.headers = headers or {"Content-Length": str(len(data))}
        self.chunk_size = chunk_size

    def read(self, amt: int = -1) -> bytes:
        if amt <= 0:
            return self.data_stream.read()
        return self.data_stream.read(min(amt, self.chunk_size))

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        return False


@pytest.fixture
def temp_models_dir(tmp_path: Path) -> Path:
    d = tmp_path / "models"
    d.mkdir(parents=True, exist_ok=True)
    return d


@pytest.fixture
def downloader(temp_models_dir: Path) -> ModelDownloader:
    return ModelDownloader(target_dir=temp_models_dir)


class TestModelRegistry:
    def test_registry_contains_core_models(self):
        core_ids = [
            "smollm2-360m",
            "qwen2.5-0.5b",
            "qwen2.5-1.5b",
            "whisper-tiny",
            "whisper-base",
            "vosk-small-pl",
            "piper-pl-darkman",
            "piper-pl-gosia",
        ]
        for mid in core_ids:
            assert mid in HUGGINGFACE_MODEL_REGISTRY
            info = HUGGINGFACE_MODEL_REGISTRY[mid]
            assert isinstance(info, ModelDownloadInfo)
            assert info.model_id == mid
            assert info.filename.endswith((".gguf", ".onnx", ".zip", ".bin"))
            assert info.url.startswith("https://")
            assert info.expected_size_bytes > 1_000_000
            assert len(info.repo_id) > 0


class TestModelDownloaderOperations:
    def test_get_model_path_and_installation_status(self, downloader: ModelDownloader, temp_models_dir: Path):
        path = downloader.get_model_path("smollm2-360m")
        assert path == temp_models_dir / "smollm2-360m-instruct-q4_k_m.gguf"
        assert not downloader.is_model_installed("smollm2-360m")
        assert downloader.get_status("smollm2-360m") == DownloadStatus.IDLE

        # Po utworzeniu pustego pliku dalej nie jest installed
        path.touch()
        assert not downloader.is_model_installed("smollm2-360m")

        # Po zapisaniu danych jest installed
        path.write_bytes(b"GGUF_MAGIC_HEADER_AND_WEIGHTS")
        assert downloader.is_model_installed("smollm2-360m")
        assert downloader.get_status("smollm2-360m") == DownloadStatus.INSTALLED

        installed_map = downloader.get_installed_models()
        assert "smollm2-360m" in installed_map
        assert installed_map["smollm2-360m"] == path

    def test_get_model_path_unknown_model_raises(self, downloader: ModelDownloader):
        with pytest.raises(KeyError):
            downloader.get_model_path("non_existent_model_id")

    def test_delete_model(self, downloader: ModelDownloader):
        path = downloader.get_model_path("qwen2.5-0.5b")
        part_path = Path(str(path) + ".part")
        path.write_bytes(b"dummy model data")
        part_path.write_bytes(b"partial data")

        assert downloader.is_model_installed("qwen2.5-0.5b")
        deleted = downloader.delete_model("qwen2.5-0.5b")
        assert deleted is True
        assert not path.exists()
        assert not part_path.exists()
        assert not downloader.is_model_installed("qwen2.5-0.5b")
        assert downloader.get_status("qwen2.5-0.5b") == DownloadStatus.IDLE

        # Usunięcie nieistniejącego modelu zwraca False
        assert downloader.delete_model("qwen2.5-0.5b") is False

    def test_successful_synchronous_download(self, downloader: ModelDownloader):
        fake_content = b"TEST_MODEL_DATA_STREAM_" * 100
        progress_records: list[tuple[int, int, float, float]] = []

        def on_prog(dl: int, tot: int, pct: float, spd: float):
            progress_records.append((dl, tot, pct, spd))

        mock_resp = FakeHTTPResponse(data=fake_content, status=200, chunk_size=64)

        with patch("urllib.request.urlopen", return_value=mock_resp):
            final_path = downloader.download_model(
                model_id="piper-pl-darkman",
                progress_callback=on_prog,
                chunk_size=64,
            )

        assert final_path.exists()
        assert final_path.read_bytes() == fake_content
        assert downloader.is_model_installed("piper-pl-darkman")
        assert downloader.get_status("piper-pl-darkman") == DownloadStatus.INSTALLED
        assert len(progress_records) > 0
        final_prog = progress_records[-1]
        assert final_prog[0] == len(fake_content)
        assert final_prog[2] == 100.0

    def test_download_already_installed_returns_immediately(self, downloader: ModelDownloader):
        p = downloader.get_model_path("whisper-tiny")
        p.write_bytes(b"EXISTS")

        with patch("urllib.request.urlopen") as mock_open:
            result = downloader.download_model("whisper-tiny")
            assert result == p
            mock_open.assert_not_called()

    def test_resume_partial_download(self, downloader: ModelDownloader):
        p = downloader.get_model_path("whisper-base")
        part_p = Path(str(p) + ".part")
        initial_part = b"FIRST_PART_DATA_"
        part_p.write_bytes(initial_part)

        second_part = b"SECOND_PART_DATA_COMPLETED"
        mock_resp = FakeHTTPResponse(
            data=second_part,
            status=206,
            headers={"Content-Length": str(len(second_part))},
            chunk_size=16,
        )

        with patch("urllib.request.urlopen", return_value=mock_resp):
            final_p = downloader.download_model("whisper-base", chunk_size=16)

        assert final_p.exists()
        assert final_p.read_bytes() == initial_part + second_part

    def test_checksum_verification_failure(self, downloader: ModelDownloader):
        custom_registry = {
            "test-checksum": ModelDownloadInfo(
                model_id="test-checksum",
                name="Test Checksum Model",
                repo_id="test/model",
                filename="test.gguf",
                url="https://huggingface.co/test/test.gguf",
                expected_size_bytes=100,
                format="gguf",
                sha256_hash="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",  # hash pustego pliku
            )
        }
        downloader.registry = custom_registry
        mock_resp = FakeHTTPResponse(data=b"NON_EMPTY_CORRUPTED_DATA", status=200)

        with patch("urllib.request.urlopen", return_value=mock_resp):
            with pytest.raises(ValueError, match="Niezgodność sumy kontrolnej SHA256"):
                downloader.download_model("test-checksum")

        assert downloader.get_status("test-checksum") == DownloadStatus.FAILED
        assert "Niezgodność sumy kontrolnej" in str(downloader.get_last_error("test-checksum"))

    def test_cancellation_during_download(self, downloader: ModelDownloader):
        fake_content = b"CHUNK_" * 1000

        def cancel_hook(dl, tot, pct, spd):
            if dl > 100:
                downloader.cancel_download("smollm2-360m")

        mock_resp = FakeHTTPResponse(data=fake_content, status=200, chunk_size=32)

        with patch("urllib.request.urlopen", return_value=mock_resp):
            with pytest.raises(InterruptedError, match="anulowane"):
                downloader.download_model(
                    "smollm2-360m",
                    progress_callback=cancel_hook,
                    chunk_size=32,
                )

        assert downloader.get_status("smollm2-360m") == DownloadStatus.CANCELLED

    def test_network_error_sets_failed_status(self, downloader: ModelDownloader):
        with patch("urllib.request.urlopen", side_effect=urllib.error.URLError("Connection refused")):
            with pytest.raises(urllib.error.URLError):
                downloader.download_model("qwen2.5-1.5b")

        assert downloader.get_status("qwen2.5-1.5b") == DownloadStatus.FAILED
        assert "Connection refused" in str(downloader.get_last_error("qwen2.5-1.5b"))

    def test_download_in_background(self, downloader: ModelDownloader):
        fake_content = b"BACKGROUND_DATA" * 50
        mock_resp = FakeHTTPResponse(data=fake_content, status=200, chunk_size=64)

        done_event = threading.Event()
        callback_result = {}

        def on_done(ok: bool, err: str | None, path: Path | None):
            callback_result["success"] = ok
            callback_result["err"] = err
            callback_result["path"] = path
            done_event.set()

        with patch("urllib.request.urlopen", return_value=mock_resp):
            th = downloader.download_in_background(
                model_id="piper-pl-gosia",
                completion_callback=on_done,
            )
            assert isinstance(th, threading.Thread)
            assert done_event.wait(timeout=5.0)

        assert callback_result.get("success") is True
        assert callback_result.get("path") == downloader.get_model_path("piper-pl-gosia")
        assert downloader.is_model_installed("piper-pl-gosia")


class TestDashboardControllerAndUIDownloaderIntegration:
    def test_controller_downloader_integration(self, temp_models_dir: Path):
        downloader = ModelDownloader(target_dir=temp_models_dir)
        client = OBDClient(connection=FakeOBDConnection(dtc=[], speed=0))
        controller = DashboardController(obd_client=client, model_downloader=downloader)

        assert not controller.is_model_installed("smollm2-360m")

        # Pobieranie przez kontroler
        fake_content = b"CONTROLLER_MODEL_CONTENT"
        mock_resp = FakeHTTPResponse(data=fake_content, status=200)

        done_event = threading.Event()

        def on_complete(ok, err, p):
            done_event.set()

        with patch("urllib.request.urlopen", return_value=mock_resp):
            controller.download_model_async("smollm2-360m", on_complete=on_complete)
            assert done_event.wait(timeout=3.0)

        assert controller.is_model_installed("smollm2-360m")

        # Po zaznaczeniu pobranego modelu status backendu to Lokalny plik
        model_spec = controller.available_models[0]
        controller.on_model_select(model_spec)
        assert controller.model_backend_status == "Zainstalowany (Lokalny plik)"

        # Usunięcie
        assert controller.delete_installed_model("smollm2-360m") is True
        assert not controller.is_model_installed("smollm2-360m")

    def test_ui_model_cards_download_and_delete_buttons(self, temp_models_dir: Path):
        downloader = ModelDownloader(target_dir=temp_models_dir)
        client = OBDClient(connection=FakeOBDConnection(dtc=[], speed=0))
        controller = DashboardController(obd_client=client, model_downloader=downloader)
        ui = CarDoctorUI(controller=controller)

        # Znajdź przycisk pobierania na karcie modelu
        dl_btn = None
        for card in ui.models_grid.children:
            for child in card.children:
                if hasattr(child, "text") and ("Pobierz" in child.text or "Usuń" in child.text):
                    dl_btn = child
                    break
            if dl_btn:
                break

        assert dl_btn is not None
        assert "Pobierz" in dl_btn.text

        # Test kliknięcia w Pobierz
        mock_resp = FakeHTTPResponse(data=b"UI_MOCK_MODEL_DATA", status=200)
        with patch("urllib.request.urlopen", return_value=mock_resp):
            ui._on_model_download_press(dl_btn)
            time.sleep(0.3)  # Pozwól wątkowi daemon ukończyć zapis

        model = dl_btn.user_data
        assert controller.is_model_installed(model.model_id)
        assert "Usuń" in dl_btn.text

        # Test kliknięcia w Usuń
        ui._on_model_download_press(dl_btn)
        assert not controller.is_model_installed(model.model_id)
        assert "Pobierz" in dl_btn.text
        assert "Usunięto model" in ui.model_status_label.text

    def test_ui_speech_card_download_and_delete(self, temp_models_dir: Path):
        downloader = ModelDownloader(target_dir=temp_models_dir)
        client = OBDClient(connection=FakeOBDConnection(dtc=[], speed=0))
        controller = DashboardController(obd_client=client, model_downloader=downloader)
        ui = CarDoctorUI(controller=controller)

        # Znajdź kartę mowy
        stt_col = ui.speech_grid.children[0]
        first_speech_card = stt_col.children[0]
        speech_dl_btn = None
        for child in first_speech_card.children:
            if hasattr(child, "text") and ("Pobierz" in child.text or "Usuń" in child.text):
                speech_dl_btn = child
                break

        assert speech_dl_btn is not None
        assert "Pobierz" in speech_dl_btn.text

        mock_resp = FakeHTTPResponse(data=b"UI_SPEECH_DATA", status=200)
        with patch("urllib.request.urlopen", return_value=mock_resp):
            ui._on_speech_download_press(speech_dl_btn)
            time.sleep(0.3)

        sp_model = speech_dl_btn.user_data
        assert controller.is_model_installed(sp_model.model_id)
        assert "Usuń" in speech_dl_btn.text

        # Usunięcie
        ui._on_speech_download_press(speech_dl_btn)
        assert not controller.is_model_installed(sp_model.model_id)
        assert "Pobierz" in speech_dl_btn.text
