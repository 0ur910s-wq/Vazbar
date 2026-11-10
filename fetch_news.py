import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

import bs4
import feedparser

HEADERS = {
    "User-Agent": "VazbarNews/1.0 (+https://0ur910s-wq.github.io/Vazbar/)",
    "Accept": "application/rss+xml, application/atom+xml, application/xml, text/xml, text/html;q=0.9, */*;q=0.8",
    "Accept-Language": "el-GR,el;q=0.9,en-US;q=0.8,en;q=0.7",
}
MAX_PER_SOURCE = 30
MAX_TOTAL = 150

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


def utc_now_iso():
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def fetch_content(target_url):
    """Fetch a public source directly; do not hide source errors behind third-party proxies."""
    request = urllib.request.Request(target_url, headers=HEADERS)
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            data = response.read()
            if not data:
                raise RuntimeError(f"Empty response from {response.geturl()}")
            return data
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"HTTP {exc.code} from {exc.url}") from exc
    except urllib.error.URLError as exc:
        reason = getattr(exc, "reason", exc)
        raise RuntimeError(f"Network error for {urllib.parse.urlsplit(target_url).netloc}: {reason}") from exc


def entry_date(entry):
    for key in ("published_parsed", "updated_parsed"):
        parsed = entry.get(key)
        if parsed:
            return datetime(*parsed[:6], tzinfo=timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")

    for key in ("published", "updated"):
        value = entry.get(key)
        if not value:
            continue
        try:
            parsed = parsedate_to_datetime(value)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
        except (TypeError, ValueError, OverflowError):
            continue
    return None


def srcset_url(value):
    candidates = []
    for part in (value or "").split(","):
        fields = part.strip().split()
        if not fields:
            continue
        score = 0.0
        if len(fields) > 1:
            descriptor = fields[1].lower()
            try:
                score = float(descriptor[:-1]) if descriptor.endswith("x") else float(descriptor[:-1]) / 1000
            except ValueError:
                pass
        candidates.append((score, fields[0]))
    return max(candidates, default=(0, ""))[1]


def image_from_element(element, base_url):
    nodes = [element] + element.find_all(["img", "source"])
    for attribute in ("data-src", "data-lazy-src", "data-original", "data-srcset", "srcset", "src"):
        for node in nodes:
            value = node.get(attribute)
            if attribute in ("data-srcset", "srcset"):
                value = srcset_url(value)
            if value and not value.strip().lower().startswith("data:"):
                return urllib.parse.urljoin(base_url, value.strip())
    for node in nodes:
        style = node.get("style", "")
        match = re.search(r"background-image\s*:\s*url\(['\"]?([^)'\"]+)", style, re.I)
        if match:
            return urllib.parse.urljoin(base_url, match.group(1).strip())
    return ""


def image_from_html(markup, base_url):
    if not markup:
        return ""
    soup = bs4.BeautifulSoup(markup, "html.parser")
    image = soup.find(["img", "source"])
    return image_from_element(image, base_url) if image else ""


def fetch_rss_feed(source):
    feed = feedparser.parse(fetch_content(source["url"]))
    if not feed.entries:
        detail = f" ({feed.bozo_exception})" if getattr(feed, "bozo", False) else ""
        raise RuntimeError(f"Feed contained no entries{detail}")

    articles = []
    for entry in feed.entries[:MAX_PER_SOURCE]:
        title = entry.get("title", "").strip()
        link = entry.get("link", "").strip()
        if not title or not link:
            continue

        image_url = ""
        for group in (entry.get("media_content"), entry.get("media_thumbnail"), entry.get("enclosures")):
            if isinstance(group, dict):
                group = [group]
            for media in group or []:
                image_url = media.get("url") or media.get("href") or ""
                if image_url:
                    image_url = urllib.parse.urljoin(link, image_url)
                    break
            if image_url:
                break
        if not image_url:
            snippets = [part.get("value", "") for part in entry.get("content", [])]
            snippets.extend((entry.get("summary", ""), entry.get("description", "")))
            image_url = image_from_html(" ".join(snippets), link)

        published = entry_date(entry)
        articles.append({
            "title": title,
            "link": link,
            "pubDate": published,
            "date": published,
            "source": source["name"],
            "color": source["color"],
            "sport": source["sport"],
            "image": image_url,
        })

    if not articles:
        raise RuntimeError("Feed had no usable article entries")
    return articles


def fetch_html_site(source):
    html = fetch_content(source["url"]).decode("utf-8", errors="replace")
    soup = bs4.BeautifulSoup(html, "html.parser")
    articles = []
    for anchor in soup.find_all("a", href=True):
        title = anchor.get_text(" ", strip=True)
        if len(title) <= 25:
            continue
        link = urllib.parse.urljoin(source["url"], anchor["href"])
        image_url = image_from_element(anchor, source["url"])
        if not image_url:
            card = anchor.find_parent("article")
            if card:
                image_url = image_from_element(card, source["url"])
        articles.append({
            "title": title,
            "link": link,
            "pubDate": None,
            "date": None,
            "source": source["name"],
            "color": source["color"],
            "sport": source["sport"],
            "image": image_url,
        })
        if len(articles) >= MAX_PER_SOURCE:
            break

    if not articles:
        raise RuntimeError("No usable article links found on the page")
    return articles


def load_previous_items(path):
    if not os.path.exists(path):
        return []
    try:
        with open(path, "r", encoding="utf-8") as file:
            payload = json.load(file)
        if isinstance(payload, list):
            return payload
        if isinstance(payload, dict) and isinstance(payload.get("items"), list):
            return payload["items"]
    except (OSError, json.JSONDecodeError):
        pass
    return []


def main():
    output_path = "news.json"
    existing_items = load_previous_items(output_path)
    articles = []
    source_status = {}

    for source in SOURCES:
        name = source["name"]
        status = source_status.setdefault(name, {"ok": False, "count": 0, "_successes": 0, "_errors": []})
        try:
            fetched = fetch_html_site(source) if source["type"] == "html" else fetch_rss_feed(source)
            articles.extend(fetched)
            status["_successes"] += 1
            status["count"] += len(fetched)
            print(f"OK {name} ({source['sport']}): {len(fetched)} articles")
        except Exception as exc:
            error = f"{source['url']}: {exc}"
            status["_errors"].append(error)
            print(f"ERROR {name} ({source['sport']}): {error}")
            # Retain this source/sport's last good articles during temporary outages.
            articles.extend(
                item for item in existing_items
                if item.get("source") == name and item.get("sport") == source["sport"]
            )

    for status in source_status.values():
        status["ok"] = status.pop("_successes") > 0
        errors = status.pop("_errors")
        if errors:
            status["msg"] = "Some endpoints failed: " + "; ".join(errors)
            if not status["ok"]:
                status["msg"] = "All endpoints failed: " + "; ".join(errors)

    # Deduplicate by URL while keeping the first copy, then keep the payload bounded.
    seen = set()
    unique_articles = []
    for item in articles:
        link = item.get("link", "").strip()
        if not link or link in seen:
            continue
        seen.add(link)
        unique_articles.append(item)
    unique_articles = unique_articles[:MAX_TOTAL]

    payload = {
        "updated": utc_now_iso(),
        "sources": source_status,
        "items": unique_articles,
    }
    with open(output_path, "w", encoding="utf-8") as file:
        json.dump(payload, file, ensure_ascii=False, indent=2)
        file.write("\n")

    print(f"Saved {len(unique_articles)} articles to {output_path}")
    for name, status in source_status.items():
        label = "OK" if status["ok"] else "ERROR"
        print(f"{label} {name}: {status['count']} articles" + (f" — {status['msg']}" if status.get("msg") and not status["ok"] else ""))


if __name__ == "__main__":
    main()
