"""PKG-3a — functiile pure ale launcher-ului (fara a porni uvicorn/tray/browser).

Importul modulului `launcher` e sigur: top-level e doar stdlib, iar third-party
(requests/uvicorn/pystray/PIL) + app.* se importa lazy in interiorul functiilor.
"""
import socket
import sys


def test_port_is_free():
    import launcher
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("127.0.0.1", 0))          # OS aloca un port efemer
    port = s.getsockname()[1]
    try:
        assert launcher._port_is_free(port) is False   # ocupat cat socketul e deschis
    finally:
        s.close()
    assert launcher._port_is_free(port) is True         # liber dupa close


def test_choose_port(monkeypatch):
    import launcher
    # 8000 ocupat de alt server (nu FlipRadar), 8001 liber -> (8001, False)
    monkeypatch.setattr(launcher, "_flipradar_at", lambda port: False)
    monkeypatch.setattr(launcher, "_port_is_free", lambda port: port != 8000)
    assert launcher._choose_port() == (8001, False)
    # FlipRadar deja la 8000 -> refolosim instanta -> (8000, True)
    monkeypatch.setattr(launcher, "_flipradar_at", lambda port: port == 8000)
    assert launcher._choose_port() == (8000, True)


def test_resolve_frontend_out(monkeypatch, tmp_path):
    from app.main import _resolve_frontend_out
    # dev: repo/frontend/out
    p = _resolve_frontend_out()
    assert p.name == "out" and p.parent.name == "frontend"
    # frozen: frontend_out/ de langa executabil
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(tmp_path / "FlipRadar.exe"), raising=False)
    assert _resolve_frontend_out() == (tmp_path / "frontend_out").resolve()
