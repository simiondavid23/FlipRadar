"""Helper partajat: e keyword-ul in fereastra lui orara acum? — FB-7a.

DE CE EXISTA. Evaluarea asta traia in CINCI locuri: `_is_within_active_hours` din
radar_scanner (canonicul), cate un `_within_hours` identic in scanerele de imobiliare,
auto si loturi auto, plus `_in_ore_active` din executorul Facebook — care delega lenes
spre canonic si mai purta INCA o copie ca rezerva in `except`. Comentariul lui explica
si de ce: `radar_scanner` e un modul greu care importa scraperele, iar executorul
trebuie sa ramana importabil singur, dar „nu exista un helper comun de nivel util".
Modulul asta e helperul care lipsea.

Cinci implementari care trebuie sa spuna acelasi lucru pot diverge TACUT — exact clasa
de defect gasita la FB-FRANA-1, unde forma orara se aplica de doua ori si nimeni n-a
observat 14 ore pe zi.

DEPENDINTE: doar stdlib. E o conditie, nu o intamplare — tot rostul modulului e sa fie
importabil de oriunde, inclusiv din module care nu-si permit sa traga aplicatia dupa ele.
"""
from datetime import datetime


def in_ore_active(kw, acum=None) -> bool:
    """True daca `kw` trebuie scanat la ora data (implicit: acum).

    Regula, pastrata EXACT ca in canonicul din radar_scanner:
      * oricare margine `None` -> mereu activ (fereastra neconfigurata nu inseamna
        fereastra goala);
      * interval normal (`s <= e`) -> `s <= h < e`, adica start INCLUSIV, end EXCLUSIV;
      * interval peste miezul noptii (`s > e`) -> `h >= s or h < e`. Exemplul din
        canonic: start=22, end=6 inseamna activ 22:00-05:59.

    `acum` e cusatura de ceas. Fara ea, orice test pe fereastra ar trece sau ar pica
    dupa ora la care e rulata suita — lectia FB-FRANA-1, unde exact asta s-a intamplat
    si a ascuns un bug real 14 ore pe zi. Ceasul ramane NAIV LOCAL (`datetime.now()`),
    ca in toate cele cinci situri de dinainte: schimbarea fusului ar fi o schimbare de
    comportament, iar FB-7a e strict conservatoare.

    Marginile se citesc prin `getattr`, deci merge cu orice model de keyword — Radar,
    Auto, AutoLot, Imobiliare — si cu obiecte care n-au deloc campurile (caz in care
    sunt „mereu activ", ca la margini absente). Rezerva din executor facea deja asa;
    aici devine regula unica.
    """
    s = getattr(kw, "active_hours_start", None)
    e = getattr(kw, "active_hours_end", None)
    if s is None or e is None:
        return True
    h = (acum or datetime.now()).hour
    return (s <= h < e) if s <= e else (h >= s or h < e)
