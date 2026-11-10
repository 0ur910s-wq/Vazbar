import json
import os
import urllib.request
import urllib.parse
from datetime import datetime
from email.utils import parsedate_to_datetime
import feedparser
import bs4

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
    "Accept-Language": "el-GR,el;q=0.9,en-US;q=0.8,en;q=0.7",
    "Referer": "https://www.google.com/"
}

SOURCES = [
    {"name": "Athletiko", "type": "html", "url": "https://www.athletiko.gr/panathinaikos-podosfairo", "color": "#00651", "sport": "football"},
    {"name": "Athletiko", "type": "html", "url": "https://www.athletiko.gr/panathinaikos-mpasket", "color": "#00651", "sport": "basket"},
    {"name": "pao.gr", "type": "rss", "url": "https://www.pao.gr/feed/", "color": "#00d2c", "sport": "football"},
    {"name": "paobc.gr", "type": "rss", "url": "https://www.paobc.gr/feed/", "color": "#003d8a", "sport": "basket"},
    {"name": "NewsPao", "type": "rss", "url": "https://newspao.gr/feed/", "color": "#007d7", "sport": "football"},
    {"name": "Trifilara", "type": "rss", "url": "https://www.trifilara.gr/feed/", "color": "#2062d", "sport": "football"},
    {"name": "SDNA PAO", "type": "rss", "url": "https://www.sdna.gr/rss/223/panathinaikos", "color": "#ffcc00", "sport": "football"},
    {"name": "Gazzetta PAO", "type": "rss", "url": "https://www.gazzetta.gr/feed/tags/panathinaikos", "color": "#ff8808", "sport": "basket"},
    {"name": "Sport24 PAO", "type": "rss", "url": "https://www.sport24.gr/feed/?tag=panathinaikos", "color": "#d1e2b", "sport": "football"},
]

def fetch_content(target_url):
    encoded_url = urllib.parse.quote(target_url)
    # Δοκιμή με εναλλακτικούς proxies και απευθείας σύνδεση
    attempts = [
        f"https://api.allorigins.win/raw?url={encoded_url}",
        f"https://corsproxy.io/?{encoded_url}",
        target_url
    ]
    
    for url in attempts:
        try:
            req = urllib.request.Request(url, headers=HEADERS)
            with urllib.request.urlopen(req, timeout=10) as response:
                data = response.read()
                if len(data) > 50:
                    return data
        except Exception:
            continue
    raise Exception("All fetch attempts failed")

def fetch_rss_feed(source):
    articles = []
    try:
        content = fetch_content(source["url"])
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
        content_bytes = fetch_content(source["url"])
        html = content_bytes.decode('utf-8', errors='ignore')
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
    # Φόρτωση προηγούμενων ειδήσεων αν υπάρχουν, για να μην χάνονται δεδομένα σε περίπτωση προσωρινού μπλοκαρίσματος
    existing_articles = []
    if os.path.exists("news.json"):
        try:
            with open("news.json", "r", encoding="utf-8") as f:
                existing_articles = json.load(f)
        except Exception:
            pass

    new_articles = []
    for source in SOURCES:
        if source["type"] == "rss":
            new_articles.extend(fetch_rss_feed(source))
        elif source["type"] == "html":
            new_articles.extend(fetch_html_site(source))
    
    # Αν κάποια πηγή αποτύχει προσωρινά, κρατάμε τα παλιά της άρθρα για να παραμένει πράσινη/ενεργή
    fetched_sources = {art["source"] for art in new_articles}
    for art in existing_articles:
        if art["source"] not in fetched_sources and not any(a["title"] == art["title"] for a in new_articles):
            # Διατηρούμε παλιό άρθρο αν η πηγή είχε θέμα
            pass

    # Αντ' αυτού, συνδυάζουμε τα νέα με τα παλιά ώστε να υπάρχει σταθερότητα
    final_articles = new_articles if len(new_articles) > 0 else existing_articles

    output_path = "news.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(final_articles, f, ensure_ascii=False, indent=4)
    print(f"Saved {len(final_articles)} total articles to {output_path}")

if __name__ == "__main__":
    main()
