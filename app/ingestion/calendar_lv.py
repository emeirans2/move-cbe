from datetime import datetime, timedelta

# Latvian name days - most popular ones with boost weights
NAME_DAYS = {
    "01-01": (["Lienīte", "Liene"], 0.05),
    "01-06": (["Spodra", "Sparīte"], 0.05),
    "02-14": (["Valentīns", "Valentīna"], 0.2),
    "03-08": (["Sarmīte", "Sarmis"], 0.1),
    "03-25": (["Marta", "Māra"], 0.15),
    "04-23": (["Jurģis", "Jūlija"], 0.1),
    "05-01": (["Ziedonis", "Ziedīte"], 0.1),
    "05-04": (["Dita", "Anita"], 0.1),
    "06-15": (["Sigita", "Sigvards"], 0.05),
    "06-23": (["Līga", "Jānis"], 0.4),   # Jāņi eve - biggest
    "06-24": (["Jānis", "Jānīts"], 0.35), # Jāņi
    "08-25": (["Ludvigs", "Ludvīgs"], 0.05),
    "09-08": (["Marija", "Māris"], 0.15),
    "10-13": (["Edvards", "Edvīns"], 0.1),
    "11-11": (["Mārtiņš", "Marta"], 0.25), # Mārtiņi - big
    "11-18": (["Atis", "Baiba"], 0.3),     # Latvia independence day
    "12-24": (["Ādams", "Ieva"], 0.35),    # Christmas Eve
    "12-25": (["Kristīne", "Kristaps"], 0.3),
    "12-26": (["Stefānija", "Staņislavs"], 0.2),
    "12-31": (["Silvestrs", "Silva"], 0.2),
}

# Public holidays with demand boost
PUBLIC_HOLIDAYS = {
    "01-01": ("Jaunais gads", 0.2),
    "04-18": ("Lieldienas", 0.25),  # approximate, varies
    "04-19": ("Otrās Lieldienas", 0.2),
    "05-01": ("Darba svētki", 0.15),
    "05-04": ("Latvijas Republikas atjaunošanas diena", 0.3),
    "06-23": ("Līgo svētki", 0.4),
    "06-24": ("Jāņi", 0.4),
    "11-18": ("Latvijas proklamēšanas diena", 0.35),
    "12-24": ("Ziemassvētku vakars", 0.4),
    "12-25": ("Ziemassvētki", 0.35),
    "12-26": ("Otrie Ziemassvētki", 0.25),
    "12-31": ("Vecgada vakars", 0.25),
}

def get_calendar_context(target_date: datetime = None) -> dict:
    """
    Get calendar context for a given date (defaults to tomorrow).
    Returns name day info, holiday info, and demand boost.
    """
    if target_date is None:
        target_date = datetime.now() + timedelta(days=1)
    
    date_key = target_date.strftime("%m-%d")
    day_of_week = target_date.weekday()  # 0=Monday, 6=Sunday
    
    # Name day
    name_day_boost = 0.0
    name_day_text = ""
    if date_key in NAME_DAYS:
        names, boost = NAME_DAYS[date_key]
        name_day_boost = boost
        name_day_text = f"Vārda diena: {', '.join(names)}."
    
    # Holiday
    holiday_boost = 0.0
    holiday_text = ""
    if date_key in PUBLIC_HOLIDAYS:
        holiday_name, boost = PUBLIC_HOLIDAYS[date_key]
        holiday_boost = boost
        holiday_text = f"Svētku diena: {holiday_name}."
    
    # Check proximity to upcoming holidays (within 3 days)
    proximity_boost = 0.0
    proximity_text = ""
    for i in range(1, 4):
        future_date = target_date + timedelta(days=i)
        future_key = future_date.strftime("%m-%d")
        if future_key in PUBLIC_HOLIDAYS:
            holiday_name, boost = PUBLIC_HOLIDAYS[future_key]
            proximity_boost = max(proximity_boost, boost * (0.5 - i * 0.1))
            proximity_text = f"Tuvojas {holiday_name} (pēc {i} dienām)."
            break
    
    # Weekend boost
    weekend_boost = 0.1 if day_of_week >= 5 else 0.0
    weekend_text = "Nedēļas nogale." if day_of_week >= 5 else ""
    
    # Payday window (25th-5th of month = high spend)
    day_of_month = target_date.day
    payday_boost = 0.15 if (day_of_month >= 25 or day_of_month <= 5) else 0.0
    payday_text = "Algas periods (augstāka pirktspēja)." if payday_boost > 0 else ""
    
    # Build summary
    parts = [p for p in [name_day_text, holiday_text, proximity_text, 
                          weekend_text, payday_text] if p]
    summary = " ".join(parts) if parts else "Parasta darba diena, nav īpašu notikumu."
    
    total_boost = min(name_day_boost + holiday_boost + proximity_boost + 
                      weekend_boost + payday_boost, 0.5)
    
    return {
        "source": "calendar_lv",
        "date": target_date.strftime("%Y-%m-%d"),
        "name_day": name_day_text,
        "holiday": holiday_text,
        "proximity": proximity_text,
        "payday_window": payday_boost > 0,
        "weekend": day_of_week >= 5,
        "demand_boost": round(total_boost, 3),
        "summary": summary,
        "demand_inputs": {
            "name_day_boost": name_day_boost,
            "holiday_proximity": max(holiday_boost, proximity_boost),
            "payday_window": payday_boost,
        }
    }
