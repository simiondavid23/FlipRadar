"""PKG-UPD — versiune + verificare de actualizare (GitHub Releases).

Endpointul /api/version sta in routerul health (fara auth, ca /health), deci
folosim clientul neautentificat. Resetam cache-ul in fiecare test si
monkeypatch-uim _fetch_latest_release ca sa nu lovim reteaua.
"""
from app.routers import health


def _reset_cache():
    health._update_cache["checked_at"] = 0.0
    health._update_cache["latest"] = None
    health._update_cache["url"] = None


def test_parse_and_compare_versions():
    assert health._parse_version("v1.2.0") > health._parse_version("0.9.0")
    # egalitate -> nu e "mai nou" -> update_available ar fi False
    assert not (health._parse_version("0.9.0") > health._parse_version("0.9.0"))
    assert health._parse_version("garbage") is None


def test_version_endpoint_update_available(client, monkeypatch):
    _reset_cache()
    monkeypatch.setattr(health, "_fetch_latest_release",
                        lambda: ("v9.9.9", "https://example.com/rel"))
    r = client.get("/api/version")
    assert r.status_code == 200
    body = r.json()
    assert body["version"] == "0.9.0"
    assert body["latest"] == "v9.9.9"
    assert body["update_available"] is True
    assert body["url"] == "https://example.com/rel"


def test_version_endpoint_fetch_failure_is_silent(client, monkeypatch):
    _reset_cache()

    def _boom():
        raise RuntimeError("GitHub down")

    monkeypatch.setattr(health, "_fetch_latest_release", _boom)
    r = client.get("/api/version")
    assert r.status_code == 200          # esecul e silentios — nu 500
    body = r.json()
    assert body["version"] == "0.9.0"
    assert body["update_available"] is False
