"""FastAPI service exposing the public lead scraper for the mobile PWA."""

import os
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from scraper import search_public_leads

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
):
    try:
        leads = await run_in_threadpool(search_public_leads, industry.strip(), location.strip(), limit)
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
        }
        for lead in leads
    ]


# Serve the mobile PWA from the same service so one always-on Render instance hosts everything.
FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"
if FRONTEND_DIR.is_dir():
    app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")
