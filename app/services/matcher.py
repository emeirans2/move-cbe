import numpy as np
from sqlalchemy import text
from app.models.database import SessionLocal

def cosine_similarity(vec_a: list, vec_b: list) -> float:
    """Compute cosine similarity between two 10-dim vectors."""
    a = np.array(vec_a)
    b = np.array(vec_b)
    norm_a = np.linalg.norm(a)
    norm_b = np.linalg.norm(b)
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return float(np.dot(a, b) / (norm_a * norm_b))

def get_matches_for_client(client_id: int, mood_vector: list, date: str) -> list:
    """
    Compare mood vector against all active creatives for a client.
    Returns ranked list of matches with similarity scores.
    """
    db = SessionLocal()
    try:
        result = db.execute(text("""
            SELECT 
                id,
                meta_ad_id,
                headline,
                primary_text,
                vector::text
            FROM creatives
            WHERE client_id = :client_id
            AND status = 'active'
            AND vector IS NOT NULL
        """), {"client_id": client_id})
        
        rows = result.fetchall()
        matches = []
        
        for row in rows:
            # Parse the pgvector string back to a list
            vec_str = row.vector.strip('[]')
            creative_vector = [float(x) for x in vec_str.split(',')]
            
            similarity = cosine_similarity(mood_vector, creative_vector)
            
            matches.append({
                "creative_id": row.id,
                "meta_ad_id": row.meta_ad_id,
                "headline": row.headline,
                "primary_text": row.primary_text[:100] if row.primary_text else "",
                "similarity": round(similarity, 4),
                "creative_vector": creative_vector
            })
        
        # Sort by similarity descending
        matches.sort(key=lambda x: x["similarity"], reverse=True)
        return matches
    finally:
        db.close()

def compute_demand_index(
    holiday_proximity: float = 0.0,
    name_day_boost: float = 0.0,
    payday_window: float = 0.0,
    sports_event: float = 0.0,
    firstparty_lift: float = 0.0
) -> float:
    """
    Deterministic demand index. Returns a multiplier in [0.5, 1.5].
    Each input is a boost value; defaults give index of 1.0 (neutral).
    """
    raw = (1.0 
           + holiday_proximity 
           + name_day_boost 
           + payday_window 
           + sports_event 
           + firstparty_lift)
    return round(max(0.5, min(1.5, raw)), 3)


def allocate_budget_pool(
    matches: list,
    total_budget_eur: float,
    demand_index: float,
    threshold: float = 0.75,
    min_budget_eur: float = 5.0,
    min_change_pct: float = 0.10
) -> list:
    """
    Distribute a FIXED budget pool across campaigns by match strength.

    - Only creatives matching >= threshold get a meaningful share; below-threshold
      creatives get the minimum floor (kept alive but starved).
    - Weight = (match strength above threshold) — stronger match = bigger slice.
    - demand_index scales how aggressively the pool tilts toward winners.
    - Every allocation respects min_budget_eur (Meta learning-phase floor).
    - Allocations always sum to total_budget_eur.

    Returns list of dicts with current vs proposed budget and whether the
    change is big enough to be worth applying (min_change_pct).
    """
    if not matches:
        return []

    n = len(matches)

    # Each creative's current equal share (baseline for "change" comparison)
    current_share = round(total_budget_eur / n, 2)

    # Compute raw weights
    weights = []
    for m in matches:
        sim = m["similarity"]
        if sim >= threshold:
            # strength above threshold, 0..1
            strength = (sim - threshold) / (1.0 - threshold)
            # demand tilts the curve: higher demand = sharper preference for winners
            weight = (0.1 + strength) ** (1.0 + (demand_index - 1.0))
        else:
            # below threshold: tiny weight, will land near the floor
            weight = 0.01
        weights.append(weight)

    total_weight = sum(weights)

    # First pass: proportional allocation
    raw_allocations = [total_budget_eur * (w / total_weight) for w in weights]

    # Enforce minimum floor, then redistribute the remainder proportionally
    allocations = [max(a, min_budget_eur) for a in raw_allocations]
    floor_total = sum(allocations)

    # If flooring pushed us over budget, scale the above-floor portion back down
    if floor_total > total_budget_eur:
        # scale only the parts above the floor
        excess = floor_total - total_budget_eur
        above_floor = [a - min_budget_eur for a in allocations]
        above_total = sum(above_floor) or 1
        allocations = [
            round(min_budget_eur + af - excess * (af / above_total), 2)
            for af in above_floor
        ]
    else:
        # distribute leftover proportionally by weight
        leftover = total_budget_eur - floor_total
        allocations = [
            round(a + leftover * (w / total_weight), 2)
            for a, w in zip(allocations, weights)
        ]

    results = []
    for m, proposed in zip(matches, allocations):
        change_pct = abs(proposed - current_share) / current_share if current_share else 0
        results.append({
            "creative_id": m["creative_id"],
            "headline": m.get("headline"),
            "similarity": m["similarity"],
            "current_budget_eur": current_share,
            "proposed_budget_eur": proposed,
            "change_pct": round(change_pct * 100, 1),
            "apply": change_pct >= min_change_pct,  # skip tiny changes (learning phase)
            "share_pct": round(proposed / total_budget_eur * 100, 1)
        })

    # Sort biggest allocation first
    results.sort(key=lambda x: x["proposed_budget_eur"], reverse=True)
    return results
