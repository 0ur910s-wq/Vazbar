// Κατεβάζει τα RSS feeds, κρατά μόνο ειδήσεις Παναθηναϊκού και γράφει news.json
const fs = require("fs");

// onlyPao: true  -> το feed είναι ήδη μόνο ΠΑΟ, δεν φιλτράρεται
// onlyPao: false -> κρατάμε μόνο ό,τι αναφέρει Παναθηναϊκό
// ΣΗΜΑΝΤΙΚΟ: έλεγξε/διόρθωσε τα URL με αυτά που έχεις στο index.html
const FEEDS = [
  { name: "Athletiko",    url: "https://www.athletiko.gr/feed/",        onlyPao: false },
  { name: "NewsPao",      url: "https://newspao.gr/feed/",              onlyPao: true  },
  { name: "Trifilara",    url: "https://www.trifilara.gr/feed/",        onlyPao: true  },
  { name: "Gazzetta PAO", url: "https://www.gazzetta.gr/teams/panathinaikos/rss", onlyPao: true },
  { name: "Google News PAO", url: "https://news.google.com/rss/topics/CAAqJggKIiBDQkFTRWdvSUwyMHZNRFp1ZEdvU0FtVnNHZ0pIVWlnQVAB?hl=el&gl=GR&ceid=GR%3Ael", onlyPao: false },
];

const MAX_PER_FEED = 30;
const MAX_TOTAL = 150;
const MAX_AGE_DAYS = 7;
const UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36";

const strip = (s) =>
  s.normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase();

const PAO_RE = /παναθηναικ|τριφυλλ|panathinaik|(^|[^α-ωa-z])(παο|pao)($|[^α-ωa-z])/;
const isPao = (t) => PAO_RE.test(strip(t));

function decode(s = "") {
  return s
    .replace(/<!\[CDATA\[([\s\S]*?)\]\]>/g, "$1")
    .replace(/&amp;/g, "&").replace(/&lt;/g, "<").replace(/&gt;/g, ">")
    .replace(/&quot;/g, '"').replace(/&#0?39;/g, "'").replace(/&apos;/g, "'")
    .replace(/&#(\d+);/g, (_, n) => String.fromCharCode(+n))
    .replace(/&#x([0-9a-f]+);/gi, (_, n) => String.fromCharCode(parseInt(n, 16)))
    .trim();
}
const stripTags = (s) => decode(s).replace(/<[^>]+>/g, " ").replace(/\s+/g, " ").trim();

function tag(block, name) {
  const m = block.match(new RegExp(`<${name}(?:\\s[^>]*)?>([\\s\\S]*?)</${name}>`, "i"));
  return m ? m[1] : "";
}

function parse(xml) {
  const blocks = xml.match(/<item[\s>][\s\S]*?<\/item>/gi) || xml.match(/<entry[\s>][\s\S]*?<\/entry>/gi) || [];
  return blocks.map((b) => {
    let link = decode(tag(b, "link"));
    if (!link) {
      const m = b.match(/<link[^>]*href=["']([^"']+)["']/i);
      link = m ? m[1] : "";
    }
    const dateStr = decode(tag(b, "pubDate") || tag(b, "published") || tag(b, "updated") || tag(b, "dc:date"));
    const t = Date.parse(dateStr);
    const img =
      (b.match(/<media:content[^>]*url=["']([^"']+)["']/i) || [])[1] ||
      (b.match(/<enclosure[^>]*url=["']([^"']+)["'][^>]*type=["']image/i) || [])[1] ||
      (b.match(/<img[^>]*src=["']([^"']+)["']/i) || [])[1] || "";
    return {
      title: stripTags(tag(b, "title")),
      link,
      date: isNaN(t) ? null : new Date(t).toISOString(),
      summary: stripTags(tag(b, "description") || tag(b, "summary")).slice(0, 240),
      image: decode(img),
    };
  }).filter((i) => i.title && i.link);
}

async function fetchFeed(feed) {
  const res = await fetch(feed.url, {
    headers: { "User-Agent": UA, Accept: "application/rss+xml, application/xml, text/xml, */*" },
    signal: AbortSignal.timeout(20000),
    redirect: "follow",
  });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  const items = parse(await res.text());
  if (!items.length) throw new Error("Κενό ή μη έγκυρο feed");
  return items;
}

(async () => {
  const sources = [];
  let all = [];

  await Promise.all(FEEDS.map(async (feed) => {
    try {
      let items = await fetchFeed(feed);
      if (!feed.onlyPao) items = items.filter((i) => isPao(i.title + " " + i.summary));
      items = items.slice(0, MAX_PER_FEED).map((i) => ({ ...i, source: feed.name }));
      sources.push({ name: feed.name, ok: true, count: items.length });
      all.push(...items);
    } catch (e) {
      sources.push({ name: feed.name, ok: false, error: e.message });
    }
  }));

  // Αν όλα αποτύχουν, κρατάμε το προηγούμενο news.json
  if (!all.length && fs.existsSync("news.json")) {
    console.log("Κανένα αποτέλεσμα — κρατάω το παλιό news.json");
    process.exit(0);
  }

  const cutoff = Date.now() - MAX_AGE_DAYS * 864e5;
  const seen = new Set();
  all = all
    .filter((i) => !i.date || Date.parse(i.date) >= cutoff)
    .filter((i) => {
      const k = strip(i.title).replace(/[^a-zα-ω0-9]/g, "").slice(0, 60);
      if (seen.has(k)) return false;
      seen.add(k);
      return true;
    })
    .sort((a, b) => (Date.parse(b.date) || 0) - (Date.parse(a.date) || 0))
    .slice(0, MAX_TOTAL);

  sources.sort((a, b) => FEEDS.findIndex((f) => f.name === a.name) - FEEDS.findIndex((f) => f.name === b.name));

  fs.writeFileSync("news.json", JSON.stringify({ updated: new Date().toISOString(), sources, items: all }, null, 1));
  console.log(sources.map((s) => `${s.ok ? "OK " : "ERR"} ${s.name} ${s.ok ? s.count : s.error}`).join("\n"));
})();
