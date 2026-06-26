"""Faza 1 ML — antrenare ensemble (pret + zile pana la vanzare) per categorie,
pe datele reale din market_listings cu sold_at/days_to_sell completate.
"""
import os
import re as _re

import numpy as np
import pandas as pd  # noqa: F401  (rezervat pentru extinderi viitoare)
from sklearn.ensemble import GradientBoostingRegressor, RandomForestRegressor
from sklearn.linear_model import Ridge
from sklearn.preprocessing import StandardScaler  # noqa: F401
from sklearn.model_selection import train_test_split
import joblib

MODELS_DIR = "backend/models/"
MIN_SAMPLES = 500  # minim pentru antrenament


def train_ml_models_if_ready():
    from app.database import SessionLocal
    from app.models.market_listing import MarketListing
    db = SessionLocal()
    try:
        for category in ["auto_bmw", "electronics_apple"]:
            samples = db.query(MarketListing).filter(
                MarketListing.category == category,
                MarketListing.sold_at.isnot(None),
                MarketListing.price.isnot(None),
                MarketListing.days_to_sell.isnot(None),
            ).all()

            if len(samples) < MIN_SAMPLES:
                print(f"[ML] {category}: {len(samples)} exemple — sub minimul de {MIN_SAMPLES}. Skip antrenament.")
                continue

            print(f"[ML] {category}: antrenez modele pe {len(samples)} exemple.")
            _train_category_models(samples, category)
    finally:
        db.close()


def _train_category_models(samples, category):
    X, y_price, y_days = [], [], []
    for s in samples:
        features = _extract_features_vector(s.features or {}, category)
        if features is None:
            continue
        X.append(features)
        y_price.append(float(s.price))
        y_days.append(int(s.days_to_sell))

    if len(X) < MIN_SAMPLES:
        return

    X = np.array(X)
    X_train, X_test, yp_train, yp_test, yd_train, yd_test = train_test_split(
        X, y_price, y_days, test_size=0.2, random_state=42
    )

    # Ensemble pret
    gbm_p = GradientBoostingRegressor(n_estimators=200, max_depth=4, random_state=42)
    rf_p = RandomForestRegressor(n_estimators=150, max_depth=8, random_state=42)
    ridge_p = Ridge(alpha=1.0)
    gbm_p.fit(X_train, yp_train)
    rf_p.fit(X_train, yp_train)
    ridge_p.fit(X_train, yp_train)

    # Ensemble zile
    gbm_d = GradientBoostingRegressor(n_estimators=150, max_depth=3, random_state=42)
    rf_d = RandomForestRegressor(n_estimators=100, max_depth=6, random_state=42)
    gbm_d.fit(X_train, yd_train)
    rf_d.fit(X_train, yd_train)

    os.makedirs(MODELS_DIR, exist_ok=True)
    joblib.dump({"gbm": gbm_p, "rf": rf_p, "ridge": ridge_p}, f"{MODELS_DIR}{category}_price_model.pkl")
    joblib.dump({"gbm": gbm_d, "rf": rf_d}, f"{MODELS_DIR}{category}_days_model.pkl")
    print(f"[ML] {category}: modele salvate in {MODELS_DIR}")


# ── Feature vector builders ───────────────────────────────────────

_BMW_SERIES_MAP = {
    "E30": 30, "E34": 34, "E36": 36, "E46": 46, "E87": 87, "E90": 90,
    "E91": 91, "E92": 92, "E60": 60, "E61": 61, "E63": 63,
    "F20": 20, "F21": 21, "F22": 22, "F30": 30, "F31": 31, "F32": 32,
    "F10": 10, "F11": 11, "F01": 1, "F06": 6,
    "G20": 120, "G21": 121, "G22": 122, "G30": 130, "G11": 111,
}
_BMW_COLOR_MAP = {
    "negru": 0, "black": 0, "alb": 1, "white": 1, "gri": 2, "grey": 2, "gray": 2,
    "argintiu": 3, "silver": 3, "albastru": 4, "blue": 4, "rosu": 5, "red": 5,
    "verde": 7, "green": 7, "bej": 8, "beige": 8, "galben": 9, "yellow": 9,
}
_BMW_BODY_MAP = {
    "touring": 1, "combi": 1, "break": 1, "coupe": 2, "cabrio": 3,
    "suv": 4, "x1": 4, "x3": 4, "x5": 4, "gran coupe": 5, "hatchback": 6,
}
_BMW_PLATFORM_MAP = {"olx": 0, "olx_auto": 0, "autovit": 1, "mobile_de": 2}

_APPLE_LINE_MAP = {"iPhone": 0, "iPad": 1, "MacBook": 2, "AirPods": 3, "Apple Watch": 4}
_APPLE_VARIANT_MAP = {"standard": 0, "mini": 1, "plus": 2, "pro": 3, "pro_max": 4}
_APPLE_ICLOUD_MAP = {"clean": 0, "blocked": 1, "unknown": 2}
_APPLE_UNLOCK_MAP = {"unlocked": 0, "locked": 1, "unknown": 2}
_APPLE_PLATFORM_MAP = {"olx": 0, "vinted": 1}


def _extract_features_vector(features: dict, category: str):
    """Convert features dict to numeric list for ML training/inference.
    Returns None if critical fields are missing.
    """
    if category == "auto_bmw":
        return _bmw_vector(features)
    if category == "electronics_apple":
        return _apple_vector(features)
    return None


def _bmw_vector(f: dict):
    year = f.get("year")
    km = f.get("km")
    if year is None or km is None:
        return None   # critical fields required for meaningful prediction

    series_raw = str(f.get("series") or "").upper().strip()
    series_code = _BMW_SERIES_MAP.get(series_raw, 0)

    motor_raw = str(f.get("motor") or "")
    m = _re.search(r"(\d{3})", motor_raw)
    motor_code = int(m.group(1)) if m else 0

    body_raw = str(f.get("body_type") or "").lower()
    body_code = next((v for k, v in _BMW_BODY_MAP.items() if k in body_raw), 0)

    color_raw = str(f.get("color") or "").lower()
    color_code = next((v for k, v in _BMW_COLOR_MAP.items() if k in color_raw), 6)

    return [
        int(year),                                          # 0  year
        min(int(km), 999999),                               # 1  km (capped)
        1 if f.get("is_diesel") else 0,                     # 2  diesel flag
        1 if f.get("is_automatic") else 0,                  # 3  automatic flag
        min(int(f.get("hp") or 0), 600),                    # 4  horsepower
        series_code,                                        # 5  series (E46→46)
        motor_code,                                         # 6  motor (320→320)
        body_code,                                          # 7  body type
        color_code,                                         # 8  color
        1 if f.get("has_itp") else 0,                       # 9  ITP valid
        1 if f.get("has_service_book") else 0,              # 10 service book
        min(int(f.get("num_owners") or 1), 5),              # 11 owner count
        1 if f.get("has_defects") else 0,                   # 12 defects declared
        1 if f.get("has_xenon") else 0,                     # 13 xenon/LED
        1 if f.get("has_navi") else 0,                      # 14 navigation
        1 if f.get("has_leather") else 0,                   # 15 leather interior
        1 if f.get("has_sunroof") else 0,                   # 16 sunroof/panoramic
        1 if f.get("is_imported") else 0,                   # 17 imported
        _BMW_PLATFORM_MAP.get(str(f.get("platform", "")).lower(), 0),  # 18 platform
    ]


def _apple_vector(f: dict):
    line_code = _APPLE_LINE_MAP.get(f.get("product_line", ""), -1)
    if line_code == -1:
        return None   # unknown product line — skip

    model_year = int(f.get("model_year") or 0)
    variant = _APPLE_VARIANT_MAP.get(f.get("variant", "standard"), 0)
    storage = min(int(f.get("storage_gb") or 0), 2048)
    battery = int(f.get("battery_pct") or 85)
    is_degraded = 1 if battery < 80 else 0
    icloud_code = _APPLE_ICLOUD_MAP.get(f.get("icloud_status", "unknown"), 2)
    screen = int(f.get("screen_condition_score") or 3)
    unlock = _APPLE_UNLOCK_MAP.get(f.get("unlocked_code", "unknown"), 2)
    warranty_months = min(int(f.get("warranty_months") or 0), 24)
    platform_code = _APPLE_PLATFORM_MAP.get(str(f.get("platform", "")).lower(), 0)

    return [
        line_code,                                          # 0  product line
        model_year,                                         # 1  model year
        variant,                                            # 2  variant
        storage,                                            # 3  storage GB
        battery,                                            # 4  battery %
        is_degraded,                                        # 5  battery degraded
        icloud_code,                                        # 6  iCloud status
        screen,                                             # 7  screen score
        1 if f.get("has_box") else 0,                       # 8  has box
        1 if f.get("has_charger") else 0,                   # 9  has charger
        unlock,                                             # 10 unlock status
        1 if f.get("has_warranty") else 0,                  # 11 has warranty
        warranty_months,                                    # 12 warranty months
        platform_code,                                      # 13 platform
    ]


def models_available() -> bool:
    """True daca exista cel putin un model de pret antrenat (pentru log la startup)."""
    if not os.path.isdir(MODELS_DIR):
        return False
    return any(f.endswith("_price_model.pkl") for f in os.listdir(MODELS_DIR))


def predict_price_and_days(category: str, features: dict) -> dict:
    """Face predictie daca modelele sunt antrenate. Altfel returneaza eroare."""
    price_model_path = f"{MODELS_DIR}{category}_price_model.pkl"
    days_model_path = f"{MODELS_DIR}{category}_days_model.pkl"

    if not os.path.exists(price_model_path):
        return {"error": "Date insuficiente pentru predictie ML. Se recomanda estimare AI.", "has_ml": False}

    X = _extract_features_vector(features, category)
    if X is None:
        return {"error": "Date insuficiente pentru constructia vectorului de features.", "has_ml": False}

    X_arr = np.array([X])
    price_models = joblib.load(price_model_path)
    days_models = joblib.load(days_model_path)

    price_pred = (
        0.5 * price_models["gbm"].predict(X_arr)[0] +
        0.35 * price_models["rf"].predict(X_arr)[0] +
        0.15 * price_models["ridge"].predict(X_arr)[0]
    )
    days_pred = (
        0.6 * days_models["gbm"].predict(X_arr)[0] +
        0.4 * days_models["rf"].predict(X_arr)[0]
    )

    return {
        "has_ml": True,
        "predicted_price_eur": round(float(price_pred), 2),
        "predicted_days_to_sell": int(max(1, days_pred)),
        "confidence": "scazuta" if len(joblib.load(price_model_path)) < 1000 else "medie",
    }


# ── Prediction (API ML: /api/ml/predict + /api/ml/stats) ──────────

def predict_price(category: str, features: dict) -> dict:
    """Run ML inference on a features dict.
    Returns {"price": float, "days": int|None} or {"error": str} on failure.
    """
    price_path = os.path.join(MODELS_DIR, f"{category}_price_model.pkl")
    days_path = os.path.join(MODELS_DIR, f"{category}_days_model.pkl")
    if not os.path.exists(price_path):
        return {"error": "model_not_trained"}

    vec = _extract_features_vector(features, category)
    if vec is None:
        return {"error": "features_incomplete"}

    X = np.array([vec])
    pm = joblib.load(price_path)
    # Ensemble average: GBM + RF + Ridge
    price_pred = (
        pm["gbm"].predict(X)[0] * 0.5 +
        pm["rf"].predict(X)[0] * 0.3 +
        pm["ridge"].predict(X)[0] * 0.2
    )
    days_pred = None
    if os.path.exists(days_path):
        dm = joblib.load(days_path)
        days_pred = int(
            dm["gbm"].predict(X)[0] * 0.6 +
            dm["rf"].predict(X)[0] * 0.4
        )

    return {
        "price": round(float(price_pred), 2),
        "days": days_pred,
    }


def get_model_stats() -> dict:
    """Return sample counts and model availability per category."""
    from app.database import SessionLocal
    from app.models.market_listing import MarketListing

    db = SessionLocal()
    stats = {}
    try:
        for cat in ["auto_bmw", "electronics_apple"]:
            total = db.query(MarketListing).filter(
                MarketListing.category == cat).count()
            sold = db.query(MarketListing).filter(
                MarketListing.category == cat,
                MarketListing.sold_at.isnot(None)).count()
            model_path = os.path.join(MODELS_DIR, f"{cat}_price_model.pkl")
            has_model = os.path.exists(model_path)
            trained_at = None
            if has_model:
                trained_at = os.path.getmtime(model_path)
            stats[cat] = {
                "total_collected": total,
                "sold_labeled": sold,
                "min_samples": MIN_SAMPLES,
                "has_model": has_model,
                "trained_at": trained_at,
                "ready_pct": min(100, round(sold / MIN_SAMPLES * 100)),
            }
    finally:
        db.close()
    return stats
