"""Smoke tests HTTP pe baza de test (TestClient, lifespan off)."""


def test_endpoint_protejat_fara_auth_da_401(client):
    # get_current_user cere cookie/Bearer -> 401 fara autentificare.
    r = client.get("/api/tracked-products/")
    assert r.status_code == 401


def test_register_apoi_login_seteaza_cookie(auth_client):
    # auth_client a facut deja register + login; jar-ul trebuie sa aiba cookie-urile.
    assert "access_token" in auth_client.cookies
    assert "refresh_token" in auth_client.cookies


def test_tracked_products_autentificat_lista_goala(auth_client):
    r = auth_client.get("/api/tracked-products/")
    assert r.status_code == 200
    assert r.json() == []   # user nou -> nimic urmarit


def test_facebook_status_nu_expune_session_path(auth_client):
    # Ingheata fixul F6: raspunsul NU mai contine calea absoluta `session_path`.
    r = auth_client.get("/api/radar/facebook/status")
    assert r.status_code == 200
    body = r.json()
    assert "valid" in body
    assert "session_path" not in body
