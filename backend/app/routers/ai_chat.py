from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func
from app.database import get_db
from app.models.user import User
from app.models.chat_message import ChatMessage
from app.models.watchlist import WatchlistItem
from app.models.alert import Alert
from app.models.product import Product
from app.models.inventory import InventoryItem
from app.models.sale import Sale
from app.schemas.ai import ChatRequest, ChatResponse
from app.utils.auth import get_current_user, require_feature

_ai_user = require_feature("can_use_ai")
from app.services.ai_service import chat_with_groq

router = APIRouter(prefix="/api/ai", tags=["AI Chat"])


BASE_SYSTEM_PROMPT = """Esti FlipRadar AI Assistant, asistent virtual pentru platforma FlipRadar.
FlipRadar este o aplicatie web care ajuta utilizatorii sa gaseasca produse profitabile pentru revanzare online, urmarind preturi pe Altex, eMAG, Sole, FarmaciaTei si PCGarage.

Functionalitati FlipRadar (acestea sunt singurele despre care raspunzi):
- Cauta Produse: catalogul utilizatorului cu produse adaugate (manual sau prin scraping). De aici se pot adauga produse la favorite sau la blacklist.
- Web Scraping: cauta produse pe magazinele integrate (Altex, eMAG, Sole, FarmaciaTei, PCGarage) si le salveaza in catalog.
- Watchlist: produse urmarite pentru evolutia pretului.
- Alerte de pret: setezi un prag, primesti notificare in aplicatie + email cand pretul scade/creste sub/peste prag.
- Notificari: feed in-app cu alertele declansate.
- Favorite & Blacklist: marcheaza produse de interes (favorite) sau evita-le (blacklist).
- Inventar: produsele pe care le ai pe stoc, cu pret achizitie, cantitate, sursa, note. Per articol exista un calculator rapid de profit (introduci pret vanzare + costuri extra, primesti profit / ROI / marja).
- Vanzari: inregistrarea vanzarilor, calcul profit pe baza pretului de vanzare si a costului de achizitie, conversie automata RON-EUR la cursul BNR. Produsele se pot prelua direct din inventar.
- AI: Analiza produs (verifica profitabilitatea unui produs), Listing Generator (genereaza descriere + bullet points), Raport AI (insight-uri pe inventarul utilizatorului), si acest chat support.
- Import / Export: import CSV/Excel pentru produse si inventar, export Excel pentru produse, watchlist, inventar; export PDF pentru vanzari.

Rolul tau:
1. Ajuti utilizatorul sa foloseasca eficient functionalitatile listate mai sus.
2. Oferi sfaturi personalizate bazate pe DATELE UTILIZATORULUI de mai jos - foloseste numele lui, produsele lui concrete din watchlist/inventar, alertele lui.
3. Adaptezi tonul la profilul utilizatorului (utilizator nou vs activ).

Reguli stricte:
- Raspunde DOAR in limba romana.
- Raspunzi DOAR despre functionalitatile FlipRadar listate mai sus si despre cum se folosesc. La intrebari off-topic (subiecte care nu au legatura cu aplicatia) redirectioneaza politicos catre subiectul aplicatiei.
- Daca utilizatorul intreaba despre o functionalitate care nu apare in lista de mai sus, spune simplu ca nu este disponibila pe FlipRadar.
- Daca utilizatorul e nou (fara produse/alerte), incurajeaza-l sa inceapa cu Cauta Produse sau Web Scraping.
- Daca utilizatorul are deja activitate, fa referire concreta la datele lui (ex: \"produsul X din watchlistul tau\", \"alerta ta pentru Y\").
- Daca are o problema tehnica sau vrea sa vorbeasca cu o persoana reala, adauga la sfarsit exact textul: [NEEDS_STAFF]
- Raspunsuri concise (2-5 propozitii), concrete, cu pasi practici cand e posibil.
"""


def _build_user_context(db: Session, user: User) -> str:
    """Collect a compact snapshot of the user's state for the system prompt."""

    watchlist_count = (
        db.query(func.count(WatchlistItem.id))
        .filter(WatchlistItem.user_id == user.id)
        .scalar()
    )
    active_alerts = (
        db.query(func.count(Alert.id))
        .filter(Alert.user_id == user.id, Alert.is_active == True)
        .scalar()
    )
    triggered_alerts = (
        db.query(func.count(Alert.id))
        .filter(Alert.user_id == user.id, Alert.is_triggered == True)
        .scalar()
    )
    inventory_count = (
        db.query(func.count(InventoryItem.id))
        .filter(InventoryItem.user_id == user.id)
        .scalar()
    )
    sales_count = (
        db.query(func.count(Sale.id))
        .filter(Sale.user_id == user.id)
        .scalar()
    )

    # Sample of watchlist product names
    watchlist_sample = (
        db.query(Product.name, Product.source, Product.current_price, Product.currency)
        .join(WatchlistItem, WatchlistItem.product_id == Product.id)
        .filter(WatchlistItem.user_id == user.id)
        .order_by(WatchlistItem.added_at.desc())
        .limit(5)
        .all()
    )
    watchlist_preview = "; ".join(
        [
            f"{n} ({s or '?'}, {p or 0} {c or 'EUR'})"
            for (n, s, p, c) in watchlist_sample
        ]
    ) or "gol"

    display_name = user.full_name or user.username or user.email

    return f"""
--- DATE UTILIZATOR ---
Nume: {display_name}
Email: {user.email}
Admin: {"da" if user.is_admin else "nu"}
Watchlist: {watchlist_count} produse. Cele mai recente: {watchlist_preview}
Alerte active: {active_alerts} | Declansate: {triggered_alerts}
Inventar: {inventory_count} articole salvate.
Vanzari inregistrate: {sales_count}
--- FINAL DATE UTILIZATOR ---
"""


@router.post("/chat", response_model=ChatResponse)
async def chat_support(
    request: ChatRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(_ai_user),
):
    """Chat with the personalized FlipRadar AI Support Assistant."""

    user_context = _build_user_context(db, current_user)
    personalized_prompt = BASE_SYSTEM_PROMPT + user_context

    response_text = await chat_with_groq(
        message=request.message,
        system_prompt=personalized_prompt,
        history=request.history if request.history else [],
    )

    needs_staff = "[NEEDS_STAFF]" in response_text
    clean_response = response_text.replace("[NEEDS_STAFF]", "").strip()

    user_msg = ChatMessage(
        user_id=current_user.id,
        role="user",
        content=request.message,
        needs_staff=False,
    )
    db.add(user_msg)

    assistant_msg = ChatMessage(
        user_id=current_user.id,
        role="assistant",
        content=clean_response,
        needs_staff=needs_staff,
    )
    db.add(assistant_msg)
    db.commit()

    return ChatResponse(response=clean_response, needs_staff=needs_staff)


@router.get("/chat/history")
async def get_chat_history(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get chat history for current user."""
    messages = (
        db.query(ChatMessage)
        .filter(ChatMessage.user_id == current_user.id)
        .order_by(ChatMessage.created_at.asc())
        .limit(50)
        .all()
    )
    return [
        {
            "role": msg.role,
            "content": msg.content,
            "needs_staff": msg.needs_staff,
            "created_at": msg.created_at.isoformat(),
        }
        for msg in messages
    ]


@router.delete("/chat/history")
async def clear_chat_history(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Clear chat history for current user."""
    db.query(ChatMessage).filter(ChatMessage.user_id == current_user.id).delete()
    db.commit()
    return {"message": "Istoricul conversatiei a fost sters"}
