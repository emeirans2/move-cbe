import json
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
from datetime import date
from sqlalchemy import text
from app.models.database import SessionLocal
from app.services.scorer import score_text, score_with_average, scores_to_vector
from app.services.matcher import get_matches_for_client, compute_demand_index
from app.services.decision import make_recommendation

router = APIRouter()

class ClientCreate(BaseModel):
    name: str
    meta_ad_account_id: Optional[str] = None
    daily_spend_cap_eur: float = 100.0

class CreativeCreate(BaseModel):
    client_id: int
    meta_ad_id: Optional[str] = None
    primary_text: str
    headline: Optional[str] = None
    visual_description: Optional[str] = None

class MoodRequest(BaseModel):
    brief: str
    geo: str = "LV"
    date: Optional[str] = None
    demand_inputs: Optional[dict] = {}

class MatchRequest(BaseModel):
    client_id: int
    date: Optional[str] = None
    current_budgets: Optional[dict] = {}

@router.post("/clients")
def create_client(data: ClientCreate):
    db = SessionLocal()
    try:
        result = db.execute(text("""
            INSERT INTO clients (name, meta_ad_account_id, daily_spend_cap_eur)
            VALUES (:name, :meta_ad_account_id, :cap)
            RETURNING id, name
        """), {"name": data.name, "meta_ad_account_id": data.meta_ad_account_id, "cap": data.daily_spend_cap_eur})
        row = result.fetchone()
        db.commit()
        return {"id": row.id, "name": row.name, "status": "created"}
    finally:
        db.close()

@router.get("/clients")
def list_clients():
    db = SessionLocal()
    try:
        result = db.execute(text("SELECT id, name, meta_ad_account_id, daily_spend_cap_eur, geo FROM clients"))
        rows = result.fetchall()
        return [{"id": r.id, "name": r.name, "meta_ad_account_id": r.meta_ad_account_id,
                 "daily_spend_cap_eur": r.daily_spend_cap_eur, "geo": r.geo} for r in rows]
    finally:
        db.close()

@router.post("/creatives")
def add_creative(data: CreativeCreate):
    text_to_score = f"{data.headline or ''}\n{data.primary_text}\n{data.visual_description or ''}"
    scores = score_with_average(text_to_score, runs=3)
    vector = scores_to_vector(scores)
    vector_str = "[" + ",".join(str(v) for v in vector) + "]"
    db = SessionLocal()
    try:
        result = db.execute(text("""
            INSERT INTO creatives
            (client_id, meta_ad_id, primary_text, headline, visual_description, raw_scores, scored_at)
            VALUES (:client_id, :meta_ad_id, :primary_text, :headline, :visual_description,
                    :raw_scores, NOW())
            RETURNING id
        """), {
            "client_id": data.client_id,
            "meta_ad_id": data.meta_ad_id,
            "primary_text": data.primary_text,
            "headline": data.headline,
            "visual_description": data.visual_description,
            "vector": vector_str,
            "raw_scores": json.dumps(scores)
        })
        creative_id = result.fetchone().id
        db.execute(text("UPDATE creatives SET vector = :vec WHERE id = :id"),
                   {"vec": vector_str, "id": creative_id})
        db.commit()
        return {"id": creative_id, "scores": scores, "vector": vector}
    finally:
        db.close()

@router.get("/creatives/{client_id}")
def list_creatives(client_id: int):
    db = SessionLocal()
    try:
        result = db.execute(text("""
            SELECT id, meta_ad_id, headline, primary_text, status, scored_at
            FROM creatives WHERE client_id = :client_id
        """), {"client_id": client_id})
        rows = result.fetchall()
        return [{"id": r.id, "meta_ad_id": r.meta_ad_id, "headline": r.headline,
                 "primary_text": r.primary_text[:80], "status": r.status} for r in rows]
    finally:
        db.close()

@router.post("/mood/score")
def score_mood(data: MoodRequest):
    today = data.date or str(date.today())
    scores = score_text(data.brief)
    vector = scores_to_vector(scores)
    vector_str = "[" + ",".join(str(v) for v in vector) + "]"
    demand = compute_demand_index(**data.demand_inputs)
    db = SessionLocal()
    try:
        db.execute(text("""
            INSERT INTO daily_context (date, geo, brief, mood_vector, demand_index, raw)
            VALUES (:date, :geo, :brief, :vector, :demand, :raw)
            ON CONFLICT DO NOTHING
        """), {
            "date": today,
            "geo": data.geo,
            "brief": data.brief,
            "vector": vector_str,
            "demand": demand,
            "raw": json.dumps(scores)
        })
        db.commit()
        return {"date": today, "mood_vector": vector, "demand_index": demand, "scores": scores}
    finally:
        db.close()

@router.post("/matches/run")
def run_matches(data: MatchRequest):
    today = data.date or str(date.today())
    db = SessionLocal()
    try:
        context = db.execute(text("""
            SELECT mood_vector::text, demand_index
            FROM daily_context
            WHERE date = :date AND geo = 'LV'
            ORDER BY created_at DESC LIMIT 1
        """), {"date": today}).fetchone()
        if not context:
            raise HTTPException(status_code=404, detail="No mood scored for today. Run /mood/score first.")
        vec_str = context.mood_vector.strip('[]')
        mood_vector = [float(x) for x in vec_str.split(',')]
        demand_index = context.demand_index
    finally:
        db.close()
    matches = get_matches_for_client(data.client_id, mood_vector, today)
    if not matches:
        return {"message": "No scored creatives found", "matches": []}
    recommendations = []
    for match in matches:
        current_budget = data.current_budgets.get(str(match["creative_id"]), 50.0)
        rec = make_recommendation(
            match=match, client_id=data.client_id, demand_index=demand_index,
            current_budget_eur=current_budget, date=today, mood_vector=mood_vector
        )
        recommendations.append(rec)
    return {"date": today, "client_id": data.client_id, "mood_vector": mood_vector,
            "demand_index": demand_index, "recommendations": recommendations}

@router.get("/recommendations")
def get_recommendations(status: str = "pending"):
    db = SessionLocal()
    try:
        result = db.execute(text("""
            SELECT r.id, r.status, r.action_type, r.current_budget_eur,
                   r.proposed_budget_eur, r.guardrail_notes,
                   m.emotional_match, m.demand_index, m.client_id, m.creative_id, m.date,
                   c.headline, c.primary_text
            FROM recommendations r
            JOIN matches m ON r.match_id = m.id
            JOIN creatives c ON m.creative_id = c.id
            WHERE r.status = :status
            ORDER BY m.emotional_match DESC
        """), {"status": status})
        rows = result.fetchall()
        return [{"id": r.id, "status": r.status, "action_type": r.action_type,
                 "current_budget_eur": r.current_budget_eur, "proposed_budget_eur": r.proposed_budget_eur,
                 "emotional_match": r.emotional_match, "demand_index": r.demand_index,
                 "client_id": r.client_id, "creative_id": r.creative_id, "date": str(r.date),
                 "headline": r.headline, "primary_text": r.primary_text[:80] if r.primary_text else ""
                 } for r in rows]
    finally:
        db.close()

@router.post("/recommendations/{rec_id}/approve")
def approve_recommendation(rec_id: int):
    db = SessionLocal()
    try:
        result = db.execute(text("""
            UPDATE recommendations
            SET status = 'approved', decided_at = NOW(), decided_by = 'dashboard_user'
            WHERE id = :id AND status = 'pending'
            RETURNING id, proposed_budget_eur
        """), {"id": rec_id})
        row = result.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Not found or already decided")
        db.execute(text("""
            INSERT INTO audit_log (event_type, entity_type, entity_id, context)
            VALUES ('recommendation_approved', 'recommendation', :id, :ctx)
        """), {"id": rec_id, "ctx": json.dumps({"proposed_budget_eur": row.proposed_budget_eur})})
        db.commit()
        return {"status": "approved", "recommendation_id": rec_id,
                "proposed_budget_eur": row.proposed_budget_eur,
                "note": "MVP mode: logged. Meta SDK execution in Phase 2."}
    finally:
        db.close()

@router.post("/recommendations/{rec_id}/reject")
def reject_recommendation(rec_id: int):
    db = SessionLocal()
    try:
        db.execute(text("""
            UPDATE recommendations
            SET status = 'rejected', decided_at = NOW(), decided_by = 'dashboard_user'
            WHERE id = :id AND status = 'pending'
        """), {"id": rec_id})
        db.execute(text("""
            INSERT INTO audit_log (event_type, entity_type, entity_id, context)
            VALUES ('recommendation_rejected', 'recommendation', :id, '{}')
        """), {"id": rec_id})
        db.commit()
        return {"status": "rejected", "recommendation_id": rec_id}
    finally:
        db.close()

@router.get("/audit")
def get_audit(limit: int = 50):
    db = SessionLocal()
    try:
        result = db.execute(text("""
            SELECT id, ts, event_type, entity_type, entity_id, context
            FROM audit_log ORDER BY ts DESC LIMIT :limit
        """), {"limit": limit})
        rows = result.fetchall()
        return [{"id": r.id, "ts": str(r.ts), "event_type": r.event_type,
                 "entity_type": r.entity_type, "entity_id": r.entity_id,
                 "context": r.context} for r in rows]
    finally:
        db.close()

@router.post("/mood/auto")
def auto_score_mood(client_id: int = 1):
    """Fetch all sources, build brief, score mood, run matches. Full daily loop."""
    from app.ingestion.fusion import build_daily_brief
    from datetime import date

    today = str(date.today())

    # Build brief from real sources
    briefdata = build_daily_brief()
    brief = briefdata["brief"]
    demand_inputs = briefdata["demand_inputs"]

    # Score mood
    scores = score_text(brief)
    vector = scores_to_vector(scores)
    vector_str = "[" + ",".join(str(v) for v in vector) + "]"
    demand = compute_demand_index(**demand_inputs)

    db = SessionLocal()
    try:
        db.execute(text("""
            INSERT INTO daily_context (date, geo, brief, mood_vector, demand_index, raw)
            VALUES (:date, 'LV', :brief, :vector, :demand, CAST(:raw AS jsonb))
            ON CONFLICT DO NOTHING
        """), {
            "date": today,
            "brief": brief,
            "vector": vector_str,
            "demand": demand,
            "raw": json.dumps(scores)
        })
        db.commit()
    finally:
        db.close()

    # Run matches for all clients
    clients_resp = SessionLocal()
    try:
        result = clients_resp.execute(text("SELECT id FROM clients"))
        client_ids = [r.id for r in result.fetchall()]
    finally:
        clients_resp.close()

    all_recommendations = []
    for cid in client_ids:
        matches = get_matches_for_client(cid, vector, today)
        for match in matches:
            rec = make_recommendation(
                match=match, client_id=cid, demand_index=demand,
                current_budget_eur=50.0, date=today, mood_vector=vector
            )
            all_recommendations.append(rec)

    return {
        "date": today,
        "mood_vector": vector,
        "demand_index": demand,
        "scores": scores,
        "sources": briefdata["sources"],
        "recommendations_generated": len(all_recommendations),
        "brief_preview": brief[:300]
    }


class AllocateRequest(BaseModel):
    client_id: int
    total_budget_eur: float = 100.0
    date: Optional[str] = None

@router.post("/allocate")
def allocate_budget(data: AllocateRequest):
    """Distribute a fixed budget pool across a client's creatives by today's mood match."""
    from app.services.matcher import allocate_budget_pool
    from datetime import date as date_cls

    today = data.date or str(date_cls.today())

    db = SessionLocal()
    try:
        context = db.execute(text("""
            SELECT mood_vector::text, demand_index
            FROM daily_context
            WHERE date = :date AND geo = 'LV'
            ORDER BY created_at DESC LIMIT 1
        """), {"date": today}).fetchone()
        if not context:
            raise HTTPException(status_code=404, detail="No mood scored for today. Run the daily loop first.")
        vec_str = context.mood_vector.strip('[]')
        mood_vector = [float(x) for x in vec_str.split(',')]
        demand_index = context.demand_index
    finally:
        db.close()

    matches = get_matches_for_client(data.client_id, mood_vector, today)
    if not matches:
        return {"message": "No scored creatives", "allocations": []}

    allocations = allocate_budget_pool(
        matches=matches,
        total_budget_eur=data.total_budget_eur,
        demand_index=demand_index
    )

    return {
        "date": today,
        "client_id": data.client_id,
        "total_budget_eur": data.total_budget_eur,
        "demand_index": demand_index,
        "mood_vector": mood_vector,
        "allocations": allocations,
        "total_allocated": round(sum(a["proposed_budget_eur"] for a in allocations), 2)
    }


class BudgetSet(BaseModel):
    client_id: int
    budget_eur: float
    date: Optional[str] = None

@router.post("/budget/set")
def set_client_budget(data: BudgetSet):
    """Set/update the manual daily budget for a client."""
    from app.services.budget_source import set_budget
    set_budget(data.client_id, data.budget_eur, data.date)
    return {"status": "ok", "client_id": data.client_id, "budget_eur": data.budget_eur}

@router.get("/budget/{client_id}")
def get_client_budget(client_id: int):
    """Get the current budget for a client (manual now, Meta-fetched later)."""
    from app.services.budget_source import get_budget
    return {"client_id": client_id, "budget_eur": get_budget(client_id)}

@router.post("/allocate/v2")
def allocate_v2(data: AllocateRequest):
    """
    Produce percentage allocation from today's mood, then convert to euros
    using the pluggable budget source.
    """
    from app.services.allocator import allocate_percentages, shares_to_euros
    from app.services.budget_source import get_budget
    from datetime import date as date_cls

    today = data.date or str(date_cls.today())

    db = SessionLocal()
    try:
        context = db.execute(text("""
            SELECT mood_vector::text, demand_index
            FROM daily_context
            WHERE date = :date AND geo = 'LV'
            ORDER BY created_at DESC LIMIT 1
        """), {"date": today}).fetchone()
        if not context:
            raise HTTPException(status_code=404, detail="No mood scored for today. Run the daily loop first.")
        vec_str = context.mood_vector.strip('[]')
        mood_vector = [float(x) for x in vec_str.split(',')]
        demand_index = context.demand_index
    finally:
        db.close()

    matches = get_matches_for_client(data.client_id, mood_vector, today)
    if not matches:
        return {"message": "No scored creatives", "allocations": []}

    # Step 1: pure percentages (budget-agnostic)
    pct_allocations = allocate_percentages(matches, demand_index)

    # Step 2: get budget from source (manual now, Meta later), convert to euros
    budget = get_budget(data.client_id, today)
    euro_allocations = shares_to_euros(pct_allocations, budget)

    return {
        "date": today,
        "client_id": data.client_id,
        "budget_eur": budget,
        "demand_index": demand_index,
        "allocations": euro_allocations,
        "total_allocated": round(sum(a["proposed_budget_eur"] for a in euro_allocations), 2)
    }
