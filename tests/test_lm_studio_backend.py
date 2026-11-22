from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from services.llm_engine import (
    DISCLAIMER_TEXT,
    LMStudioBackend,
    LocalLLMEngine,
    OpenAICompatibleBackend,
)


def test_openai_compatible_backend_is_available_success() -> None:
    backend = OpenAICompatibleBackend(endpoint="http://127.0.0.1:1234/v1")

    mock_resp = MagicMock()
    mock_resp.status = 200
    mock_resp.read.return_value = json.dumps({"data": [{"id": "qwen3.5-9b-mtp"}]}).encode("utf-8")
    mock_resp.__enter__.return_value = mock_resp

    with patch("urllib.request.urlopen", return_value=mock_resp):
        assert backend.is_available() is True


def test_openai_compatible_backend_is_available_failure() -> None:
    backend = OpenAICompatibleBackend(endpoint="http://non-existent-host:1234/v1")
    with patch("urllib.request.urlopen", side_effect=Exception("Connection refused")):
        assert backend.is_available() is False


def test_openai_compatible_backend_generate_success() -> None:
    backend = OpenAICompatibleBackend(endpoint="http://127.0.0.1:1234/v1", model_name="qwen3.5-9b-mtp")

    response_data = {
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": "Wszystkie parametry silnika są w normie.",
                }
            }
        ]
    }

    mock_resp = MagicMock()
    mock_resp.read.return_value = json.dumps(response_data).encode("utf-8")
    mock_resp.__enter__.return_value = mock_resp

    with patch("urllib.request.urlopen", return_value=mock_resp):
        res = backend.generate("Jaki jest stan auta?")
        assert "Wszystkie parametry" in res
        assert DISCLAIMER_TEXT in res


def test_openai_compatible_backend_generate_reasoning_fallback() -> None:
    backend = OpenAICompatibleBackend(endpoint="http://127.0.0.1:1234/v1")

    response_data = {
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": "",
                    "reasoning_content": "Analiza wskazuje na prawidłową pracę sondy lambda.",
                }
            }
        ]
    }

    mock_resp = MagicMock()
    mock_resp.read.return_value = json.dumps(response_data).encode("utf-8")
    mock_resp.__enter__.return_value = mock_resp

    with patch("urllib.request.urlopen", return_value=mock_resp):
        res = backend.generate("Sprawdź lambdę")
        assert "prawidłową pracę" in res
        assert DISCLAIMER_TEXT in res


def test_openai_compatible_backend_generate_error() -> None:
    backend = OpenAICompatibleBackend(endpoint="http://127.0.0.1:1234/v1")

    with patch("urllib.request.urlopen", side_effect=Exception("Timeout")):
        with pytest.raises(RuntimeError, match="Błąd komunikacji z serwerem LLM"):
            backend.generate("Test")


def test_lm_studio_backend_detect_best_endpoint() -> None:
    mock_resp = MagicMock()
    mock_resp.status = 200
    mock_resp.__enter__.return_value = mock_resp

    with patch("urllib.request.urlopen", return_value=mock_resp):
        ep = LMStudioBackend._detect_best_endpoint()
        assert "1234" in ep


def test_local_llm_engine_create_auto() -> None:
    # 1. Gdy LM Studio nie odpowiada
    with patch.object(LMStudioBackend, "is_available", return_value=False):
        engine = LocalLLMEngine.create_auto_engine()
        assert engine.backend is not None

    # 2. Gdy LM Studio odpowiada
    with patch.object(LMStudioBackend, "is_available", return_value=True):
        engine_lm = LocalLLMEngine.create_auto_engine()
        assert isinstance(engine_lm.backend, LMStudioBackend)
        assert engine_lm.model_spec.model_id == "qwen3.5-9b-mtp"
