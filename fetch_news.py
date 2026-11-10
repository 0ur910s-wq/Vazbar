#!/usr/bin/env python3
"""
Κατεβάζει τα νέα του Παναθηναϊκού από τις πηγές και τα γράφει στο news.json.
Τρέχει αυτόματα στο GitHub (αρχείο .github/workflows/update.yml) – δεν χρειάζεται να το τρέξεις εσύ.
Δουλεύει server-side, άρα δεν έχει προβλήματα CORS / proxies / ορίων rss2json και μπορεί να βρει και φωτογραφίες.
"""
import gzip
import html as htmllib
import json
import os
import re
import sys
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")

# Ίδιες πηγές με τη σελίδα. Η σειρά μετράει για το Athletiko (πρώτα ειδικά αθλήματα, μετά το γενικό).
SOURCES = [
    {"name": "Athletiko",    "type": "html", "url": "https://www.athletiko.gr/panathinaikos-podosfairo", "color": "#00a651", "sport": "football"},
    {"name": "Athletiko",    "type": "html", "url": "https://www.athletiko.gr/panathinaikos-mpasket",    "color": "#00a651", "sport": "basket"},
    {"name": "Athletiko",    "type": "html", "url": "https://www.athletiko.gr/panathinaikos",            "color": "#00a651", "sport": "other"},
    {"name": "pao.gr",       "type": "rss",  "url": "https://www.pao.gr/feed/",                          "color": "#0a7d2e", "sport": "football"},
    {"name": "paobc.gr",     "type": "rss",  "url": "https://www.paobc.gr/feed/",                        "color": "#0a3d8a", "sport": "basket"},
    {"name": "NewsPao",      "type": "rss",  "url": "https://newspao.gr/feed/",                          "color": "#0a7d2e", "sport": "football"},
    {"name": "Trifilara",    "type": "rss",  "url": "https://trifilara.gr/feed/",                        "color": "#2d8a2d", "sport": "football"},
    {"name": "SDNA PAO",     "type": "rss",  "url": "https://www.sdna.gr/rss/223/panathinaikos",         "color": "#ffcc00", "sport": "football"},
    {"name": "Gazzetta PAO", "type": "rss",  "url": "https://www.gazzetta.gr/feed/tags/panathinaikos",   "color": "#ff6b00", "sport": "basket"},
    {"name": "Sport24 PAO",  "type": "rss",  "url": "https://www.sport24.gr/feed/?tag=panathinaikos",    "color": "#d91e2b", "sport": "football"},
]

OUT = os.environ.get("NEWS_OUT", "news.json")
MAX_PER_SOURCE = 25
MAX_TOTAL = 200
MAX_IMG_FETCH = 30  # πόσες σελίδες άρθρων θα ανοίγουμε ανά τρέξιμο για να βρούμε φωτογραφία


def get(url, timeout=20, limit=None):
    req = urllib.request.Request(url, headers={
        "User-Agent": UA,
        "Accept": "text/html,application/xhtml+xml,application/xml,application/rss+xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "el,en;q=0.8",
    })
    with urllib.request.urlopen(req, timeout=timeout) as r:
        data = r.read(limit) if limit else r.read()
        try:
            enc = r.headers.get("Content-Encoding", "")
        except Exception:
            enc = ""
    if enc == "gzip" and not limit:
        data = gzip.decompress(data)
    return data


def text_of(s):
    s = re.sub(r"<[^>]+>", "", s or "")
    s = htmllib.unescape(htmllib.unescape(s))
    return re.sub(r"\s+", " ", s).strip()


def parse_dt(s):
    if not s:
        return None
    s = s.strip()
    d = None
    try:
        d = parsedate_to_datetime(s)
    except Exception:
        d = None
    if d is None:
        try:
            d = datetime.fromisoformat(s.replace("Z", "+00:00"))
        except Exception:
            return None
    if d.tzinfo is None:
        d = d.replace(tzinfo=timezone.utc)
    return d.astimezone(timezone.utc)


def abs_url(u, base=None):
    u = (u or "").strip()
    if not u:
        return ""
    if u.startswith("//"):
        return "https:" + u
    if u.startswith("/") and base:
        m = re.match(r"(https?://[^/]+)", base)
        return (m.group(1) + u) if m else ""
    if u.startswith("http://"):
        return "https://" + u[len("http://"):]
    return u if u.startswith("https://") else ""


def local(tag):
    return tag.rsplit("}", 1)[-1]


# ---------------- RSS ----------------
def parse_rss(data):
    try:
        root = ET.fromstring(data)
    except ET.ParseError:
        txt = data.decode("utf-8", "replace")
        txt = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", txt)
        txt = re.sub(r"^\s*<\?xml[^>]*\?>", "", txt)
        root = ET.fromstring(txt)
    out = []
    for el in root.iter():
        if local(el.tag) not in ("item", "entry"):
            continue
        title = link = pub = body = image = ""
        for c in el:
            n = local(c.tag)
            if n == "title":
                title = text_of(c.text)
            elif n == "link":
                link = (c.text or "").strip() or c.get("href", "")
            elif n in ("pubDate", "published", "updated", "date") and not pub:
                pub = c.text or ""
            elif n in ("content", "thumbnail") and c.get("url"):
                if not image:
                    image = c.get("url")
            elif n in ("encoded", "content", "description", "summary") and not body:
                body = c.text or ""
            elif n == "enclosure" and c.get("url") and "image" in (c.get("type") or "image") and not image:
                image = c.get("url")
        if not image:
            m = re.search(r"<img[^>]+(?:data-src|data-lazy-src|src)=[\"']([^\"']+)[\"']", body or "", re.I)
            image = m.group(1) if m else ""
        if title and link:
            out.append({"title": title, "link": link.strip(), "image": abs_url(htmllib.unescape(image)), "pub": parse_dt(pub)})
    if not out:
        raise ValueError("Κενό ή μη έγκυρο feed")
    return out


# ---------------- ATHLETIKO (HTML) ----------------
ATH_A = re.compile(
    r"<a\b[^>]*?href=[\"'](?P<h>(?:https?://(?:www\.)?athletiko\.gr)?/[^\"'#?\s]+-\d{4,7})/?(?:[#?][^\"']*)?[\"'][^>]*>",
    re.I)
REL = re.compile(r"πριν\s+(\d+)\s+(δευτ|λεπτ|ώρ|ημέρ|εβδομ)", re.I)


def parse_athletiko(page, now=None):
    now = now or datetime.now(timezone.utc)
    found = {}
    order = []
    for m in ATH_A.finditer(page):
        link = abs_url(m.group("h"), "https://www.athletiko.gr")
        if link.startswith("https://athletiko.gr"):
            link = link.replace("https://athletiko.gr", "https://www.athletiko.gr")
        tag = m.group(0)
        t = ""
        tm = re.search(r"title=[\"']([^\"']+)[\"']", tag)
        if tm:
            t = text_of(tm.group(1))
        end = page.find("</a>", m.end())
        inner = text_of(page[m.end():end]) if end != -1 else ""
        prio = 2 if t else 0
        if not t and inner and not inner.startswith("/") and not inner.startswith("http"):
            t, prio = inner, 1
        if link not in found:
            found[link] = {"link": link, "title": "", "prio": 0, "start": m.start()}
            order.append(link)
        if t and prio > found[link]["prio"]:
            found[link]["title"], found[link]["prio"] = t, prio
    out = []
    for i, link in enumerate(order):
        rec = found[link]
        nxt = found[order[i + 1]]["start"] if i + 1 < len(order) else len(page)
        window = page[rec["start"]:min(nxt, rec["start"] + 3000)]
        d = None
        rm = REL.search(text_of(window))
        if rm:
            n, u = int(rm.group(1)), rm.group(2).lower()
            delta = (timedelta(seconds=n) if u.startswith("δευτ") else timedelta(minutes=n) if u.startswith("λεπτ")
                     else timedelta(hours=n) if u.startswith("ώρ") else timedelta(days=n) if u.startswith("ημέρ")
                     else timedelta(weeks=n))
            d = now - delta
        if rec["title"]:
            out.append({"title": rec["title"], "link": link, "image": "", "pub": d, "order": i})
    if not out:
        raise ValueError("Δεν βρέθηκαν άρθρα (άλλαξε η δομή της σελίδας;)")
    return out


def og_image(url):
    page = get(url, 15, limit=250000).decode("utf-8", "replace")
    pats = [
        r"<meta[^>]+(?:property|name)=[\"']og:image(?::secure_url)?[\"'][^>]*content=[\"']([^\"']+)[\"']",
        r"<meta[^>]+content=[\"']([^\"']+)[\"'][^>]+(?:property|name)=[\"']og:image[\"']",
        r"<meta[^>]+(?:property|name)=[\"']twitter:image[\"'][^>]*content=[\"']([^\"']+)[\"']",
    ]
    for p in pats:
        m = re.search(p, page, re.I)
        if m:
            return abs_url(htmllib.unescape(m.group(1)), url)
    return ""


# ---------------- ΚΥΡΙΟ ----------------
def load_prev():
    try:
        with open(OUT, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def main(sources=None):
    sources = sources or SOURCES
    now = datetime.now(timezone.utc)
    prev = load_prev()
    prev_items = {i["link"]: i for i in prev.get("items", [])}
    status = {}
    items = []
    seen = set()
    img_budget = MAX_IMG_FETCH
    failed_names = set()

    for src in sources:
        name = src["name"]
        st = status.setdefault(name, {"ok": False, "n": 0, "msg": ""})
        try:
            data = get(src["url"])
            if src["type"] == "html":
                raw = parse_athletiko(data.decode("utf-8", "replace"), now)
            else:
                raw = parse_rss(data)
        except Exception as e:
            if not st["ok"]:
                st["msg"] = "%s: %s" % (type(e).__name__, str(e)[:120])
            print("FAIL", name, src["url"], e, file=sys.stderr)
            continue
        st["ok"] = True
        st["msg"] = ""
        cnt = 0
        for r in raw[:MAX_PER_SOURCE]:
            link = r["link"]
            if link in seen:
                continue
            seen.add(link)
            p = prev_items.get(link)
            image = r["image"]
            tried = False
            if not image and p:
                image = p.get("image", "")
                tried = bool(p.get("noimg"))
            if not image and not tried and img_budget > 0:
                img_budget -= 1
                try:
                    image = og_image(link)
                except Exception:
                    image = ""
                tried = True
            pub = r["pub"]
            if src["type"] == "html" and p and p.get("pubDate"):
                pub = parse_dt(p["pubDate"]) or pub  # κρατάμε την ώρα που πρωτοείδαμε το άρθρο
            if pub is None:
                pub = now - timedelta(minutes=2 * (r.get("order", cnt) + 1))
            if pub > now + timedelta(minutes=5):
                pub = now
            item = {"title": r["title"], "link": link, "image": image, "source": name,
                    "color": src["color"], "sport": src["sport"],
                    "pubDate": pub.strftime("%Y-%m-%dT%H:%M:%SZ")}
            if not image:
                item["noimg"] = True
            items.append(item)
            cnt += 1
        st["n"] += cnt

    # Αν μια πηγή απέτυχε, κρατάμε τα προηγούμενα άρθρα της ώστε να μη χαθούν
    for name, st in status.items():
        if not st["ok"]:
            for p in prev.get("items", []):
                if p.get("source") == name and p["link"] not in seen:
                    seen.add(p["link"])
                    items.append(p)

    items.sort(key=lambda i: i["pubDate"], reverse=True)
    items = items[:MAX_TOTAL]
    result = {"items": items, "sources": status}

    if not items:
        print("Καμία είδηση – δεν γράφω το αρχείο.", file=sys.stderr)
        return 1

    old = {k: v for k, v in prev.items() if k != "updated"}
    if json.dumps(old, sort_keys=True, ensure_ascii=False) == json.dumps(result, sort_keys=True, ensure_ascii=False):
        print("Καμία αλλαγή.")
        return 0
    result["updated"] = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=1)
    print("Γράφτηκαν %d ειδήσεις. Πηγές OK: %d/%d" % (len(items), sum(1 for s in status.values() if s["ok"]), len(status)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
