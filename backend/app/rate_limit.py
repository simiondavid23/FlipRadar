"""MODIFICARE 5 — instanță unică Limiter (slowapi) pentru rate limiting.

Definită într-un modul dedicat (nu în main.py) ca să poată fi importată atât de
main.py, cât și de routerele care decorează endpoint-uri de scraping, fără import
circular (routerele sunt importate de main.py înainte ca `app` să existe).
"""
from slowapi import Limiter
from slowapi.util import get_remote_address

# Cheia de rate limiting = adresa IP a clientului.
limiter = Limiter(key_func=get_remote_address)
