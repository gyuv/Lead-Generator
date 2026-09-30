"""High-accuracy public B2B lead scraper (no API keys).

Candidate pages come from DuckDuckGo (Bing as fallback) using source-targeted queries:
IndiaMART / TradeIndia seller pages, government register pages (gov.in / nic.in) and the
businesses' own websites. Every candidate is then fetched and verified before it is returned:

* phone numbers are taken only from structured data (JSON-LD / microdata), tel: links or text
  right after a "Phone / Mobile / Call" label, and must pass Indian numbering-plan checks;
* the page must mention both the searched location and the industry;
* article / "top 10" / job / news pages and multi-business search listings are rejected.

Each lead carries a confidence score (0-100) and the source it came from.
"""

import base64
import json
import re
import time
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import parse_qs, quote_plus, unquote, urljoin, urlparse

import requests
from bs4 import BeautifulSoup

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-IN,en;q=0.9",
}

REQUEST_TIMEOUT = 10
MIN_CONFIDENCE = 60

# Sites that never describe a single business (social, aggregators, search engines, news, jobs).
BLOCKED_DOMAINS = (
    "facebook.com", "instagram.com", "linkedin.com", "twitter.com", "x.com", "youtube.com",
    "pinterest.com", "quora.com", "reddit.com", "wikipedia.org", "justdial.com", "sulekha.com",
    "yellowpages.in", "asklaila.com", "grotal.com", "duckduckgo.com", "bing.com", "google.com",
    "microsoft.com", "naukri.com", "indeed.com", "glassdoor.com", "shine.com", "timesofindia.com",
    "indiatimes.com", "thehindu.com", "hindustantimes.com", "ndtv.com", "zaubacorp.com",
    "tofler.in", "medium.com", "blogspot.com", "wordpress.com",
)

# Paths on listing portals that show many businesses at once (not one seller).
LISTING_PATH_HINTS = ("/search", "/impcat/", "/proddetail/", "/products/", "/manufacturers/", "/suppliers/", "/city/")

JUNK_TITLE = re.compile(
    r"\b(top\s*\d+|best\s+\d*|list of|near me|directory|reviews?|jobs?|vacanc|news|blog|"
    r"how to|what is|guide|wiki|articles?|ranking|compare|vs\.?)\b",
    re.I,
)

EMAIL_PATTERN = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")
EMAIL_JUNK = (".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp", "bootstrap", "example", "sentry",
              "wixpress", "domain.com", "yourmail", "email.com")

# Phone-like digit runs (with optional +91 / 0 prefix and separators).
PHONE_CANDIDATE = re.compile(r"(?:\+?91[\s\-.]?)?\(?0?\d{2,5}\)?[\s\-.]?\d{3,5}[\s\-.]?\d{3,5}")
PHONE_LABEL = re.compile(r"(?:phone|mobile|mob|cell|call|tel|telephone|contact|ph|whatsapp)\s*(?:no\.?|number|#)?\s*[:\-.]?", re.I)


# ---------------------------------------------------------------- phone validation

def normalize_phone(raw):
    """Return an Indian number as '+91XXXXXXXXXX' if it is a plausible real number, else ''."""
    digits = re.sub(r"\D", "", str(raw or ""))
    if digits.startswith("0091"):
        digits = digits[4:]
    elif len(digits) == 12 and digits.startswith("91"):
        digits = digits[2:]
    elif len(digits) == 11 and digits.startswith("0"):
        digits = digits[1:]
    if len(digits) != 10 or digits[0] in "01":
        return ""
    if len(set(digits)) <= 2 or re.search(r"(\d)\1{6,}", digits):
        return ""  # 9999999999, 9000000000 ...
    if digits in "01234567890123456789" or digits in "98765432109876543210":
        return ""  # sequential filler
    if digits.startswith("1800") or digits.startswith("1860"):
        return ""
    return "+91" + digits


def is_mobile(e164):
    return bool(e164) and e164[3] in "6789"


def whatsapp_link(e164):
    return f"https://wa.me/{e164[1:]}" if is_mobile(e164) else ""


def _labelled_phones(text):
    """Phones that appear within a short window after a phone/mobile/call label."""
    found = []
    for label in PHONE_LABEL.finditer(text):
        window = text[label.end(): label.end() + 45]
        m = PHONE_CANDIDATE.search(window)
        if m:
            found.append(m.group(0))
    return found


# ---------------------------------------------------------------- page parsing

def _fetch(url):
    try:
        resp = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
    except requests.RequestException:
        return None
    if resp.status_code != 200 or "html" not in resp.headers.get("Content-Type", "html"):
        return None
    return resp


def _json_ld_entities(soup):
    """Yield dicts from JSON-LD blocks that describe an organisation / local business."""
    for tag in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(tag.string or "")
        except (ValueError, TypeError):
            continue
        stack = data if isinstance(data, list) else [data]
        while stack:
            item = stack.pop()
            if isinstance(item, list):
                stack.extend(item)
                continue
            if not isinstance(item, dict):
                continue
            stack.extend(v for k, v in item.items() if k == "@graph")
            kind = item.get("@type", "")
            kinds = kind if isinstance(kind, list) else [kind]
            if any(k and k not in ("WebSite", "WebPage", "BreadcrumbList", "SearchAction", "Product",
                                   "Offer", "ImageObject", "ListItem", "ItemList") for k in kinds):
                yield item


def _address_text(address):
    if isinstance(address, str):
        return address
    if isinstance(address, dict):
        parts = (address.get(k, "") for k in ("streetAddress", "addressLocality", "addressRegion", "postalCode"))
        return ", ".join(str(p) for p in parts if p)
    if isinstance(address, list) and address:
        return _address_text(address[0])
    return ""


def parse_business_page(html, url):
    """Extract name, phones (with how they were found), emails and address from one page."""
    soup = BeautifulSoup(html, "html.parser")
    info = {"name": "", "structured_phones": [], "tel_phones": [], "text_phones": [],
            "emails": [], "address": "", "is_business_schema": False, "contact_url": ""}

    for ent in _json_ld_entities(soup):
        info["is_business_schema"] = True
        info["name"] = info["name"] or str(ent.get("name", "")).strip()
        tel = ent.get("telephone")
        for t in (tel if isinstance(tel, list) else [tel]):
            if t:
                info["structured_phones"].append(str(t))
        info["address"] = info["address"] or _address_text(ent.get("address"))
        if ent.get("email"):
            info["emails"].append(str(ent["email"]).replace("mailto:", ""))

    for el in soup.select("[itemprop=telephone]"):
        info["structured_phones"].append(el.get("content") or el.get_text(" ", strip=True))
    for el in soup.select("[itemprop=address]"):
        info["address"] = info["address"] or el.get_text(" ", strip=True)

    for a in soup.select("a[href^='tel:']"):
        info["tel_phones"].append(a["href"][4:])
    for a in soup.select("a[href^='mailto:']"):
        info["emails"].append(a["href"][7:].split("?")[0])
    for a in soup.select("a[href]"):
        if re.search(r"contact", a.get("href", "") + " " + a.get_text(" ", strip=True), re.I):
            info["contact_url"] = urljoin(url, a["href"])
            break

    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    text = soup.get_text(" ", strip=True)
    info["text"] = text
    info["text_phones"] = _labelled_phones(text)
    info["emails"].extend(EMAIL_PATTERN.findall(text))

    if not info["name"]:
        og = soup.find("meta", property="og:site_name")
        title = soup.title.get_text(" ", strip=True) if soup.title else ""
        info["name"] = (og.get("content", "").strip() if og else "") or _clean_business_name(title)
    info["title"] = soup.title.get_text(" ", strip=True) if soup.title else ""
    return info


def _clean_business_name(title):
    name = re.split(r"\s[\|\-–—:]\s", title or "")[0].strip()
    return name or (title or "").strip()


def _clean_emails(emails, domain):
    out = []
    for e in emails:
        e = e.lower().strip(" .")
        if any(j in e for j in EMAIL_JUNK) or e in out:
            continue
        out.append(e)
    # Prefer an address on the business's own domain.
    out.sort(key=lambda e: 0 if domain and e.endswith("@" + domain) else 1)
    return out


# ---------------------------------------------------------------- verification & scoring

def _keywords(phrase):
    stop = {"and", "the", "for", "in", "of", "shop", "shops", "services", "service", "company", "companies"}
    words = [w for w in re.findall(r"[a-z0-9]+", phrase.lower()) if len(w) > 2 and w not in stop]
    return [w.rstrip("s") if len(w) > 4 else w for w in words] or [phrase.lower()]


def source_of(url):
    host = urlparse(url).netloc.lower()
    if host.endswith("indiamart.com"):
        return "IndiaMART"
    if host.endswith("tradeindia.com"):
        return "TradeIndia"
    if host.endswith(".gov.in") or host.endswith(".nic.in"):
        return "Government register"
    return "Business website"


def is_candidate_url(url, title=""):
    if not url.startswith("http"):
        return False
    parsed = urlparse(url)
    host = parsed.netloc.lower()
    if any(host == d or host.endswith("." + d) for d in BLOCKED_DOMAINS):
        return False
    src = source_of(url)
    path = parsed.path.lower()
    if src in ("IndiaMART", "TradeIndia"):
        # Keep seller / company pages, skip multi-seller search and category listings.
        if host.startswith("dir.") or "/search" in path:
            return False
        if any(h in path for h in LISTING_PATH_HINTS):
            return False
    elif src == "Business website" and JUNK_TITLE.search(title or ""):
        return False
    return True


def score_lead(info, url, industry, location):
    """Return (lead dict or None, reasons). None means the page failed verification."""
    domain = urlparse(url).netloc.lower().removeprefix("www.")
    text = (info.get("text", "") + " " + info.get("address", "")).lower()
    title = info.get("title", "")

    phones, method = [], ""
    for key, label in (("structured_phones", "structured data"), ("tel_phones", "click-to-call link"),
                       ("text_phones", "labelled on page")):
        for raw in info.get(key, []):
            p = normalize_phone(raw)
            if p and p not in phones:
                phones.append(p)
                method = method or label
    if not phones:
        return None, "no valid phone"
    if len(phones) > 6:
        return None, "too many phones (likely a listing page)"

    loc_words = _keywords(location)
    if not any(w in text for w in loc_words):
        return None, "location not on page"
    ind_words = _keywords(industry)
    ind_hits = sum(1 for w in ind_words if w in text or w in title.lower())
    if ind_hits == 0:
        return None, "industry not on page"
    name = info.get("name", "").strip()
    if not name or JUNK_TITLE.search(name):
        return None, "not a business name"

    score = {"structured data": 40, "click-to-call link": 35, "labelled on page": 30}[method]
    score += 20 if any(w in info.get("address", "").lower() for w in loc_words) else 15
    score += round(20 * ind_hits / len(ind_words))
    score += 10 if info.get("is_business_schema") else 0
    emails = _clean_emails(info.get("emails", []), domain)
    score += 5 if emails else 0
    score += 5 if source_of(url) != "Business website" else 0
    score = min(score, 100)

    phone = next((p for p in phones if is_mobile(p)), phones[0])
    lead = {
        "Business Name": name[:120],
        "Phone": phone,
        "All Phones": phones,
        "Call Link": f"tel:{phone}",
        "WhatsApp Link": whatsapp_link(phone),
        "Email Address": emails[0] if emails else "",
        "Website": url,
        "Address": info.get("address", "")[:200],
        "City": location,
        "Source": source_of(url),
        "Phone Found Via": method,
        "Confidence": score,
        "Call Status": "Pending",
        "Notes": "",
    }
    return lead, "ok"


def verify_candidate(url, industry, location):
    """Fetch a candidate page (and its contact page if needed) and return a verified lead or None."""
    resp = _fetch(url)
    if resp is None:
        return None
    info = parse_business_page(resp.text, url)
    lead, _ = score_lead(info, url, industry, location)
    if lead is None and info.get("contact_url") and info["contact_url"] != url:
        contact = _fetch(info["contact_url"])
        if contact is not None:
            cinfo = parse_business_page(contact.text, info["contact_url"])
            merged = dict(info)
            for key in ("structured_phones", "tel_phones", "text_phones", "emails"):
                merged[key] = info[key] + cinfo[key]
            merged["address"] = info["address"] or cinfo["address"]
            merged["text"] = info["text"] + " " + cinfo["text"]
            lead, _ = score_lead(merged, url, industry, location)
    return lead


# ---------------------------------------------------------------- search engines

def _resolve_ddg_link(href):
    if not href:
        return ""
    if href.startswith("//"):
        href = "https:" + href
    parsed = urlparse(href)
    if "duckduckgo.com" in parsed.netloc and parsed.path.startswith("/l/"):
        return unquote(parse_qs(parsed.query).get("uddg", [""])[0])
    return href


def _resolve_bing_link(href):
    """Decode Bing's /ck/a redirect links (u=a1<base64url>) to the real URL."""
    if not href:
        return ""
    parsed = urlparse(href)
    if "bing.com" in parsed.netloc and parsed.path.startswith("/ck/"):
        encoded = parse_qs(parsed.query).get("u", [""])[0]
        if encoded.startswith("a1"):
            encoded = encoded[2:]
            try:
                return base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4)).decode("utf-8", "ignore")
            except (ValueError, UnicodeDecodeError):
                return ""
    return href


def _ddg_results(query, page):
    resp = _fetch(f"https://html.duckduckgo.com/html/?q={quote_plus(query)}&s={page * 30}")
    if resp is None:
        return []
    soup = BeautifulSoup(resp.text, "html.parser")
    out = []
    for res in soup.select("div.result"):
        link = res.select_one("a.result__a")
        if link:
            out.append((link.get_text(" ", strip=True), _resolve_ddg_link(link.get("href", ""))))
    return out


def _bing_results(query, page):
    resp = _fetch(f"https://www.bing.com/search?q={quote_plus(query)}&first={page * 10 + 1}&setlang=en-IN&cc=IN")
    if resp is None:
        return []
    soup = BeautifulSoup(resp.text, "html.parser")
    out = []
    for res in soup.select("li.b_algo"):
        link = res.select_one("h2 a")
        if link:
            out.append((link.get_text(" ", strip=True), _resolve_bing_link(link.get("href", ""))))
    return out


SEARCH_ENGINES = (_ddg_results, _bing_results)

SOURCE_QUERIES = {
    "indiamart": 'site:indiamart.com "{industry}" {location}',
    "tradeindia": 'site:tradeindia.com "{industry}" {location}',
    "government": '(site:gov.in OR site:nic.in) "{industry}" {location} phone',
    "websites": '"{industry}" {location} contact phone address',
}
DEFAULT_SOURCES = ("indiamart", "tradeindia", "government", "websites")


def _search(query, pages=2):
    """Collect (title, url) results for a query, falling back to the next engine when blocked."""
    for engine in SEARCH_ENGINES:
        results = []
        for page in range(pages):
            batch = engine(query, page)
            if not batch:
                break
            results.extend(batch)
            time.sleep(1)
        if results:
            return results
    return []


def search_public_leads(industry, location, limit=10, sources=DEFAULT_SOURCES, min_confidence=MIN_CONFIDENCE):
    """Find, verify and rank leads. Only leads at or above `min_confidence` are returned."""
    candidates, seen_urls = [], set()
    for src in sources:
        template = SOURCE_QUERIES.get(src)
        if not template:
            continue
        for title, url in _search(template.format(industry=industry, location=location)):
            key = url.split("#")[0].rstrip("/")
            if key in seen_urls or not is_candidate_url(url, title):
                continue
            seen_urls.add(key)
            candidates.append(url)

    candidates = candidates[: max(limit * 5, 20)]
    with ThreadPoolExecutor(max_workers=8) as pool:
        verified = list(pool.map(lambda u: verify_candidate(u, industry, location), candidates))

    leads, seen_phones, seen_names = [], set(), set()
    for lead in sorted((v for v in verified if v), key=lambda l: -l["Confidence"]):
        name_key = re.sub(r"[^a-z0-9]", "", lead["Business Name"].lower())
        if lead["Confidence"] < min_confidence or lead["Phone"] in seen_phones or name_key in seen_names:
            continue
        seen_phones.add(lead["Phone"])
        seen_names.add(name_key)
        lead["Lead ID"] = len(leads) + 1
        leads.append(lead)
        if len(leads) >= limit:
            break
    return leads


# Kept for callers of the previous version.
def clean_whatsapp_number(phone_str):
    p = normalize_phone(phone_str)
    return p[1:] if is_mobile(p) else ""
