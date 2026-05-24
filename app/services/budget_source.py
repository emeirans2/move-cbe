"""
Pluggable budget source.

TODAY: returns a manually-set budget stored per client per date.
LATER: swap get_budget() body to fetch from Meta Marketing API (ads_read).
Nothing downstream changes — it just calls get_budget(client_id).
"""
from sqlalchemy import text
from app.models.database import SessionLocal
from datetime import date as date_cls


def set_budget(client_id: int, amount_eur: float, on_date: str = None):
    """Store/update the manual daily budget for a client on a given date."""
    on_date = on_date or str(date_cls.today())
    db = SessionLocal()
    try:
        db.execute(text("""
            INSERT INTO daily_budget (client_id, date, budget_eur, source)
            VALUES (:client_id, :date, :amount, 'manual')
            ON CONFLICT (client_id, date)
            DO UPDATE SET budget_eur = :amount, source = 'manual'
        """), {"client_id": client_id, "date": on_date, "amount": amount_eur})
        db.commit()
    finally:
        db.close()


def get_budget(client_id: int, on_date: str = None) -> float:
    """
    Return the budget for a client on a date.

    Order of resolution:
    1. (FUTURE) fetch live from Meta API  <-- swap in here later
    2. today's manually-set budget
    3. most recent prior manual budget (default-to-yesterday)
    4. fallback default
    """
    on_date = on_date or str(date_cls.today())
    db = SessionLocal()
    try:
        # today's value
        row = db.execute(text("""
            SELECT budget_eur FROM daily_budget
            WHERE client_id = :cid AND date = :d
        """), {"cid": client_id, "d": on_date}).fetchone()
        if row:
            return float(row.budget_eur)

        # default to most recent prior value
        row = db.execute(text("""
            SELECT budget_eur FROM daily_budget
            WHERE client_id = :cid AND date < :d
            ORDER BY date DESC LIMIT 1
        """), {"cid": client_id, "d": on_date}).fetchone()
        if row:
            return float(row.budget_eur)

        return 100.0  # fallback default
    finally:
        db.close()
