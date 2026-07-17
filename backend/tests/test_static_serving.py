"""PKG-1 — servirea frontend-ului static exportat din FastAPI (catch-all serve_frontend).

Nu depindem de un build real: monkeypatch pe app.main.FRONTEND_OUT catre un tmp_path
populat cu fisiere fabricate (marker distinct per fisier), ca sa validam rutarea si
conventia FLAT .html independent de `npm run build`.
"""
import pytest


@pytest.fixture
def static_out(tmp_path, monkeypatch):
    """out/ fals legat la catch-all-ul din app.main; fiecare fisier are marker propriu."""
    (tmp_path / "index.html").write_text("<html>MARKER_INDEX</html>", encoding="utf-8")
    (tmp_path / "login.html").write_text("<html>MARKER_LOGIN</html>", encoding="utf-8")
    (tmp_path / "dashboard").mkdir()
    (tmp_path / "dashboard" / "alerts.html").write_text("<html>MARKER_ALERTS</html>", encoding="utf-8")
    (tmp_path / "404.html").write_text("<html>MARKER_404</html>", encoding="utf-8")
    monkeypatch.setattr("app.main.FRONTEND_OUT", tmp_path)
    return tmp_path


def test_root_serves_index_html(client, static_out):
    r = client.get("/")
    assert r.status_code == 200
    assert "MARKER_INDEX" in r.text


def test_login_flat_html_convention(client, static_out):
    # conventia FLAT: /login -> login.html (nu login/index.html)
    r = client.get("/login")
    assert r.status_code == 200
    assert "MARKER_LOGIN" in r.text


def test_deep_path_served(client, static_out):
    # cai adanci: /dashboard/alerts -> dashboard/alerts.html
    r = client.get("/dashboard/alerts")
    assert r.status_code == 200
    assert "MARKER_ALERTS" in r.text


def test_unknown_path_falls_back_to_404_html(client, static_out):
    r = client.get("/nu-exista")
    assert r.status_code == 404
    assert "MARKER_404" in r.text


def test_api_unknown_returns_json_not_html(client, static_out):
    r = client.get("/api/ruta-inexistenta")
    assert r.status_code == 404
    assert "MARKER" not in r.text  # NU serveste HTML pe /api/*
    assert r.json()["detail"]  # e JSON cu `detail`
