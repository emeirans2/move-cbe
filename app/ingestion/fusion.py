from app.ingestion.weather import get_weather_context
from app.ingestion.calendar_lv import get_calendar_context
from app.ingestion.news_rss import get_news_context

def build_daily_brief() -> dict:
    """
    Fetch all sources and fuse into one context brief for mood scoring.
    Returns the brief text and demand_inputs for the decision engine.
    """
    print("Fetching news...")
    news = get_news_context()
    
    print("Fetching weather...")
    weather = get_weather_context()
    
    print("Fetching calendar...")
    calendar = get_calendar_context()
    
    # Build the fused brief
    sections = []
    
    # News (highest weight - most important signal)
    if news["headlines"]:
        sections.append(news["summary"])
    
    # Calendar context
    if calendar["summary"]:
        sections.append(f"\nKalendāra konteksts: {calendar['summary']}")
    
    # Weather
    sections.append(f"\nLaika apstākļi: {weather['summary']}")
    
    brief = "\n".join(sections)
    
    return {
        "brief": brief,
        "demand_inputs": calendar["demand_inputs"],
        "sources": {
            "news": news["sources_used"],
            "weather": weather.get("date"),
            "calendar": calendar.get("date")
        },
        "raw": {
            "news": news,
            "weather": weather,
            "calendar": calendar
        }
    }
