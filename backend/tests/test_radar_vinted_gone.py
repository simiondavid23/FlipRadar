"""RAD-1 — fetch_item_page distinge itemul sters (404 curat) de un esec de fetch.

404 fara semnatura de blocare -> {"gone": True} (apelantul trece listingul pe
`removed` si il scoate din coada de enrichment). Orice alt esec, inclusiv 403
(= blocare), ramane None -> reincercare, comportament neschimbat.

Fara retea: `get_html` e stubuit cu un raspuns fals (status + text).
"""
import app.services.radar.vinted_html as vh


class _Resp:
    def __init__(self, status_code, text):
        self.status_code = status_code
        self.text = text


def _patch_get_html(monkeypatch, status, text):
    """Stub pe get_html + captura emisiilor de log. Returneaza lista de (nivel, mesaj)."""
    monkeypatch.setattr(vh, "get_html", lambda *a, **k: _Resp(status, text))
    emis = []
    monkeypatch.setattr(vh.log_manager, "emit",
                        lambda modul, nivel, mesaj, *a, **k: emis.append((nivel, mesaj)))
    return emis


def test_404_curat_inseamna_item_disparut(monkeypatch):
    _patch_get_html(monkeypatch, 404, "<html><body>Not found</body></html>")
    assert vh.fetch_item_page("123456") == {"gone": True}


def test_404_nu_emite_warn(monkeypatch):
    # Itemul sters e normal, nu un esec -> fara WARN (scannerul logheaza INFO).
    emis = _patch_get_html(monkeypatch, 404, "<html><body>Not found</body></html>")
    vh.fetch_item_page("123456")
    assert [e for e in emis if e[0] == "WARN"] == []


def test_403_nu_e_gone_ci_esec(monkeypatch):
    # 403 = blocare (_looks_blocked) -> None, ca sa fie reincercat mai tarziu.
    _patch_get_html(monkeypatch, 403, "blocked")
    assert vh.fetch_item_page("123456") is None


def test_403_pastreaza_warn(monkeypatch):
    emis = _patch_get_html(monkeypatch, 403, "blocked")
    vh.fetch_item_page("123456")
    assert any(nivel == "WARN" for nivel, _ in emis)


def test_500_ramane_esec(monkeypatch):
    _patch_get_html(monkeypatch, 500, "boom")
    assert vh.fetch_item_page("123456") is None


def test_skip_din_guard_ramane_none(monkeypatch):
    # get_html None (breaker/plafon) -> contract neschimbat, nu se confunda cu gone.
    monkeypatch.setattr(vh, "get_html", lambda *a, **k: None)
    assert vh.fetch_item_page("123456") is None
