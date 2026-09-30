"""FastAPI service exposing the public lead scraper for the mobile PWA."""

import os
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from scraper import DEFAULT_SOURCES, MIN_CONFIDENCE, search_public_leads

app = FastAPI(title="Lead Generator API", version="1.0.0")

allowed_origins = [o.strip() for o in os.getenv("ALLOWED_ORIGINS", "*").split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_methods=["GET"],
    allow_headers=["*"],
)


@app.get("/healthz")
def health():
    return {"status": "ok"}


@app.get("/api/leads")
async def get_leads(
    industry: str = Query(..., min_length=2, max_length=100),
    location: str = Query(..., min_length=2, max_length=100),
    limit: int = Query(10, ge=1, le=50),
    sources: str = Query(",".join(DEFAULT_SOURCES), description="Comma list: indiamart,tradeindia,government,websites"),
    min_confidence: int = Query(MIN_CONFIDENCE, ge=0, le=100),
):
    chosen = tuple(s.strip().lower() for s in sources.split(",") if s.strip().lower() in DEFAULT_SOURCES)
    if not chosen:
        raise HTTPException(status_code=422, detail=f"sources must include one of: {', '.join(DEFAULT_SOURCES)}")
    try:
        leads = await run_in_threadpool(
            search_public_leads, industry.strip(), location.strip(), limit, chosen, min_confidence
        )
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Search failed: {exc}") from exc

    return [
        {
            "id": f"{lead['Website']}",
            "name": lead["Business Name"],
            "phone": lead["Phone"],
            "email": lead["Email Address"],
            "website": lead["Website"],
            "city": lead["City"],
            "tel_link": lead["Call Link"],
            "wa_link": lead["WhatsApp Link"],
            "address": lead["Address"],
            "source": lead["Source"],
            "confidence": lead["Confidence"],
            "phone_found_via": lead["Phone Found Via"],
            "all_phones": lead["All Phones"],
        }
        for lead in leads
    ]


# Serve the mobile PWA from the same service so one always-on Render instance hosts everything.
FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"
if FRONTEND_DIR.is_dir():
    app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")
