"""Public B2B lead scraper using DuckDuckGo's HTML endpoint (no API keys)."""

import re
import time
from urllib.parse import parse_qs, quote_plus, unquote, urlparse

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
)

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


def _clean_dial_number(phone_str):
    digits = re.sub(r"\D", "", str(phone_str))
    if len(digits) == 12 and digits.startswith("91"):
        return "+" + digits
    return digits


def extract_contact_info(url):
    """Fetch a website and return (phones, emails) lists found in its HTML."""
    phones, emails = [], []
    try:
        resp = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
        if resp.status_code != 200:
            return phones, emails
        soup = BeautifulSoup(resp.text, "html.parser")

        for a in soup.select("a[href^='tel:']"):
            phones.append(a["href"][4:].strip())
        for a in soup.select("a[href^='mailto:']"):
            emails.append(a["href"][7:].split("?")[0].strip())

        text = soup.get_text(" ", strip=True)
        phones.extend(m.group(0).strip() for m in PHONE_PATTERN.finditer(text))
        emails.extend(EMAIL_PATTERN.findall(resp.text))
    except requests.RequestException:
        return [], []

    seen, clean_phones = set(), []
    for p in phones:
        digits = re.sub(r"\D", "", p)
        if 10 <= len(digits) <= 13 and digits not in seen:
            seen.add(digits)
            clean_phones.append(p)

    clean_emails = []
    for e in emails:
        e_low = e.lower().strip(".")
        if any(j in e_low for j in EMAIL_JUNK):
            continue
        if e_low not in clean_emails:
            clean_emails.append(e_low)
    return clean_phones, clean_emails


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


def _is_blocked(url):
    netloc = urlparse(url).netloc.lower()
    return any(netloc == d or netloc.endswith("." + d) for d in BLOCKED_DOMAINS)


def _clean_business_name(title):
    name = re.split(r"\s[\|\-–—:]\s", title)[0].strip()
    return name or title.strip()


def search_public_leads(industry, location, limit=10):
    """Search DuckDuckGo HTML results and build a list of lead dictionaries."""
    query = f"{industry} in {location} contact details"
    leads, seen_names, seen_domains = [], set(), set()
    offset = 0

    while len(leads) < limit and offset <= 150:
        url = f"https://html.duckduckgo.com/html/?q={quote_plus(query)}&s={offset}"
        try:
            resp = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
            resp.raise_for_status()
        except requests.RequestException:
            break

        soup = BeautifulSoup(resp.text, "html.parser")
        results = soup.select("div.result")
        if not results:
            break

        for res in results:
            if len(leads) >= limit:
                break
            link = res.select_one("a.result__a")
            if not link:
                continue
            website = _resolve_ddg_link(link.get("href", ""))
            if not website.startswith("http") or _is_blocked(website):
                continue
            domain = urlparse(website).netloc.lower().removeprefix("www.")
            name = _clean_business_name(link.get_text(" ", strip=True))
            key = name.lower()
            if not name or key in seen_names or domain in seen_domains:
                continue
            seen_names.add(key)
            seen_domains.add(domain)

            snippet_el = res.select_one(".result__snippet")
            snippet = snippet_el.get_text(" ", strip=True) if snippet_el else ""
            phones = [m.group(0) for m in PHONE_PATTERN.finditer(snippet)]
            emails = [e for e in EMAIL_PATTERN.findall(snippet) if not any(j in e.lower() for j in EMAIL_JUNK)]

            site_phones, site_emails = extract_contact_info(website)
            phones = phones + [p for p in site_phones if p not in phones]
            emails = emails + [e for e in site_emails if e not in emails]

            wa_num = ""
            for p in phones:
                wa_num = clean_whatsapp_number(p)
                if wa_num:
                    break
            phone = phones[0] if phones else ""
            dial = _clean_dial_number(phone) if phone else ""

            leads.append({
                "Lead ID": len(leads) + 1,
                "Business Name": name,
                "Phone": phone,
                "Call Link": f"tel:{dial}" if dial else "",
                "WhatsApp Link": f"https://wa.me/{wa_num}" if wa_num else "",
                "Email Address": emails[0] if emails else "",
                "Website": website,
                "Call Status": "Pending",
                "Notes": "",
                "City": location,
            })

        offset += len(results)
        time.sleep(1)

    return leads
