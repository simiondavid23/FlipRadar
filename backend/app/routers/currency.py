from fastapi import APIRouter, Depends, Query
from app.models.user import User
from app.utils.auth import get_current_user
from app.services.currency_service import (
    convert,
    get_eur_ron_rate,
    get_all_rates,
)

router = APIRouter(prefix="/api/currency", tags=["Currency"])


@router.get("/rates")
def currency_rates(current_user: User = Depends(get_current_user)):
    """Return current BNR exchange rates (EUR/USD -> RON)."""
    rates = get_all_rates()
    return {
        "EUR_RON": round(rates["EUR_RON"], 4),
        "USD_RON": round(rates["USD_RON"], 4),
        "RON_EUR": round(1 / rates["EUR_RON"], 4) if rates["EUR_RON"] else 0,
        "RON_USD": round(1 / rates["USD_RON"], 4) if rates["USD_RON"] else 0,
        "source": "BNR (Banca Nationala a Romaniei)",
    }


@router.get("/convert")
def convert_amount(
    amount: float = Query(..., description="Amount to convert"),
    from_currency: str = Query("RON", alias="from"),
    to_currency: str = Query("EUR", alias="to"),
    current_user: User = Depends(get_current_user),
):
    """Convert an amount between currencies using BNR rates."""
    result = convert(amount, from_currency, to_currency)
    return {
        "original_amount": amount,
        "original_currency": from_currency.upper(),
        "converted_amount": result,
        "converted_currency": to_currency.upper(),
    }
