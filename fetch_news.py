import json
import os
import urllib.request
from datetime import datetime
from email.utils import parsedate_to_datetime
import feedparser
import bs4

# Σωστά headers χωρίς συμπίεση για να μην μπλοκάρονται οι σελίδες
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
    "Accept-Language": "el-GR,el;q=0.9,en-US;q=0.8,en;q=0.7",
    "Referer": "https://www.google.com/"
}

SOURCES = [
    {"name": "Athletiko", "type": "html", "url": "https://www.athletiko.gr/panathinaikos-podosfairo", "color": "#00651", "sport": "football"},
    {"name": "Athletiko", "type": "html", "url": "https://www.athletiko.gr/panathinaikos-mpasket", "color": "#00651", "sport": "basket"},
    {"name": "pao.gr", "type": "rss", "url": "https://www.pao.gr/feed/", "color": "#00/d2c", "sport": "football"},
    {"name": "paobc.gr", "type": "rss", "url": "https://www.paobc.gr/feed/", "color": "#003d8a", "sport": "basket"},
    {"name": "NewsPao", "type": "rss", "url": "https://newspao.gr/feed/", "color": "#007d7", "sport": "football"},
    {"name": "Trifilara", "type": "rss", "url": "https://www.trifilara.gr/feed/", "color": "#2062d", "sport": "football"},
    {"name": "SDNA PAO", "type": "rss", "url": "https://www.sdna.gr/rss/223/panathinaikos", "color": "#ffcc00", "sport": "football"},
    {"name": "Gazzetta PAO", "type": "rss", "url": "https://www.gazzetta.gr/feed/tags/panathinaikos", "color": "#ff8808", "sport": "basket"},
    {"name": "Sport24 PAO", "type": "rss", "url": "https://www.sport24.gr/feed/?tag=panathinaikos", "color": "#d1e2b", "sport": "football"},
]

def fetch_rss_feed(source):
    articles = []
    try:
        req = urllib.request.Request(source["url"], headers=HEADERS)
        with urllib.request.urlopen(req, timeout=15) as response:
            content = response.read()
            feed = feedparser.parse(content)
            for entry in feed.entries[:5]:
                title = entry.get("title", "").strip()
                link = entry.get("link", "").strip()
                if not title or not link:
                    continue
                
                published = entry.get("published", entry.get("updated", ""))
                date_str = datetime.now().strftime("%d/%m %H:%M")
                if published:
                    try:
                        dt = parsedate_to_datetime(published)
                        date_str = dt.strftime("%d/%m %H:%M")
                    except Exception:
                        pass
                
                image_url = ""
                if "media_content" in entry and entry.media_content:
                    image_url = entry.media_content[0].get("url", "")
                
                articles.append({
                    "title": title,
                    "link": link,
                    "date": date_str,
                    "source": source["name"],
                    "color": source["color"],
                    "sport": source["sport"],
                    "image": image_url
                })
        print(f"Success RSS: {source['name']}")
    except Exception as e:
        print(f"Error RSS {source['name']}: {e}")
    return articles

def fetch_html_site(source):
    articles = []
    try:
        req = urllib.request.Request(source["url"], headers=HEADERS)
        with urllib.request.urlopen(req, timeout=15) as response:
            html = response.read().decode('utf-8', errors='ignore')
            soup = bs4.BeautifulSoup(html, 'html.parser')
            
            for a_tag in soup.find_all('a', href=True)[:15]:
                title = a_tag.get_text().strip()
                link = a_tag['href']
                if len(title) > 25:
                    if not link.startswith('http'):
                        base_domain = "/".join(source["url"].split("/")[:3])
                        link = base_domain + link if link.startswith('/') else base_domain + '/' + link
                    
                    articles.append({
                        "title": title,
                        "link": link,
                        "date": datetime.now().strftime("%d/%m %H:%M"),
                        "source": source["name"],
                        "color": source["color"],
                        "sport": source["sport"],
                        "image": ""
                    })
        print(f"Success HTML: {source['name']}")
    except Exception as e:
        print(f"Error HTML {source['name']}: {e}")
    return articles

def main():
    all_articles = []
    for source in SOURCES:
        if source["type"] == "rss":
            all_articles.extend(fetch_rss_feed(source))
        elif source["type"] == "html":
            all_articles.extend(fetch_html_site(source))
    
    output_path = "news.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(all_articles, f, ensure_ascii=False, indent=4)
    print(f"Saved {len(all_articles)} total articles to {output_path}")

if __name__ == "__main__":
    main()
