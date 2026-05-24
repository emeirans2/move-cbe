from app.services.scorer import score_text, scores_to_vector
from app.services.matcher import cosine_similarity, compute_demand_index

# Simulate a daily mood (e.g. war news + cold weather + payday week)
mood_brief = """
Latvijas ziņas šodien: Ukrainas karš turpinās, jauni Krievijas uzbrukumi.
Ekonomikas ziņas: inflācija samazinās, iedzīvotāji jūtas optimistiskāk.
Laikapstākļi: apmācies, +8C, lietus. Tipisks rudens rīts Rīgā.
Šodienas vārda diena: Ziedonis. Populārs vārds Latvijā.
"""

print("Step 1: Scoring today's mood brief...")
mood_scores = score_text(mood_brief)
mood_vector = scores_to_vector(mood_scores)
print(f"Mood vector: {mood_vector}")
print(f"Rationale: {mood_scores['rationale']}\n")

# Simulate two creatives
creative_1 = "Pēdējā iespēja! Tikai šodien -50% visām precēm. Nepalaid garām!"
creative_2 = "Jau 30 gadus mēs nesam Latvijas tradīcijas jūsu ģimenei. Silts un mājīgs."

print("Step 2: Scoring creatives...")
c1_scores = score_text(creative_1)
c1_vector = scores_to_vector(c1_scores)
print(f"Creative 1 (urgency): {c1_vector}")

c2_scores = score_text(creative_2)
c2_vector = scores_to_vector(c2_scores)
print(f"Creative 2 (heritage): {c2_vector}\n")

print("Step 3: Computing cosine similarity...")
sim1 = cosine_similarity(mood_vector, c1_vector)
sim2 = cosine_similarity(mood_vector, c2_vector)
print(f"Creative 1 similarity to mood: {sim1:.4f}")
print(f"Creative 2 similarity to mood: {sim2:.4f}\n")

print("Step 4: Computing demand index...")
demand = compute_demand_index(
    name_day_boost=0.1,   # Ziedonis name day
    payday_window=0.15,   # Mid-month payday
)
print(f"Demand index: {demand}\n")

winner = "Creative 1" if sim1 > sim2 else "Creative 2"
winner_sim = max(sim1, sim2)
print(f"Winner: {winner} (similarity: {winner_sim:.4f})")
print(f"Budget recommendation: +{round(min(0.15 * demand, 0.25) * 100, 1)}%")
