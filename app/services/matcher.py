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
