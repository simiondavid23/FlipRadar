from sqlalchemy import Column, Integer, Float, String, DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.orm import relationship
from datetime import datetime, timezone
from app.database import Base


class ResaleFeeProfile(Base):
    """FASHION-3a — profilul de taxe al unei platforme de revanzare, per user.

    Taxele NU se scrapeaza niciodata: se configureaza. Procentele vin cu un seed
    verificat manual (vezi routers/resale.py), iar taxele fixe si transportul
    raman 0 pana cand userul le completeaza cu valorile CONTULUI lui — depind de
    nivel de vanzator, tara si metoda de plata, deci o valoare "generala" ar fi
    o minciuna comoda.

    Nimic derivat nu se stocheaza aici: netul se recalculeaza mereu din profilul
    curent (vezi resale_service.compute_net_ron).
    """

    __tablename__ = "resale_fee_profiles"
    __table_args__ = (
        UniqueConstraint("user_id", "platform", name="uq_resale_fee_profile_user_platform"),
    )

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    # "stockx" / "goat" pentru seed; string liber pentru profilurile custom.
    platform = Column(String, nullable=False, index=True)
    label = Column(String, nullable=False)

    # Procente aplicate pe pretul de referinta (0-100, nu fractii).
    commission_pct = Column(Float, nullable=False, default=0.0)
    processing_pct = Column(Float, nullable=False, default=0.0)
    extra_pct = Column(Float, nullable=False, default=0.0)
    # Sume absolute, in `currency` — pot fi in ALTA moneda decat referinta.
    fixed_fee = Column(Float, nullable=False, default=0.0)
    shipping_cost = Column(Float, nullable=False, default=0.0)
    currency = Column(String, nullable=False, default="EUR")

    # Data la care procentele au fost verificate pe pagina oficiala (text, nu
    # timestamp: e o nota de provenienta pentru om, nu o valoare calculabila).
    verified_at = Column(String, nullable=True)
    note = Column(String, nullable=True)

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc),
                        onupdate=lambda: datetime.now(timezone.utc))

    user = relationship("User")
