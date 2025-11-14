# python
import json
import pytest
from types import SimpleNamespace

# Relative import per package layout (test file lives in same package 'utilities')
from . import ai_generator_LLM_Clone as ai_mod
from .ai_generator_LLM_Clone import _call_genai


def _make_client_with_response(resp_obj):
    """Helper to build a fake client whose models.generate_content returns resp_obj."""
    class Models:
        def generate_content(self, *args, **kwargs):
            return resp_obj
    class Client:
        def __init__(self):
            self.models = Models()
    return Client()


def test_call_genai_uses_parsed_model_dump(monkeypatch):
    # Ensure env and SDK placeholders exist
    monkeypatch.setenv("GEMINI_API_KEY", "dummy")
    monkeypatch.setattr(ai_mod, "genai", object())
    monkeypatch.setattr(ai_mod, "GenerateContentConfig", lambda **k: object())

    # Create a response whose parsed has model_dump()
    class Parsed:
        def model_dump(self):
            return {"hello": "world", "num": 1}
    resp = SimpleNamespace(parsed=Parsed(), text=None)

    # Patch _get_client to return our mock client
    mock_client = _make_client_with_response(resp)
    monkeypatch.setattr(ai_mod, "_get_client", lambda: mock_client)

    out = _call_genai("dummy prompt", model="mymodel")
    assert out == json.dumps({"hello": "world", "num": 1}, ensure_ascii=False)


def test_call_genai_uses_parsed_dict_when_model_dump_missing(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "dummy")
    monkeypatch.setattr(ai_mod, "genai", object())
    monkeypatch.setattr(ai_mod, "GenerateContentConfig", lambda **k: object())

    # Response where parsed has dict()
    class ParsedDict:
        def dict(self):
            return {"a": 2, "b": "x"}
    resp = SimpleNamespace(parsed=ParsedDict(), text=None)

    mock_client = _make_client_with_response(resp)
    monkeypatch.setattr(ai_mod, "_get_client", lambda: mock_client)

    out = _call_genai("prompt", model="m")
    assert out == json.dumps({"a": 2, "b": "x"}, ensure_ascii=False)


def test_call_genai_falls_back_to_text(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "dummy")
    monkeypatch.setattr(ai_mod, "genai", object())
    monkeypatch.setattr(ai_mod, "GenerateContentConfig", lambda **k: object())

    # No parsed, but text present
    json_text = '{"ok": true, "msg": "from-text"}'
    resp = SimpleNamespace(parsed=None, text=json_text)

    mock_client = _make_client_with_response(resp)
    monkeypatch.setattr(ai_mod, "_get_client", lambda: mock_client)

    out = _call_genai("p", model="m")
    assert out == json_text


def test_call_genai_raises_when_no_output(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "dummy")
    monkeypatch.setattr(ai_mod, "genai", object())
    monkeypatch.setattr(ai_mod, "GenerateContentConfig", lambda **k: object())

    # Neither parsed nor text -> should raise
    resp = SimpleNamespace(parsed=None, text=None)
    mock_client = _make_client_with_response(resp)
    monkeypatch.setattr(ai_mod, "_get_client", lambda: mock_client)

    with pytest.raises(RuntimeError):
        _call_genai("p", model="m")