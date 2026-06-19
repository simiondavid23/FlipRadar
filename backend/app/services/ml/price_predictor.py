"""Faza 1 ML — antrenare ensemble (pret + zile pana la vanzare) per categorie,
pe datele reale din market_listings cu sold_at/days_to_sell completate.
"""
import os

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


def _extract_features_vector(features: dict, category: str):
    """Converteste features dict intr-un vector numeric. None daca lipsesc date cheie."""
    if category == "auto_bmw":
        year = features.get("year")
        km = features.get("km")
        if not year or not km:
            return None
        engine_map = {"benzina": 0, "diesel": 1, "hibrid": 2, "electric": 3, "gpl": 4}
        gearbox_map = {"manuala": 0, "automata": 1}
        return [
            int(year),
            int(km),
            engine_map.get(str(features.get("engine_type", "")).lower(), -1),
            gearbox_map.get(str(features.get("gearbox", "")).lower(), -1),
            float(features.get("price", 0)),
        ]
    elif category == "electronics_apple":
        price = features.get("price")
        if not price:
            return None
        product_map = {"iPhone": 0, "iPad": 1, "MacBook": 2, "AirPods": 3, "Apple Watch": 4}
        return [
            product_map.get(features.get("product_line", ""), -1),
            int(features.get("storage_gb", 0)),
            float(features.get("battery_health_pct", 100)),
            float(price),
        ]
    return None


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
