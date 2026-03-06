"""
Hoshloop SEO Engine — FastAPI Backend

Endpoints:
  POST /audit                    — Full SEO audit
  GET  /health                   — Health check

  Phase 2 — Keywords:
  GET  /gsc/connect              — Start Google Search Console OAuth flow
  GET  /gsc/callback             — OAuth callback (store tokens)
  POST /keywords/strike-zone     — Strike zone keywords (positions 5–20)
  GET  /keywords/trend           — Position trend for a single keyword
"""

import os
from contextlib import asynccontextmanager
from urllib.parse import urlparse

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Header, Query
from fastapi.responses import RedirectResponse  # used in /gsc/callback
from pydantic import BaseModel, HttpUrl

from .engine import run_audit
from .db import (
    init_schema,
    close_pool,
    get_gsc_token,
    save_gsc_token,
    upsert_company,
    get_company,
)
from .integrations.gsc import GSCClient
from .analyzers.keywords import analyze_strike_zone, get_keyword_history

load_dotenv()

API_SECRET = os.environ.get("API_SECRET_KEY", "")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("WARNING: ANTHROPIC_API_KEY not set. E-E-A-T analysis will be skipped.")
    if os.environ.get("DATABASE_URL"):
        try:
            await init_schema()
            print("Database schema initialised.")
        except Exception as e:
            print(f"WARNING: Database init failed: {e}. Growth features disabled.")
    else:
        print("WARNING: DATABASE_URL not set. Growth features disabled.")
    yield
    # Shutdown
    await close_pool()


app = FastAPI(
    title="Hoshloop SEO Engine",
    version="1.0.0",
    lifespan=lifespan,
)


class AuditRequest(BaseModel):
    url: HttpUrl
    competitor_url: HttpUrl | None = None


class AuditResponse(BaseModel):
    overallScore: int
    categories: list
    topFixes: list
    url: str
    domain: str
    fetchedAt: str
    auditDuration: int
    pageTitle: str | None
    metaDescription: str | None
    error: str | None = None


@app.get("/health")
async def health():
    return {"status": "ok", "engine": "hoshloop-seo"}


@app.post("/audit", response_model=AuditResponse)
async def audit(req: AuditRequest, x_api_key: str = Header(default="")):
    # Auth check
    if API_SECRET and x_api_key != API_SECRET:
        raise HTTPException(status_code=401, detail="Invalid API key")

    url = str(req.url)

    # Block private IPs
    from urllib.parse import urlparse
    parsed = urlparse(url)
    blocked = ["localhost", "127.0.0.1", "0.0.0.0", "::1"]
    if parsed.hostname in blocked or (parsed.hostname and (
        parsed.hostname.startswith("10.")
        or parsed.hostname.startswith("192.168.")
        or parsed.hostname.startswith("172.16.")
    )):
        raise HTTPException(status_code=400, detail="Private/local URLs not allowed")

    competitor = str(req.competitor_url) if req.competitor_url else None

    try:
        results = await run_audit(url, competitor_url=competitor)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Audit failed: {str(e)}")

    return results


# ---------------------------------------------------------------------------
# Phase 2 — GSC OAuth
# ---------------------------------------------------------------------------

def _gsc_redirect_uri() -> str:
    return os.environ.get(
        "GSC_REDIRECT_URI",
        "http://localhost:8000/api/gsc/callback",
    )


@app.get("/gsc/connect")
async def gsc_connect(
    domain: str = Query(..., description="Domain to connect, e.g. example.com"),
    x_api_key: str = Header(default=""),
):
    """
    Returns the Google OAuth consent URL as JSON.
    The frontend handles the browser redirect.
    """
    if API_SECRET and x_api_key != API_SECRET:
        raise HTTPException(status_code=401, detail="Invalid API key")

    client = GSCClient()
    if not client.client_id:
        raise HTTPException(status_code=500, detail="GOOGLE_CLIENT_ID not configured")

    auth_url = client.get_authorization_url(
        redirect_uri=_gsc_redirect_uri(),
        state=domain,
    )
    return {"url": auth_url, "domain": domain}


@app.get("/gsc/callback")
async def gsc_callback(
    code: str = Query(...),
    state: str = Query(default=""),
    error: str = Query(default=""),
):
    """
    Google OAuth callback.
    Exchanges code for tokens, lists GSC sites, stores tokens in DB.
    Redirects user back to the frontend after success.
    """
    if error:
        raise HTTPException(status_code=400, detail=f"OAuth error: {error}")

    domain = state  # we set state=domain in /gsc/connect
    client = GSCClient()

    try:
        tokens = await client.exchange_code(code, redirect_uri=_gsc_redirect_uri())
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Token exchange failed: {e}")

    # Ensure company row exists
    company = await upsert_company(domain=domain)
    company_id = company["id"]

    # Find the matching GSC site (prefer sc-domain: prefix for full coverage)
    try:
        sites = await client.list_sites(tokens["access_token"])
    except Exception:
        sites = []

    site_url = _pick_site_url(sites, domain)

    # Store tokens
    await save_gsc_token(
        company_id=company_id,
        access_token=tokens.get("access_token", ""),
        refresh_token=tokens.get("refresh_token", ""),
        token_expiry=tokens.get("expiry"),
        site_url=site_url,
    )

    # Redirect back to frontend dashboard
    frontend = os.environ.get("FRONTEND_URL", "https://engine.hoshloop.com").rstrip("/")
    return RedirectResponse(f"{frontend}/dashboard?gsc=connected&domain={domain}")


# ---------------------------------------------------------------------------
# Phase 2 — Keywords
# ---------------------------------------------------------------------------

class StrikeZoneRequest(BaseModel):
    domain: str
    days: int = 90
    min_pos: float = 5.0
    max_pos: float = 20.0


@app.post("/keywords/strike-zone")
async def keywords_strike_zone(
    req: StrikeZoneRequest,
    x_api_key: str = Header(default=""),
):
    """
    Return strike zone keywords (positions 5–20) for a domain.
    Requires the domain to have GSC connected via /gsc/connect first.
    """
    if API_SECRET and x_api_key != API_SECRET:
        raise HTTPException(status_code=401, detail="Invalid API key")

    company = await get_company(req.domain)
    if not company:
        raise HTTPException(
            status_code=404,
            detail=f"Domain '{req.domain}' not found. Connect GSC first via /gsc/connect.",
        )

    result = await analyze_strike_zone(
        domain=req.domain,
        company_id=company["id"],
        min_pos=req.min_pos,
        max_pos=req.max_pos,
        days=req.days,
    )

    if result.get("error"):
        raise HTTPException(status_code=400, detail=result["error"])

    return result


@app.get("/keywords/trend")
async def keywords_trend(
    domain: str = Query(...),
    keyword: str = Query(...),
    days: int = Query(default=90),
    x_api_key: str = Header(default=""),
):
    """Position trend for a single keyword over time (from DB history)."""
    if API_SECRET and x_api_key != API_SECRET:
        raise HTTPException(status_code=401, detail="Invalid API key")

    return await get_keyword_history(domain=domain, keyword=keyword, days=days)


@app.get("/gsc/sites")
async def gsc_sites(
    domain: str = Query(...),
    x_api_key: str = Header(default=""),
):
    """List all GSC-verified sites for a connected domain."""
    if API_SECRET and x_api_key != API_SECRET:
        raise HTTPException(status_code=401, detail="Invalid API key")

    company = await get_company(domain)
    if not company:
        raise HTTPException(status_code=404, detail="Domain not connected")

    token_row = await get_gsc_token(company["id"])
    if not token_row:
        raise HTTPException(status_code=404, detail="GSC not connected for this domain")

    client = GSCClient()
    access_token = await client.get_valid_token(token_row)
    sites = await client.list_sites(access_token)
    return {"domain": domain, "sites": sites}


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------

def _pick_site_url(sites: list[dict], domain: str) -> str:
    """
    Choose the best GSC site URL for a domain.
    Prefers sc-domain: (covers all protocols) over https:// or http://.
    """
    sc_domain = f"sc-domain:{domain}"
    for s in sites:
        if s["site_url"] == sc_domain:
            return sc_domain

    for prefix in (f"https://{domain}/", f"http://{domain}/",
                   f"https://www.{domain}/", f"http://www.{domain}/"):
        for s in sites:
            if s["site_url"] == prefix:
                return prefix

    # Fallback: use sc-domain format even if not verified yet
    return sc_domain


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("api.main:app", host="0.0.0.0", port=port, reload=True)
