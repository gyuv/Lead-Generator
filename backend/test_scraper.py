"""Offline tests for lead verification: run with `cd backend && python -m pytest -q`."""

import json

import scraper

SELLER_PAGE = """<html><head><title>Sri Balaji CNC Works - Manufacturer of CNC Machines, Chennai</title>
<script type="application/ld+json">{}</script></head>
<body><h1>Sri Balaji CNC Works</h1><p>Manufacturer of CNC machine parts.</p>
<a href="mailto:sales@sribalajicnc.in">Email</a></body></html>""".format(json.dumps({
    "@context": "https://schema.org", "@type": "LocalBusiness", "name": "Sri Balaji CNC Works",
    "telephone": "+91-98401 23456",
    "address": {"streetAddress": "12 SIDCO Estate, Guindy", "addressLocality": "Chennai", "postalCode": "600032"},
}))

ARTICLE_PAGE = """<html><head><title>Top 10 CNC Machine Manufacturers in Chennai</title></head>
<body>Call 9840123456 for CNC machine companies in Chennai.</body></html>"""

FAKE_NUMBER_PAGE = """<html><head><title>ABC CNC Machine Shop</title></head>
<body>ABC CNC machine shop, Chennai. Phone: 9999999999. Order no 9840123456789</body></html>"""

UNLABELLED_DIGITS_PAGE = """<html><head><title>XYZ CNC Machine Tools</title></head>
<body>XYZ CNC machine tools Chennai. GST 33AAAAA0000A1Z5 Invoice 9840123457 dated.</body></html>"""

LABELLED_PAGE = """<html><head><title>Kumar CNC Machine Services | Chennai</title></head>
<body>Kumar CNC machine services, Ambattur, Chennai. Mobile No: 098841 22334</body></html>"""

OTHER_CITY_PAGE = """<html><head><title>Pune CNC Machine Works</title></head>
<body><a href="tel:+919822012345">Call</a> CNC machine works in Pune.</body></html>"""


def _verify(html, url="https://www.example-business.in/"):
    info = scraper.parse_business_page(html, url)
    return scraper.score_lead(info, url, "CNC Machine", "Chennai")


def test_normalize_phone():
    assert scraper.normalize_phone("+91-98401 23456") == "+919840123456"
    assert scraper.normalize_phone("098401 23456") == "+919840123456"
    assert scraper.normalize_phone("044 2434 5678") == "+914424345678"
    for bad in ("9999999999", "1234567890", "12345", "18001234567", "0000000000", "9840123456789"):
        assert scraper.normalize_phone(bad) == "", bad


def test_structured_seller_page_is_high_confidence():
    lead, reason = _verify(SELLER_PAGE, "https://www.indiamart.com/sri-balaji-cnc/")
    assert reason == "ok"
    assert lead["Business Name"] == "Sri Balaji CNC Works"
    assert lead["Phone"] == "+919840123456"
    assert lead["WhatsApp Link"] == "https://wa.me/919840123456"
    assert lead["Source"] == "IndiaMART"
    assert lead["Email Address"] == "sales@sribalajicnc.in"
    assert "Chennai" in lead["Address"]
    assert lead["Confidence"] >= 90


def test_labelled_phone_accepted():
    lead, reason = _verify(LABELLED_PAGE)
    assert reason == "ok" and lead["Phone"] == "+919884122334"
    assert lead["Business Name"] == "Kumar CNC Machine Services"


def test_rejections():
    assert _verify(FAKE_NUMBER_PAGE)[0] is None
    assert _verify(UNLABELLED_DIGITS_PAGE)[0] is None
    assert _verify(OTHER_CITY_PAGE)[1] == "location not on page"
    assert not scraper.is_candidate_url("https://example.com/top", ARTICLE_PAGE and "Top 10 CNC Machine Manufacturers")


def test_candidate_urls():
    assert scraper.is_candidate_url("https://www.indiamart.com/sri-balaji-cnc/", "Sri Balaji CNC Works")
    assert not scraper.is_candidate_url("https://dir.indiamart.com/chennai/cnc-machine.html", "CNC Machine in Chennai")
    assert not scraper.is_candidate_url("https://www.indiamart.com/proddetail/cnc-123.html", "CNC")
    assert not scraper.is_candidate_url("https://www.justdial.com/Chennai/CNC", "CNC")
    assert scraper.source_of("https://msme.tn.gov.in/list") == "Government register"


def test_search_pipeline_filters_and_ranks(monkeypatch):
    pages = {
        "https://www.indiamart.com/sri-balaji-cnc/": SELLER_PAGE,
        "https://kumarcnc.in/": LABELLED_PAGE,
        "https://abccnc.in/": FAKE_NUMBER_PAGE,
        "https://punecnc.in/": OTHER_CITY_PAGE,
    }

    class Resp:
        def __init__(self, text):
            self.text = text

    monkeypatch.setattr(scraper, "_fetch", lambda url: Resp(pages[url]) if url in pages else None)
    monkeypatch.setattr(scraper, "_search", lambda q, pages=2: [
        ("Sri Balaji CNC Works", "https://www.indiamart.com/sri-balaji-cnc/"),
        ("Top 10 CNC Machine Manufacturers in Chennai", "https://listicle.in/top-10"),
        ("Kumar CNC", "https://kumarcnc.in/"),
        ("ABC", "https://abccnc.in/"),
        ("Pune", "https://punecnc.in/"),
    ])
    leads = scraper.search_public_leads("CNC Machine", "Chennai", limit=10)
    assert [l["Business Name"] for l in leads] == ["Sri Balaji CNC Works", "Kumar CNC Machine Services"]
    assert leads[0]["Confidence"] >= leads[1]["Confidence"]
