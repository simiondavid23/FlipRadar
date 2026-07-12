"""GE-7 — teste pentru modulul Gestiune: vanzari din inventar (decrement/epuizare/
refuz), restaurarea stocului la stergere (GE-6a), stats cu extra_costs (GE-4a), rapoarte cu
categoria denormalizata (GE-3) si ROI agregat (GE-6b), plafonul de import. EUR-only unde e
posibil (fara retea); multi-moneda cu convert mock-uit."""
import io

from openpyxl import Workbook


_IMPORT_HEADER = ["nume", "categorie", "sku", "cantitate", "pret_achizitie", "moneda", "sursa", "note"]


def _mk_item(auth_client, name, qty, price, currency="EUR", category=None):
    payload = {"name": name, "quantity": qty, "purchase_price": price, "currency": currency}
    if category:
        payload["category"] = category
    r = auth_client.post("/api/inventory/", json=payload)
    assert r.status_code == 200, r.text
    return r.json()


def _mk_sale(auth_client, **payload):
    r = auth_client.post("/api/sales/", json=payload)
    return r


def _items_by_name(auth_client):
    r = auth_client.get("/api/inventory/")
    assert r.status_code == 200, r.text
    return {it["name"]: it for it in r.json()}


def _make_xlsx(header, rows):
    wb = Workbook()
    ws = wb.active
    ws.append(header)
    for row in rows:
        ws.append(row)
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf.getvalue()


# ── GRUPA A: crearea vanzarii din inventar ──────────────────────────────────────
def test_vanzare_din_inventar_decrement_si_autofill(auth_client):
    item = _mk_item(auth_client, "GE7 A1 Casti", qty=5, price=60, category="Audio")
    r = _mk_sale(auth_client, inventory_item_id=item["id"], quantity=2, sale_price=100)
    assert r.status_code == 200, r.text
    body = r.json()
    # nume/cost/moneda/categorie preluate automat din inventar
    assert body["cost_price"] == 60
    assert body["currency"] == "EUR"
    assert body["category"] == "Audio"
    assert body["inventory_item_id"] == item["id"]
    assert _items_by_name(auth_client)["GE7 A1 Casti"]["quantity"] == 3


def test_vanzare_epuizeaza_stocul_sterge_articolul(auth_client):
    item = _mk_item(auth_client, "GE7 A2 Mouse", qty=2, price=30)
    r = _mk_sale(auth_client, inventory_item_id=item["id"], quantity=2, sale_price=50)
    assert r.status_code == 200, r.text
    assert "GE7 A2 Mouse" not in _items_by_name(auth_client)


def test_vanzare_peste_stoc_refuzata(auth_client):
    item = _mk_item(auth_client, "GE7 A3 Tastatura", qty=1, price=40)
    r = _mk_sale(auth_client, inventory_item_id=item["id"], quantity=3, sale_price=50)
    assert r.status_code == 400
    assert r.json()["detail"] == "Stocul disponibil este 1, nu poti vinde 3."
    assert _items_by_name(auth_client)["GE7 A3 Tastatura"]["quantity"] == 1


def test_vanzare_cu_articol_inexistent(auth_client):
    r = _mk_sale(auth_client, inventory_item_id=999999, quantity=1, sale_price=50)
    assert r.status_code == 404
    assert r.json()["detail"] == "Articolul de inventar nu a fost gasit."
    sales = auth_client.get("/api/sales/")
    assert sales.status_code == 200, sales.text
    assert sales.json() == []


def test_vanzare_manuala_fara_link(auth_client):
    r = _mk_sale(auth_client, product_name="GE7 A5 Manual", sale_price=80, quantity=1, category="Manuala")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["inventory_item_id"] is None
    assert body["category"] == "Manuala"


# ── GRUPA B: stergerea vanzarii — GE-6a ─────────────────────────────────────────
def test_stergere_restituie_stocul(auth_client):
    item = _mk_item(auth_client, "GE7 B1 Boxa", qty=5, price=100)
    r = _mk_sale(auth_client, inventory_item_id=item["id"], quantity=2, sale_price=150)
    assert r.status_code == 200, r.text
    assert _items_by_name(auth_client)["GE7 B1 Boxa"]["quantity"] == 3
    d = auth_client.delete(f"/api/sales/{r.json()['id']}")
    assert d.status_code == 200, d.text
    assert _items_by_name(auth_client)["GE7 B1 Boxa"]["quantity"] == 5


def test_stergere_recreeaza_articolul_epuizat(auth_client):
    item = _mk_item(auth_client, "GE7 B2 Telefon", qty=2, price=15, category="Telefoane")
    r = _mk_sale(auth_client, inventory_item_id=item["id"], quantity=2, sale_price=99)
    assert r.status_code == 200, r.text
    assert "GE7 B2 Telefon" not in _items_by_name(auth_client)  # articolul s-a epuizat
    d = auth_client.delete(f"/api/sales/{r.json()['id']}")
    assert d.status_code == 200, d.text
    recreat = _items_by_name(auth_client)["GE7 B2 Telefon"]
    assert recreat["quantity"] == 2
    assert recreat["purchase_price"] == 15
    assert recreat["category"] == "Telefoane"
    assert (recreat["notes"] or "").startswith("Recreat automat")


def test_stergere_vanzare_manuala_nu_atinge_inventarul(auth_client):
    _mk_item(auth_client, "GE7 B3 Control", qty=4, price=20)
    r = _mk_sale(auth_client, product_name="GE7 B3 Vanzare", sale_price=10, quantity=1)
    assert r.status_code == 200, r.text
    before = _items_by_name(auth_client)
    d = auth_client.delete(f"/api/sales/{r.json()['id']}")
    assert d.status_code == 200, d.text
    after = _items_by_name(auth_client)
    assert set(before) == set(after)
    assert after["GE7 B3 Control"]["quantity"] == 4


# ── GRUPA C: stats /api/sales/stats ─────────────────────────────────────────────
def test_stats_profit_extra_si_fara_cost(auth_client):
    _mk_sale(auth_client, product_name="GE7 C1 X", sale_price=100, quantity=1, cost_price=60, extra_costs=10, currency="EUR")
    _mk_sale(auth_client, product_name="GE7 C1 Y", sale_price=50, quantity=1, currency="EUR")
    r = auth_client.get("/api/sales/stats")
    assert r.status_code == 200, r.text
    s = r.json()
    assert s["total_revenue_eur"] == 150.0
    assert s["total_cost_eur"] == 60.0
    assert s["total_extra_costs_eur"] == 10.0
    assert s["total_profit_eur"] == 80.0
    assert s["sales_without_cost"] == 1


def test_stats_multi_moneda_convert_mockuit(auth_client, monkeypatch):
    # patch DOAR pe namespace-ul app.routers.sales — reports nu e implicat aici
    monkeypatch.setattr(
        "app.routers.sales.convert",
        lambda amount, frm, to: round(amount * (0.2 if (frm or "").upper() == "RON" and to == "EUR" else 1.0), 2),
    )
    _mk_sale(auth_client, product_name="GE7 C2 RON", sale_price=100, quantity=1, cost_price=50, currency="RON")
    _mk_sale(auth_client, product_name="GE7 C2 EUR", sale_price=30, quantity=1, cost_price=10, currency="EUR")
    r = auth_client.get("/api/sales/stats")
    assert r.status_code == 200, r.text
    s = r.json()
    assert s["total_revenue_eur"] == 50.0   # 20 (RON->EUR) + 30 (EUR)
    assert s["total_cost_eur"] == 20.0      # 10 (RON->EUR) + 10 (EUR)
    assert s["total_profit_eur"] == 30.0


# ── GRUPA D: rapoarte ───────────────────────────────────────────────────────────
def test_reports_roi_agregat_si_fara_cost(auth_client):
    _mk_sale(auth_client, product_name="GE7 D1 A", sale_price=100, quantity=1, cost_price=60, extra_costs=10, currency="EUR")
    _mk_sale(auth_client, product_name="GE7 D1 B", sale_price=40, quantity=1, cost_price=20, currency="EUR")
    _mk_sale(auth_client, product_name="GE7 D1 C", sale_price=50, quantity=1, currency="EUR")
    r = auth_client.get("/api/reports/summary")
    assert r.status_code == 200, r.text
    s = r.json()
    assert s["profit_total"] == 100.0
    # ROI agregat: (30+20) / (70+20) * 100 = 55.555... -> 55.6
    assert s["roi_mediu"] == 55.6
    assert s["vanzari_fara_cost"] == 1


def test_reports_categoria_denormalizata_si_fallback(auth_client):
    # (1) categoria denormalizata supravietuieste stergerii articolului (santinela bug G-1)
    drona = _mk_item(auth_client, "GE7 D2 Drona", qty=1, price=500, category="Drone")
    r1 = _mk_sale(auth_client, inventory_item_id=drona["id"], quantity=1, sale_price=800)
    assert r1.status_code == 200, r1.text
    assert "GE7 D2 Drona" not in _items_by_name(auth_client)  # articol epuizat
    # (2) fallback pe join de nume: articol ramas in inventar + vanzare manuala cu acelasi nume
    _mk_item(auth_client, "GE7 D2 Boxa", qty=3, price=100, category="Audio")
    r2 = _mk_sale(auth_client, product_name="GE7 D2 Boxa", sale_price=150, quantity=1, currency="EUR")
    assert r2.status_code == 200, r2.text
    # (3) vanzare manuala fara categorie -> Necunoscut
    r3 = _mk_sale(auth_client, product_name="GE7 D2 Misterios", sale_price=20, quantity=1, currency="EUR")
    assert r3.status_code == 200, r3.text

    r = auth_client.get("/api/reports/summary")
    assert r.status_code == 200, r.text
    cats = {c["categorie"] for c in r.json()["top_categorii"]}
    assert "Drone" in cats
    assert "Audio" in cats
    assert "Necunoscut" in cats


def test_reports_serie_zile(auth_client):
    _mk_sale(auth_client, product_name="GE7 D3 A", sale_price=100, quantity=1, currency="EUR", sold_at="2026-07-10")
    _mk_sale(auth_client, product_name="GE7 D3 B", sale_price=50, quantity=1, currency="EUR", sold_at="2026-07-12")
    r = auth_client.get("/api/reports/summary", params={"date_from": "2026-07-10", "date_to": "2026-07-12"})
    assert r.status_code == 200, r.text
    serie = r.json()["vanzari_pe_zi"]
    assert len(serie) == 3
    assert serie[0]["data"] == "2026-07-10" and serie[0]["venit"] == 100.0
    assert serie[1]["data"] == "2026-07-11" and serie[1]["venit"] == 0.0  # ziua din mijloc, fara vanzari
    assert serie[2]["data"] == "2026-07-12" and serie[2]["venit"] == 50.0


# ── GRUPA E: importul Excel ─────────────────────────────────────────────────────
def test_import_plafon_2000(auth_client):
    rows = [[f"GE7 E1 {i}", None, None, 1, 10.0, "EUR", None, None] for i in range(2001)]
    content = _make_xlsx(_IMPORT_HEADER, rows)
    r = auth_client.post(
        "/api/inventory/import-excel",
        files={"file": ("inventar.xlsx", content, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    )
    assert r.status_code == 400
    assert r.json()["detail"] == "Fisierul depaseste limita de 2000 de randuri per import."
    assert _items_by_name(auth_client) == {}


def test_import_happy_path(auth_client):
    rows = [
        ["GE7 E2 Alpha", "Cat", "SKU1", 3, 25.0, "EUR", "src", "note"],
        ["GE7 E2 Beta", "Cat2", "SKU2", 7, 40.0, "EUR", None, None],
    ]
    content = _make_xlsx(_IMPORT_HEADER, rows)
    r = auth_client.post(
        "/api/inventory/import-excel",
        files={"file": ("inventar.xlsx", content, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    )
    assert r.status_code == 200, r.text
    items = _items_by_name(auth_client)
    assert items["GE7 E2 Alpha"]["quantity"] == 3
    assert items["GE7 E2 Alpha"]["purchase_price"] == 25.0
    assert items["GE7 E2 Beta"]["quantity"] == 7
    assert items["GE7 E2 Beta"]["purchase_price"] == 40.0
