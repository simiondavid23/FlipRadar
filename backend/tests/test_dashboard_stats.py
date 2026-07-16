"""DASH-2 — contractul blocului `modules` din /api/dashboard/stats."""


def test_dashboard_stats_contine_blocul_modules(auth_client):
    r = auth_client.get("/api/dashboard/stats")
    assert r.status_code == 200, r.text
    s = r.json()
    assert "modules" in s
    for modul in ("radar", "auto", "imobiliare"):
        assert modul in s["modules"]
        bloc = s["modules"][modul]
        assert isinstance(bloc["new_24h"], int)
        assert isinstance(bloc["active_keywords"], int)


def test_dashboard_stats_campurile_moarte_au_ramas_eliminate(auth_client):
    # Santinela DASH-1: cheile eliminate nu reapar.
    r = auth_client.get("/api/dashboard/stats")
    assert r.status_code == 200, r.text
    s = r.json()
    for cheie in ("total_products_value_eur", "watchlist_total_value_eur", "user", "watchlist_count"):
        assert cheie not in s
