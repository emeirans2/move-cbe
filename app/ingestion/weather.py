import httpx
from datetime import datetime, timedelta

def get_weather_context(lat: float = 56.9496, lon: float = 24.1052) -> dict:
    """
    Fetch tomorrow's weather forecast for Riga (default).
    Returns a dict with numeric data and a natural language summary.
    """
    tomorrow = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
    
    url = "https://api.open-meteo.com/v1/forecast"
    params = {
        "latitude": lat,
        "longitude": lon,
        "daily": "temperature_2m_max,temperature_2m_min,precipitation_sum,weathercode,sunshine_duration",
        "timezone": "Europe/Riga",
        "start_date": tomorrow,
        "end_date": tomorrow
    }
    
    resp = httpx.get(url, params=params, timeout=10)
    data = resp.json()
    
    d = data["daily"]
    temp_max = d["temperature_2m_max"][0]
    temp_min = d["temperature_2m_min"][0]
    precip = d["precipitation_sum"][0]
    sunshine = d["sunshine_duration"][0] / 3600  # convert to hours
    wcode = d["weathercode"][0]
    
    # Map weather code to description
    weather_desc = _weather_code_to_text(wcode)
    
    # Build natural language summary
    summary = f"Rīgas laika prognoze rītdienai: {weather_desc}. "
    summary += f"Temperatūra {temp_min}°C līdz {temp_max}°C. "
    
    if precip > 5:
        summary += f"Gaidāms stiprs nokrišņu daudzums ({precip}mm). "
    elif precip > 1:
        summary += f"Iespējams neliels lietus ({precip}mm). "
    else:
        summary += "Nokrišņi nav gaidāmi. "
    
    if sunshine < 1:
        summary += "Mākoņains, gandrīz bez saules. Tumša diena."
    elif sunshine < 3:
        summary += f"Maz saules ({sunshine:.1f}h)."
    else:
        summary += f"Salīdzinoši saulaina diena ({sunshine:.1f}h saules)."
    
    return {
        "source": "open_meteo",
        "date": tomorrow,
        "temp_max": temp_max,
        "temp_min": temp_min,
        "precipitation_mm": precip,
        "sunshine_hours": round(sunshine, 1),
        "weather_code": wcode,
        "summary": summary
    }

def _weather_code_to_text(code: int) -> str:
    mapping = {
        0: "skaidrs", 1: "galvenokārt skaidrs", 2: "daļēji mākoņains",
        3: "apmācies", 45: "migla", 48: "sarma migla",
        51: "neliels miglainis", 53: "mērens miglainis", 55: "stiprs miglainis",
        61: "neliels lietus", 63: "mērens lietus", 65: "stiprs lietus",
        71: "neliels sniegs", 73: "mērens sniegs", 75: "stiprs sniegs",
        80: "neliels lietus gāzes", 81: "mērenas lietus gāzes", 82: "stipras lietus gāzes",
        85: "nelielas sniegputeņa gāzes", 86: "stipras sniegputeņa gāzes",
        95: "pērkona negaiss", 96: "pērkona negaiss ar krusu"
    }
    return mapping.get(code, f"mainīgi laika apstākļi (kods {code})")
