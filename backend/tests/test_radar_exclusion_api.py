"""RP-2 — endpoint tester de excluderi (POST /keywords/{id}/test-exclusion), ambele moduri."""


def _create_keyword(auth_client, **extra):
    payload = {
        "name": "iphone 12", "max_price": 3000, "resale_price": 3500,
        "platform": "olx", "platforms": ["olx"],
        **extra,
    }
    r = auth_client.post("/api/radar/keywords", json=payload)
    assert r.status_code == 200, r.text
    return r.json()["id"]


def test_advanced_mode_word_boundary(auth_client):
    kid = _create_keyword(auth_client, exclude_matching_mode="advanced", exclude_words=["blocat"])
    # advanced: „Deblocat" NU e prins de „blocat" (word-boundary)
    r = auth_client.post(f"/api/radar/keywords/{kid}/test-exclusion", json={"title": "iPhone 12 Deblocat"})
    assert r.status_code == 200
    assert r.json()["excluded"] is False
    assert r.json()["mode"] == "advanced"
    # dar „blocat" ca și cuvânt întreg e prins
    r2 = auth_client.post(f"/api/radar/keywords/{kid}/test-exclusion", json={"title": "iPhone blocat rețea"})
    assert r2.json()["excluded"] is True
    assert r2.json()["matched_rule"]


def test_advanced_mode_exception(auth_client):
    kid = _create_keyword(
        auth_client, exclude_matching_mode="advanced",
        exclude_words=["defect"], exclude_exceptions=[],
    )
    # excepția DEFAULT „fara defecte" neutralizează
    r = auth_client.post(f"/api/radar/keywords/{kid}/test-exclusion", json={"title": "telefon fara defecte"})
    assert r.json()["excluded"] is False


def test_simple_mode_unchanged(auth_client):
    kid = _create_keyword(auth_client, exclude_matching_mode="simple", exclude_words=["blocat"])
    # simplu = substring (comportamentul vechi): „Deblocat" CONȚINE „blocat" -> exclus
    r = auth_client.post(f"/api/radar/keywords/{kid}/test-exclusion", json={"title": "iPhone Deblocat"})
    assert r.status_code == 200
    assert r.json()["excluded"] is True
    assert r.json()["mode"] == "simple"
