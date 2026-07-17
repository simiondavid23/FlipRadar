"""PKG-2 — furnizor AI comutabil per utilizator.

t1-t4 testeaza direct functiile din app.services.ai_service (fara retea — doar
rezolvare de config + construirea clientului). t5-t6 testeaza contractul HTTP
(setari write-only + endpointul de testare a conexiunii, cu OpenAI monkeypatch-uit).
"""
from types import SimpleNamespace

import pytest

from app.services.ai_service import resolve_ai_config, get_ai_client, AIConfigError


def test_resolve_gemini_custom_model():
    u = SimpleNamespace(ai_provider="gemini", ai_api_key="k123", ai_model="my-model")
    client, model = get_ai_client(u)
    assert model == "my-model"  # override-ul userului bate default-ul furnizorului
    assert "generativelanguage" in str(client.base_url)


def test_resolve_env_fallback(monkeypatch):
    monkeypatch.setattr("app.services.ai_service.GROQ_API_KEY", "gsk_test")
    u = SimpleNamespace(ai_provider=None, ai_api_key=None, ai_model=None)
    provider, key, model = resolve_ai_config(u)
    assert provider == "groq"          # default cand ai_provider e None
    assert key == "gsk_test"           # fallback pe cheia din env
    assert model == "llama-3.3-70b-versatile"


def test_resolve_no_key_raises(monkeypatch):
    monkeypatch.setattr("app.services.ai_service.GROQ_API_KEY", "")
    u = SimpleNamespace(ai_provider=None, ai_api_key=None, ai_model=None)
    with pytest.raises(AIConfigError) as ei:
        resolve_ai_config(u)
    assert "Setari" in str(ei.value)   # mesajul trimite userul in Setari


def test_resolve_invalid_provider(monkeypatch):
    monkeypatch.setattr("app.services.ai_service.GROQ_API_KEY", "gsk_test")
    u = SimpleNamespace(ai_provider="openai", ai_api_key="k", ai_model=None)
    with pytest.raises(AIConfigError):
        resolve_ai_config(u)


def test_settings_ai_key_write_only(auth_client):
    r = auth_client.patch("/api/users/settings",
                          json={"ai_provider": "gemini", "ai_api_key": "k123"})
    assert r.status_code == 200
    g = auth_client.get("/api/users/settings").json()
    assert g["ai_provider"] == "gemini"
    assert g["ai_api_key_set"] is True
    assert "ai_api_key" not in g          # cheia nu se intoarce NICIODATA
    # "" sterge cheia
    auth_client.patch("/api/users/settings", json={"ai_api_key": ""})
    g2 = auth_client.get("/api/users/settings").json()
    assert g2["ai_api_key_set"] is False
    assert g2["ai_provider"] == "gemini"  # provider-ul ramane (camp neatins)


def test_ai_test_endpoint(auth_client, monkeypatch):
    class _FakeOK:
        def __init__(self, *a, **k):
            self.chat = SimpleNamespace(
                completions=SimpleNamespace(create=lambda **kw: SimpleNamespace(choices=[])))

    monkeypatch.setattr("app.routers.user_settings.OpenAI", _FakeOK)
    r = auth_client.post("/api/users/ai/test", json={"provider": "groq", "api_key": "ktest"})
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["provider"] == "groq"

    class _FakeErr:
        def __init__(self, *a, **k):
            def _raise(**kw):
                raise RuntimeError("boom")
            self.chat = SimpleNamespace(completions=SimpleNamespace(create=_raise))

    monkeypatch.setattr("app.routers.user_settings.OpenAI", _FakeErr)
    r2 = auth_client.post("/api/users/ai/test", json={"provider": "groq", "api_key": "ktest"})
    assert r2.status_code == 200          # eroarea e in body, nu in status
    body2 = r2.json()
    assert body2["ok"] is False
    assert "boom" in body2["error"]
