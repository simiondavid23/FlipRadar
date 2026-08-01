"""NET-5.2b — configuratia rotatorului se valideaza la pornire.

`MODEM_ROTATION_METHOD` scris gresit arunca ValueError din `build_rotator()`, iar
`get_rotator()` lasa singletonul pe None si re-arunca la fiecare apel. Fara verificarea
de la boot, simptomul apare abia dupa 5 minute, pe toate platformele legate deodata, si
arata ca o problema de modem.

Testele apeleaza `_check_rotator_config()` direct — nu porneste `lifespan`.
"""
import pytest

from app.main import _check_rotator_config
from app.services.network.rotator import NoopRotator, get_rotator, reset_rotator


@pytest.fixture(autouse=True)
def clean_modem_env(monkeypatch):
    import os
    for key in list(os.environ):
        if key.startswith("MODEM_"):
            monkeypatch.delenv(key, raising=False)
    reset_rotator()
    yield
    reset_rotator()


def test_metoda_invalida_e_raportata_la_boot_fara_sa_arunce(monkeypatch, capsys):
    monkeypatch.setenv("MODEM_ROTATION_ENABLED", "true")
    monkeypatch.setenv("MODEM_ROTATION_METHOD", "datswitch")   # o litera lipsa
    _check_rotator_config()          # nu are voie sa arunce: app-ul trebuie sa porneasca
    out = capsys.readouterr().out
    assert "CONFIGURATIE INVALIDA" in out
    # Mesajul trebuie sa numeasca variabila, altfel omul cauta la modem.
    assert "MODEM_ROTATION_METHOD" in out


def test_lifespan_chiar_apeleaza_validarea():
    """Testele de mai sus apeleaza functia direct, deci NU pot vedea daca firul din
    `lifespan` dispare — verificarea ar exista, dar n-ar rula niciodata la pornire.
    Pornirea reala a lui `lifespan` ar instala Playwright si ar inregistra ~20 de joburi,
    deci pinuim call site-ul la nivel de sursa."""
    import inspect

    from app import main
    # Linie care E apelul, nu doar text care il contine: un `# _check_rotator_config()`
    # comentat ar trece un simplu `in`.
    linii = [ln.strip() for ln in inspect.getsource(main.lifespan).splitlines()]
    assert "_check_rotator_config()" in linii


def test_config_valida_nu_raporteaza_eroare(capsys):
    # Fara MODEM_ROTATION_ENABLED => NoopRotator, calea implicita a instalarilor.
    _check_rotator_config()
    out = capsys.readouterr().out
    assert "CONFIGURATIE INVALIDA" not in out
    assert "NoopRotator" in out
    assert isinstance(get_rotator(), NoopRotator)
