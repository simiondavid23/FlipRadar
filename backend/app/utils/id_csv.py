"""Helper partajat: parsare CSV de id-uri. Unificat din radar/auto/RE — REF-1."""


def parse_id_csv(ids):
    """CSV de id-uri -> list[int] tolerant: split pe virgula, strip, pastreaza doar tokenii
    care trec int(); ignora restul. [] daca None/gol (fara filtrare pe id)."""
    if not ids:
        return []
    out = []
    for tok in str(ids).split(","):
        tok = tok.strip()
        if not tok:
            continue
        try:
            out.append(int(tok))
        except ValueError:
            continue
    return out
