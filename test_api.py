import httpx
import json

BASE = "http://localhost:8000"

# Step 1: Create a client
print("1. Creating client...")
r = httpx.post(f"{BASE}/clients", json={
    "name": "Test Client - Latvijas Balzams",
    "meta_ad_account_id": "act_dummy_123",
    "daily_spend_cap_eur": 200.0
})
client = r.json()
print(f"   Created: {client}")
client_id = client["id"]

# Step 2: Add two creatives
print("\n2. Adding creatives (this takes ~20 seconds, scoring 3 runs each)...")
r1 = httpx.post(f"{BASE}/creatives", json={
    "client_id": client_id,
    "headline": "Pēdējā iespēja! Tikai šodien -50%",
    "primary_text": "Nepalaid garām! Šodien vien visi produkti par puscenu. Pasūti tagad!",
    "visual_description": "Bright red sale banner, countdown timer, bold discount text"
}, timeout=60)
c1 = r1.json()
print(f"   Creative 1 scores: urgency={c1['scores']['urgency']}, joy={c1['scores']['joy']}")

r2 = httpx.post(f"{BASE}/creatives", json={
    "client_id": client_id,
    "headline": "Latvijas tradīcijas jūsu galdam",
    "primary_text": "Jau 85 gadus mēs ražojam ar mīlestību. Garšo kā mājās.",
    "visual_description": "Warm wooden table, family gathering, traditional Latvian food, candles"
}, timeout=60)
c2 = r2.json()
print(f"   Creative 2 scores: nostalgia={c2['scores']['nostalgia']}, belonging={c2['scores']['belonging']}")

# Step 3: Score today's mood
print("\n3. Scoring today's mood...")
r3 = httpx.post(f"{BASE}/mood/score", json={
    "brief": """
    Latvijas ziņas šodien: Karš Ukrainā turpinās ar jauniem uzbrukumiem.
    Ekonomika: algas pieaug, inflācija samazinās - iedzīvotāji jūtas optimistiskāk.
    Laiks: apmācies, +8C, lietus. Tipisks rudens vakars Rīgā.
    Vārda diena: Ziedonis - populārs vārds, daudz svinību.
    """,
    "demand_inputs": {
        "name_day_boost": 0.1,
        "payday_window": 0.15
    }
}, timeout=30)
mood = r3.json()
print(f"   Mood vector: {mood['mood_vector']}")
print(f"   Demand index: {mood['demand_index']}")

# Step 4: Run matching
print("\n4. Running matches...")
r4 = httpx.post(f"{BASE}/matches/run", json={
    "client_id": client_id,
    "current_budgets": {
        str(c1["id"]): 50.0,
        str(c2["id"]): 50.0
    }
}, timeout=30)
matches = r4.json()
print(f"   Recommendations:")
for rec in matches["recommendations"]:
    print(f"   Creative {rec.get('creative_id')}: action={rec.get('action')}, status={rec.get('status')}, budget €{rec.get('current_budget_eur')}→€{rec.get('proposed_budget_eur')}")

# Step 5: Check pending recommendations
print("\n5. Pending recommendations:")
r5 = httpx.get(f"{BASE}/recommendations?status=pending")
recs = r5.json()
for rec in recs:
    print(f"   ID:{rec['id']} | {rec['headline']} | match={rec['emotional_match']:.3f} | €{rec['current_budget_eur']}→€{rec['proposed_budget_eur']}")

if recs:
    rec_id = recs[0]["id"]
    print(f"\n6. Approving recommendation {rec_id}...")
    r6 = httpx.post(f"{BASE}/recommendations/{rec_id}/approve")
    print(f"   {r6.json()}")

print("\n✅ Full API flow complete.")
