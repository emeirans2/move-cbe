from app.services.scorer import score_text, scores_to_vector

# Test with a simple creative
test_creative = "Pēdējā iespēja! Tikai šodien -50% visām precēm. Nepalaid garām!"
# (Translation: Last chance! Today only -50% on all products. Don't miss out!)

print("Scoring creative...")
result = score_text(test_creative)
print("\nScores:")
for key, val in result.items():
    print(f"  {key}: {val}")

print("\nVector:", scores_to_vector(result))
