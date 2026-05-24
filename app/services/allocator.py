"""
Pure-percentage budget allocator.
The engine produces ALLOCATION RATIOS (budget-agnostic).
Euro conversion happens separately, using whatever budget source is plugged in.
"""

def allocate_percentages(
    matches: list,
    demand_index: float,
    threshold: float = 0.75,
    min_share_pct: float = 5.0
) -> list:
    """
    Distribute 100% across creatives by match strength.

    - Creatives >= threshold compete for the pool by how far above threshold they are.
    - demand_index sharpens the tilt toward winners on high-demand days.
    - Below-threshold creatives get only the minimum share (kept alive, starved).
    - Always sums to 100%.

    Returns list of dicts with share_pct, sorted biggest first.
    """
    if not matches:
        return []

    weights = []
    for m in matches:
        sim = m["similarity"]
        if sim >= threshold:
            strength = (sim - threshold) / (1.0 - threshold)  # 0..1
            # demand sharpens preference: higher demand = steeper curve toward winners
            weight = (0.1 + strength) ** (1.0 + (demand_index - 1.0))
        else:
            weight = 0.01
        weights.append(weight)

    total_weight = sum(weights) or 1.0
    raw_pcts = [100.0 * (w / total_weight) for w in weights]

    # Enforce minimum share floor, then rescale so it still sums to 100
    floored = [max(p, min_share_pct) for p in raw_pcts]
    floor_total = sum(floored)

    if floor_total > 100.0:
        # too many creatives forced to floor — scale the above-floor portion down
        excess = floor_total - 100.0
        above = [f - min_share_pct for f in floored]
        above_total = sum(above) or 1.0
        final_pcts = [
            round(min_share_pct + a - excess * (a / above_total), 2)
            for a in above
        ]
    else:
        leftover = 100.0 - floor_total
        final_pcts = [
            round(f + leftover * (w / total_weight), 2)
            for f, w in zip(floored, weights)
        ]

    results = []
    for m, pct in zip(matches, final_pcts):
        results.append({
            "creative_id": m["creative_id"],
            "headline": m.get("headline"),
            "similarity": m["similarity"],
            "share_pct": pct
        })

    results.sort(key=lambda x: x["share_pct"], reverse=True)
    return results


def shares_to_euros(allocations: list, total_budget_eur: float, min_change_pct: float = 10.0) -> list:
    """
    Convert percentage shares to euro amounts using the supplied budget.
    This is where the budget (manual now, Meta-fetched later) gets applied.

    min_change_pct: flag changes below this as 'skip' to protect Meta's learning phase.
    """
    n = len(allocations)
    current_share_eur = round(total_budget_eur / n, 2) if n else 0

    out = []
    for a in allocations:
        proposed = round(total_budget_eur * (a["share_pct"] / 100.0), 2)
        change = abs(proposed - current_share_eur) / current_share_eur * 100 if current_share_eur else 0
        out.append({
            **a,
            "proposed_budget_eur": proposed,
            "current_budget_eur": current_share_eur,
            "change_pct": round(change, 1),
            "apply": change >= min_change_pct
        })
    return out
