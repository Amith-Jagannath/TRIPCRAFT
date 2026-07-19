"""
Currency conversion — Frankfurter API, free and keyless.
Docs: https://www.frankfurter.app/docs/
"""
from __future__ import annotations
import requests
from functools import lru_cache

BASE_URL = "https://api.frankfurter.app/latest"


@lru_cache(maxsize=32)
def get_rate(from_currency: str, to_currency: str = "INR") -> float:
    """Cached because rates don't change within a single planning session."""
    if from_currency.upper() == to_currency.upper():
        return 1.0
    resp = requests.get(BASE_URL, params={"from": from_currency.upper(), "to": to_currency.upper()}, timeout=15)
    resp.raise_for_status()
    rates = resp.json().get("rates", {})
    return rates.get(to_currency.upper(), 1.0)


def convert(amount: float, from_currency: str, to_currency: str = "INR") -> float:
    return round(amount * get_rate(from_currency, to_currency), 2)
