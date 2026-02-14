"""
Hoshloop SEO Engine — FastAPI Backend

Endpoints:
  POST /audit          — Run a full SEO audit (returns JSON results)
  GET  /health         — Health check
"""

import os
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Header
from pydantic import BaseModel, HttpUrl

from .engine import run_audit

load_dotenv()

API_SECRET = os.environ.get("API_SECRET_KEY", "")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("WARNING: ANTHROPIC_API_KEY not set. E-E-A-T analysis will be skipped.")
    yield
    # Shutdown


app = FastAPI(
    title="Hoshloop SEO Engine",
    version="1.0.0",
    lifespan=lifespan,
)


class AuditRequest(BaseModel):
    url: HttpUrl


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

    try:
        results = await run_audit(url)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Audit failed: {str(e)}")

    return results


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("api.main:app", host="0.0.0.0", port=port, reload=True)
