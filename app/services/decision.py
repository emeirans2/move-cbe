from datetime import datetime
from sqlalchemy import text
from app.models.database import SessionLocal

SIMILARITY_THRESHOLD = 0.75  # Start lower for testing, raise to 0.85 in production
BASE_STEP = 0.15              # 15% budget increase
MAX_STEP = 0.25               # Hard cap at 25% per day
COOLDOWN_DAYS = 2             # Don't bump same creative twice in 2 days

def check_guardrails(creative_id: int, client_id: int, proposed_eur: float) -> tuple[bool, str]:
    """
    Returns (passes: bool, reason: str).
    Checks cooldown and spend ceiling.
    """
    db = SessionLocal()
    try:
        # Check cooldown
        result = db.execute(text("""
            SELECT COUNT(*) as cnt FROM recommendations r
            JOIN matches m ON r.match_id = m.id
            WHERE m.creative_id = :creative_id
            AND r.status IN ('approved', 'executed')
            AND r.decided_at > NOW() - INTERVAL ':days days'
        """), {"creative_id": creative_id, "days": COOLDOWN_DAYS})
        
        row = result.fetchone()
        if row and row.cnt > 0:
            return False, f"cooldown: creative bumped in last {COOLDOWN_DAYS} days"

        # Check client daily spend ceiling
        client = db.execute(text("""
            SELECT daily_spend_cap_eur FROM clients WHERE id = :id
        """), {"id": client_id}).fetchone()
        
        if client and proposed_eur > client.daily_spend_cap_eur:
            return False, f"spend_ceiling: proposed €{proposed_eur} exceeds cap €{client.daily_spend_cap_eur}"

        return True, "ok"
    finally:
        db.close()

def make_recommendation(
    match: dict,
    client_id: int,
    demand_index: float,
    current_budget_eur: float,
    date: str,
    mood_vector: list,
    mvp_mode: bool = True  # True = recommend only, False = auto-execute
) -> dict:
    """
    Given a match, decide whether to recommend a budget increase.
    Writes recommendation to DB. Returns decision dict.
    """
    similarity = match["similarity"]
    
    if similarity < SIMILARITY_THRESHOLD:
        return {
            "action": "hold",
            "reason": f"below_threshold: {similarity} < {SIMILARITY_THRESHOLD}",
            "creative_id": match["creative_id"]
        }
    
    # Calculate budget delta — scales with BOTH match strength and demand
    # match_strength: how far above threshold (0 at threshold, 1 at perfect match)
    match_strength = (similarity - SIMILARITY_THRESHOLD) / (1.0 - SIMILARITY_THRESHOLD)
    match_strength = max(0.0, min(1.0, match_strength))
    # base step is modulated by match strength (0.5x to 1.5x) and demand
    match_multiplier = 0.5 + match_strength  # ranges 0.5–1.5
    delta = min(BASE_STEP * match_multiplier * demand_index, MAX_STEP)
    proposed = round(current_budget_eur * (1 + delta), 2)
    
    # Check guardrails
    passes, guardrail_note = check_guardrails(match["creative_id"], client_id, proposed)
    
    db = SessionLocal()
    try:
        # Store match
        match_result = db.execute(text("""
            INSERT INTO matches (date, client_id, creative_id, emotional_match, demand_index)
            VALUES (:date, :client_id, :creative_id, :emotional_match, :demand_index)
            RETURNING id
        """), {
            "date": date,
            "client_id": client_id,
            "creative_id": match["creative_id"],
            "emotional_match": similarity,
            "demand_index": demand_index
        })
        match_id = match_result.fetchone().id

        status = "pending" if passes else "suppressed"
        
        # Store recommendation
        db.execute(text("""
            INSERT INTO recommendations 
            (match_id, action_type, current_budget_eur, proposed_budget_eur, status, guardrail_notes)
            VALUES (:match_id, 'increase_budget', :current, :proposed, :status, :notes)
        """), {
            "match_id": match_id,
            "current": current_budget_eur,
            "proposed": proposed,
            "status": status,
            "notes": guardrail_note
        })

        # Audit log
        db.execute(text("""
            INSERT INTO audit_log (event_type, entity_type, entity_id, context)
            VALUES ('recommendation_created', 'creative', :creative_id, CAST(:context AS jsonb))
        """), {
            "creative_id": match["creative_id"],
            "context": f'{{"similarity": {similarity}, "demand_index": {demand_index}, "delta_pct": {round(delta*100,1)}, "status": "{status}"}}'
        })
        
        db.commit()

        return {
            "action": "increase_budget" if passes else "suppressed",
            "creative_id": match["creative_id"],
            "similarity": similarity,
            "demand_index": demand_index,
            "current_budget_eur": current_budget_eur,
            "proposed_budget_eur": proposed,
            "delta_pct": round(delta * 100, 1),
            "status": status,
            "reason": guardrail_note
        }
    finally:
        db.close()
