import feedparser
import httpx
from datetime import datetime

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

RSS_FEEDS = [
    {"name": "LSM", "url": "https://www.lsm.lv/lv/rss", "weight": 1.0},
    {"name": "Jauns.lv", "url": "https://jauns.lv/rss", "weight": 0.9},
    {"name": "Apollo", "url": "https://www.apollo.lv/rss", "weight": 0.8},
]

def get_delfi_headlines(max_items: int = 8) -> list:
    """Scrape Delfi headlines directly from HTML since RSS is behind cookie wall."""
    try:
        r = httpx.get("https://www.delfi.lv", headers=HEADERS, timeout=10, follow_redirects=True)
        from html.parser import HTMLParser
        
        class HeadlineParser(HTMLParser):
            def __init__(self):
                super().__init__()
                self.headlines = []
                self.in_headline = False
                
            def handle_starttag(self, tag, attrs):
                attrs_dict = dict(attrs)
                classes = attrs_dict.get("class", "")
                if tag in ["h2", "h3"] and any(k in classes for k in ["headline", "title", "virsraksts"]):
                    self.in_headline = True
                    
            def handle_endtag(self, tag):
                if tag in ["h2", "h3"]:
                    self.in_headline = False
                    
            def handle_data(self, data):
                if self.in_headline and data.strip() and len(data.strip()) > 15:
                    self.headlines.append(data.strip())
        
        parser = HeadlineParser()
        parser.feed(r.text)
        
        # Fallback: extract og:title and article titles from meta
        if not parser.headlines:
            import re
            titles = re.findall(r'<title[^>]*>([^<]+)</title>', r.text)
            headlines = [t.strip() for t in titles if len(t.strip()) > 20 and 'Delfi' not in t]
            return headlines[:max_items]
            
        return parser.headlines[:max_items]
    except Exception as e:
        print(f"Delfi scrape failed: {e}")
        return []

def get_news_context(max_items_per_feed: int = 8) -> dict:
    """
    Fetch latest headlines from Latvian news sources.
    Returns headlines and a structured summary for mood scoring.
    """
    all_headlines = []
    sources_used = []

    # RSS feeds
    for feed in RSS_FEEDS:
        try:
            r = httpx.get(feed["url"], headers=HEADERS, timeout=10, follow_redirects=True)
            parsed = feedparser.parse(r.text)
            headlines = []
            for entry in parsed.entries[:max_items_per_feed]:
                title = entry.get("title", "").strip()
                if title:
                    headlines.append(title)
            if headlines:
                all_headlines.extend(headlines)
                sources_used.append(feed["name"])
        except Exception as e:
            print(f"Failed to fetch {feed['name']}: {e}")
            continue

    # Delfi HTML scrape
    delfi_headlines = get_delfi_headlines()
    if delfi_headlines:
        all_headlines.extend(delfi_headlines)
        sources_used.append("Delfi")

    if not all_headlines:
        return {
            "source": "news_rss",
            "headlines": [],
            "summary": "Ziņu avoti nav pieejami.",
            "sources_used": []
        }

    headlines_text = "\n".join(f"- {h}" for h in all_headlines[:25])
    summary = f"Šodienas galvenās ziņas Latvijā ({', '.join(sources_used)}):\n{headlines_text}"

    return {
        "source": "news_rss",
        "headlines": all_headlines[:25],
        "summary": summary,
        "sources_used": sources_used,
        "fetched_at": datetime.now().isoformat()
    }
