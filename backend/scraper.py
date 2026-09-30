"""Public B2B lead scraper: DuckDuckGo HTML results with a Bing fallback (no API keys)."""

import base64
import re
import time
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

BLOCKED_DOMAINS = (
    "facebook.com",
    "instagram.com",
    "linkedin.com",
    "twitter.com",
    "x.com",
    "youtube.com",
    "justdial.com",
    "indiamart.com",
    "sulekha.com",
    "wikipedia.org",
    "duckduckgo.com",
    "bing.com",
    "microsoft.com",
    # directories, aggregators, review and news sites: they list many businesses, not one lead
    "yellowpages.in",
    "tradeindia.com",
    "exportersindia.com",
    "clutch.co",
    "goodfirms.co",
    "glassdoor.com",
    "glassdoor.co.in",
    "ambitionbox.com",
    "naukri.com",
    "indeed.com",
    "quora.com",
    "reddit.com",
    "zaubacorp.com",
    "tofler.in",
    "crunchbase.com",
    "yelp.com",
    "tripadvisor.in",
    "tripadvisor.com",
    "practo.com",
    "urbanpro.com",
    "grotal.com",
    "asklaila.com",
    "cybo.com",
    "nearbuy.com",
    "magicpin.in",
    "zomato.com",
    "swiggy.com",
    "google.com",
    "maps.google.com",
    "medium.com",
    "blogspot.com",
    "wordpress.com",
    "timesofindia.indiatimes.com",
    "thehindu.com",
    "economictimes.indiatimes.com",
    "icai.org",
    "gov.in",
)

# Titles like "Top 10 CA Firms in Chennai" or "List of ..." are articles/directories, not a business.
LISTICLE_PATTERN = re.compile(
    r"^\s*(top|best|list of|\d+\s+(best|top))\b|\b(top|best)\s+\d+\b|\bnear me\b|\bdirectory\b|\blistings?\b|\breviews?\b",
    re.IGNORECASE,
)

CONTACT_PATHS = ("/contact", "/contact-us", "/contactus")

EMAIL_JUNK = (".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp", "bootstrap", "example", "sentry", "wixpress", "domain.com")

PHONE_PATTERN = re.compile(
    r"(?:\+91[\s\-]?[6-9]\d{4}[\s\-]?\d{5})"          # +91 mobile
    r"|(?:\b0?44[\s\-]?\d{4}[\s\-]?\d{4}\b)"           # 044 landline (Chennai)
    r"|(?:\b0\d{2,4}[\s\-]\d{6,8}\b)"                  # other STD landlines
    r"|(?:\b[6-9]\d{9}\b)"                             # 10-digit mobile
)
EMAIL_PATTERN = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")

REQUEST_TIMEOUT = 10


def clean_whatsapp_number(phone_str):
    """Return a 12-digit '91XXXXXXXXXX' string for Indian mobiles, else ''."""
    if not phone_str:
        return ""
    digits = re.sub(r"\D", "", str(phone_str))
    if digits.startswith("0") and len(digits) == 11:
        digits = digits[1:]
    if len(digits) == 10 and digits[0] in "6789":
        return "91" + digits
    if len(digits) == 12 and digits.startswith("91") and digits[2] in "6789":
        return digits
    return ""


def _is_real_phone(phone_str):
    """Reject digit runs that match the pattern but are clearly not phone numbers."""
    digits = re.sub(r"\D", "", str(phone_str))
    if digits.startswith("91") and len(digits) == 12:
        digits = digits[2:]
    digits = digits.lstrip("0")
    if not 9 <= len(digits) <= 10:
        return False
    if len(set(digits)) <= 2:  # 9999999999, 1010101010
        return False
    if digits in "01234567890123456789" or digits in "98765432109876543210":  # sequential
        return False
    return True


def _clean_dial_number(phone_str):
    digits = re.sub(r"\D", "", str(phone_str))
    if len(digits) == 12 and digits.startswith("91"):
        return "+" + digits
    return digits


def _scan_page(url, phones, emails):
    """Collect phones/emails from one page into the given lists; return (soup, text) or (None, "")."""
    try:
        resp = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
    except requests.RequestException:
        return None, ""
    if resp.status_code != 200 or "html" not in resp.headers.get("Content-Type", "html"):
        return None, ""
    soup = BeautifulSoup(resp.text, "html.parser")
    for a in soup.select("a[href^='tel:']"):
        phones.append(unquote(a["href"][4:]).strip())
    for a in soup.select("a[href^='mailto:']"):
        emails.append(unquote(a["href"][7:]).split("?")[0].strip())
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    text = soup.get_text(" ", strip=True)
    phones.extend(m.group(0).strip() for m in PHONE_PATTERN.finditer(text))
    emails.extend(EMAIL_PATTERN.findall(text))
    return soup, text


def _site_name(soup):
    if soup is None:
        return ""
    meta = soup.find("meta", property="og:site_name")
    if meta and meta.get("content"):
        return meta["content"].strip()
    return ""


def extract_contact_info(url):
    """Fetch a website (home + contact page) and return (phones, emails, page_text, site_name)."""
    phones, emails = [], []
    soup, text = _scan_page(url, phones, emails)
    if soup is None:
        return [], [], "", ""
    site_name = _site_name(soup)

    parsed = urlparse(url)
    base = f"{parsed.scheme}://{parsed.netloc}"
    contact_url = ""
    for a in soup.find_all("a", href=True):
        if "contact" in a["href"].lower() or "contact" in a.get_text(" ", strip=True).lower():
            contact_url = urljoin(url, a["href"])
            break
    candidates = [contact_url] if contact_url else [base + p for p in CONTACT_PATHS[:1]]
    for c in candidates:
        if urlparse(c).netloc == parsed.netloc and c.rstrip("/") != url.rstrip("/"):
            _, contact_text = _scan_page(c, phones, emails)
            text += " " + contact_text

    seen, clean_phones = set(), []
    for p in phones:
        digits = re.sub(r"\D", "", p)
        if 10 <= len(digits) <= 13 and digits not in seen and _is_real_phone(p):
            seen.add(digits)
            clean_phones.append(p)

    clean_emails = []
    for e in emails:
        e_low = e.lower().strip(".")
        if any(j in e_low for j in EMAIL_JUNK) or not EMAIL_PATTERN.fullmatch(e_low):
            continue
        if e_low not in clean_emails:
            clean_emails.append(e_low)
    return clean_phones, clean_emails, text, site_name


def _resolve_ddg_link(href):
    if not href:
        return ""
    if href.startswith("//"):
        href = "https:" + href
    parsed = urlparse(href)
    if "duckduckgo.com" in parsed.netloc and parsed.path.startswith("/l/"):
        target = parse_qs(parsed.query).get("uddg", [""])[0]
        return unquote(target)
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


def _fetch_html(url):
    try:
        resp = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
    except requests.RequestException:
        return None
    if resp.status_code != 200:
        return None
    return BeautifulSoup(resp.text, "html.parser")


def _ddg_results(query, page):
    """Return (title, url, snippet) tuples for one DuckDuckGo results page, or [] if blocked."""
    soup = _fetch_html(f"https://html.duckduckgo.com/html/?q={quote_plus(query)}&s={page * 30}")
    if soup is None:
        return []
    results = []
    for res in soup.select("div.result"):
        link = res.select_one("a.result__a")
        if not link:
            continue
        snippet_el = res.select_one(".result__snippet")
        results.append((
            link.get_text(" ", strip=True),
            _resolve_ddg_link(link.get("href", "")),
            snippet_el.get_text(" ", strip=True) if snippet_el else "",
        ))
    return results


def _bing_results(query, page):
    """Return (title, url, snippet) tuples for one Bing results page, or [] if blocked."""
    soup = _fetch_html(f"https://www.bing.com/search?q={quote_plus(query)}&first={page * 10 + 1}&setlang=en-IN&cc=IN")
    if soup is None:
        return []
    results = []
    for res in soup.select("li.b_algo"):
        link = res.select_one("h2 a")
        if not link:
            continue
        snippet_el = res.select_one(".b_caption p, p.b_lineclamp2, p.b_lineclamp3, p.b_lineclamp4")
        results.append((
            link.get_text(" ", strip=True),
            _resolve_bing_link(link.get("href", "")),
            snippet_el.get_text(" ", strip=True) if snippet_el else "",
        ))
    return results


# Search engines tried in order; the next one is used when the previous one is blocked or runs dry.
SEARCH_ENGINES = (("DuckDuckGo", _ddg_results, 6), ("Bing", _bing_results, 10))


def _is_blocked(url):
    netloc = urlparse(url).netloc.lower()
    return any(netloc == d or netloc.endswith("." + d) for d in BLOCKED_DOMAINS)


def _clean_business_name(title):
    name = re.split(r"\s[\|\-–—:]\s", title)[0].strip()
    return name or title.strip()


def _build_lead(name, website, snippet, location, lead_id):
    """Return a lead verified against the business's own website, or None if it can't be verified."""
    site_phones, site_emails, site_text, site_name = extract_contact_info(website)
    if not site_text:
        return None  # site unreachable: can't confirm it's a real business

    # Must actually be in the requested city, otherwise it's an unrelated/unknown lead.
    if location.lower() not in (site_text + " " + snippet).lower():
        return None

    phones = site_phones + [
        m.group(0) for m in PHONE_PATTERN.finditer(snippet)
        if _is_real_phone(m.group(0)) and m.group(0) not in site_phones
    ]
    emails = site_emails
    if not phones and not emails:
        return None  # no way to contact them: not a usable lead

    if site_name and not LISTICLE_PATTERN.search(site_name):
        name = site_name

    wa_num = ""
    for p in phones:
        wa_num = clean_whatsapp_number(p)
        if wa_num:
            break
    phone = phones[0] if phones else ""
    dial = _clean_dial_number(phone) if phone else ""

    return {
        "Lead ID": lead_id,
        "Business Name": name,
        "Phone": phone,
        "Call Link": f"tel:{dial}" if dial else "",
        "WhatsApp Link": f"https://wa.me/{wa_num}" if wa_num else "",
        "Email Address": emails[0] if emails else "",
        "Website": website,
        "Call Status": "Pending",
        "Notes": "",
        "City": location,
    }


def search_public_leads(industry, location, limit=10):
    """Search DuckDuckGo (falling back to Bing) and build a list of lead dictionaries."""
    query = f"{industry} in {location} phone"
    leads, seen_names, seen_domains = [], set(), set()

    for _engine, fetch_page, max_pages in SEARCH_ENGINES:
        for page in range(max_pages):
            if len(leads) >= limit:
                return leads
            results = fetch_page(query, page)
            if not results:
                break  # blocked or no more results: move on to the next engine

            for title, website, snippet in results:
                if len(leads) >= limit:
                    break
                if not website.startswith("http") or _is_blocked(website):
                    continue
                domain = urlparse(website).netloc.lower().removeprefix("www.")
                name = _clean_business_name(title)
                key = name.lower()
                if not name or key in seen_names or domain in seen_domains or LISTICLE_PATTERN.search(title):
                    continue
                seen_names.add(key)
                seen_domains.add(domain)
                lead = _build_lead(name, website, snippet, location, len(leads) + 1)
                if lead:
                    leads.append(lead)

            time.sleep(1)

    return leads
