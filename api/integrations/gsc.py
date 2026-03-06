"""
Google Search Console (GSC) integration — Hoshloop SEO Growth Platform

Handles:
  - OAuth 2.0 flow (authorization URL → code exchange → token storage)
  - Token refresh (access tokens expire after 1 hour)
  - Search Analytics queries (positions, clicks, impressions)
  - Strike zone keyword extraction (positions 5–20)
  - Position trend tracking per keyword

Setup:
  1. Create a project at console.cloud.google.com
  2. Enable the "Google Search Console API"
  3. Create OAuth 2.0 credentials (Web application)
  4. Add your redirect URI (e.g. https://engine.hoshloop.com/api/gsc/callback)
  5. Set GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET env vars

Scopes: webmasters.readonly (read-only, no write access to the site)
"""

import os
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode
from typing import Optional

import httpx


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

AUTH_URI = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URI = "https://oauth2.googleapis.com/token"
REVOKE_URI = "https://oauth2.googleapis.com/revoke"
WEBMASTERS_BASE = "https://www.googleapis.com/webmasters/v3"

SCOPES = [
    "https://www.googleapis.com/auth/webmasters.readonly",
    "openid",
    "email",
]


class GSCError(Exception):
    """Raised when the GSC API returns an error."""


# ---------------------------------------------------------------------------
# OAuth flow helpers (stateless — tokens are stored in DB by the caller)
# ---------------------------------------------------------------------------

class GSCClient:
    """
    Google Search Console client.

    Usage:
        client = GSCClient()

        # Step 1 — send user to this URL
        url = client.get_authorization_url(state="company_42")

        # Step 2 — on callback, exchange code for tokens
        tokens = await client.exchange_code(code, redirect_uri)

        # Step 3 — use access_token to call the API
        sites = await client.list_sites(tokens["access_token"])

        # Step 4 — refresh when expired
        new_tokens = await client.refresh_token(tokens["refresh_token"])
    """

    def __init__(self):
        self.client_id = os.environ.get("GOOGLE_CLIENT_ID", "")
        self.client_secret = os.environ.get("GOOGLE_CLIENT_SECRET", "")

    def get_authorization_url(
        self,
        redirect_uri: str,
        state: str = "",
    ) -> str:
        """
        Build the Google OAuth consent page URL.
        Redirect the user's browser here to begin the auth flow.
        """
        params = {
            "client_id": self.client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": " ".join(SCOPES),
            "access_type": "offline",     # get refresh_token
            "prompt": "consent",          # always show consent (ensures refresh_token)
            "state": state,
        }
        return f"{AUTH_URI}?{urlencode(params)}"

    async def exchange_code(
        self, code: str, redirect_uri: str
    ) -> dict:
        """
        Exchange an authorization code for access + refresh tokens.

        Returns:
          {
            "access_token": "...",
            "refresh_token": "...",
            "expires_in": 3599,
            "token_type": "Bearer",
            "expiry": datetime  (UTC)
          }
        """
        payload = {
            "code": code,
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "redirect_uri": redirect_uri,
            "grant_type": "authorization_code",
        }
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(TOKEN_URI, data=payload)
            resp.raise_for_status()
            data = resp.json()

        if "error" in data:
            raise GSCError(f"Token exchange failed: {data['error']} — {data.get('error_description', '')}")

        expiry = datetime.now(timezone.utc) + timedelta(seconds=data.get("expires_in", 3600))
        data["expiry"] = expiry
        return data

    async def refresh_token(self, refresh_token: str) -> dict:
        """
        Use a refresh_token to get a new access_token.

        Returns: { "access_token", "expires_in", "expiry" }
        """
        payload = {
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "refresh_token": refresh_token,
            "grant_type": "refresh_token",
        }
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(TOKEN_URI, data=payload)
            resp.raise_for_status()
            data = resp.json()

        if "error" in data:
            raise GSCError(f"Token refresh failed: {data['error']}")

        expiry = datetime.now(timezone.utc) + timedelta(seconds=data.get("expires_in", 3600))
        data["expiry"] = expiry
        return data

    # ------------------------------------------------------------------
    # Token management helper
    # ------------------------------------------------------------------

    async def get_valid_token(self, stored_token: dict) -> str:
        """
        Returns a valid access token, refreshing if expired.

        stored_token: dict from DB (has access_token, refresh_token, token_expiry)
        Returns the access_token string.
        """
        expiry = stored_token.get("token_expiry")
        if isinstance(expiry, str):
            expiry = datetime.fromisoformat(expiry)

        # Refresh if expiry is unknown or within 5 minutes
        needs_refresh = expiry is None or expiry <= datetime.now(timezone.utc) + timedelta(minutes=5)

        if needs_refresh:
            new_tokens = await self.refresh_token(stored_token["refresh_token"])
            return new_tokens["access_token"]

        return stored_token["access_token"]

    # ------------------------------------------------------------------
    # GSC API calls
    # ------------------------------------------------------------------

    async def list_sites(self, access_token: str) -> list[dict]:
        """
        List all sites verified in Google Search Console for this account.

        Each item: { site_url, permission_level }
        """
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(
                f"{WEBMASTERS_BASE}/sites",
                headers={"Authorization": f"Bearer {access_token}"},
            )
            _raise_for_gsc_error(resp)
            data = resp.json()

        return [
            {
                "site_url": s.get("siteUrl", ""),
                "permission_level": s.get("permissionLevel", ""),
            }
            for s in data.get("siteEntry", [])
        ]

    async def query_search_analytics(
        self,
        access_token: str,
        site_url: str,
        start_date: str,          # "YYYY-MM-DD"
        end_date: str,            # "YYYY-MM-DD"
        dimensions: list[str],    # e.g. ["query", "page"]
        row_limit: int = 1000,
        filters: Optional[list[dict]] = None,
        data_state: str = "final",
    ) -> list[dict]:
        """
        Query the Search Analytics API.

        Dimensions available: query, page, country, device, date, searchAppearance
        Each result row: { keys: [...], clicks, impressions, ctr, position }
        """
        body: dict = {
            "startDate": start_date,
            "endDate": end_date,
            "dimensions": dimensions,
            "rowLimit": min(row_limit, 25000),
            "dataState": data_state,
        }
        if filters:
            body["dimensionFilterGroups"] = [{"filters": filters}]

        encoded_site = _encode_site_url(site_url)
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"{WEBMASTERS_BASE}/sites/{encoded_site}/searchAnalytics/query",
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Content-Type": "application/json",
                },
                json=body,
            )
            _raise_for_gsc_error(resp)
            data = resp.json()

        rows = data.get("rows", [])
        result = []
        for row in rows:
            keys = row.get("keys", [])
            entry = {
                "clicks": row.get("clicks", 0),
                "impressions": row.get("impressions", 0),
                "ctr": round(row.get("ctr", 0) * 100, 2),      # as %
                "position": round(row.get("position", 0), 1),
            }
            for i, dim in enumerate(dimensions):
                if i < len(keys):
                    entry[dim] = keys[i]
            result.append(entry)
        return result

    # ------------------------------------------------------------------
    # High-level helpers
    # ------------------------------------------------------------------

    async def get_strike_zone_keywords(
        self,
        access_token: str,
        site_url: str,
        days: int = 90,
        min_pos: float = 5.0,
        max_pos: float = 20.0,
        min_impressions: int = 50,
    ) -> list[dict]:
        """
        Return keywords ranking at positions 5–20 with meaningful search volume.
        These are the 'one good article away from page 1' opportunities.

        Results sorted by impressions descending (highest opportunity first).
        """
        end_date = _today()
        start_date = _days_ago(days)

        rows = await self.query_search_analytics(
            access_token=access_token,
            site_url=site_url,
            start_date=start_date,
            end_date=end_date,
            dimensions=["query", "page"],
            row_limit=5000,
        )

        strike_zone = [
            r for r in rows
            if min_pos <= r["position"] <= max_pos
            and r["impressions"] >= min_impressions
        ]

        return sorted(strike_zone, key=lambda r: r["impressions"], reverse=True)

    async def get_all_ranked_keywords(
        self,
        access_token: str,
        site_url: str,
        days: int = 90,
    ) -> list[dict]:
        """
        All keywords the site has impressions for over the last N days.
        """
        end_date = _today()
        start_date = _days_ago(days)

        return await self.query_search_analytics(
            access_token=access_token,
            site_url=site_url,
            start_date=start_date,
            end_date=end_date,
            dimensions=["query"],
            row_limit=10000,
        )

    async def get_keyword_trend(
        self,
        access_token: str,
        site_url: str,
        keyword: str,
        days: int = 90,
    ) -> list[dict]:
        """
        Daily position trend for a specific keyword over the last N days.
        Returns list of { date, position, clicks, impressions }.
        """
        end_date = _today()
        start_date = _days_ago(days)

        filters = [
            {
                "dimension": "query",
                "operator": "equals",
                "expression": keyword,
            }
        ]

        return await self.query_search_analytics(
            access_token=access_token,
            site_url=site_url,
            start_date=start_date,
            end_date=end_date,
            dimensions=["date"],
            filters=filters,
            row_limit=days + 10,
        )

    async def get_top_pages(
        self,
        access_token: str,
        site_url: str,
        days: int = 30,
        limit: int = 50,
    ) -> list[dict]:
        """
        Top-performing pages by clicks over the last N days.
        Useful for identifying what content is already working.
        """
        end_date = _today()
        start_date = _days_ago(days)

        rows = await self.query_search_analytics(
            access_token=access_token,
            site_url=site_url,
            start_date=start_date,
            end_date=end_date,
            dimensions=["page"],
            row_limit=limit,
        )
        return sorted(rows, key=lambda r: r["clicks"], reverse=True)

    async def get_declining_keywords(
        self,
        access_token: str,
        site_url: str,
        compare_days: int = 28,
    ) -> list[dict]:
        """
        Keywords whose average position has declined (number increased) recently.
        Compares last 28 days vs. the 28 days before that.

        Each result: { query, recent_position, previous_position, delta }
        """
        end_date = _today()
        mid_date = _days_ago(compare_days)
        start_date = _days_ago(compare_days * 2)

        recent, previous = await _gather(
            self.query_search_analytics(
                access_token=access_token,
                site_url=site_url,
                start_date=mid_date,
                end_date=end_date,
                dimensions=["query"],
                row_limit=5000,
            ),
            self.query_search_analytics(
                access_token=access_token,
                site_url=site_url,
                start_date=start_date,
                end_date=mid_date,
                dimensions=["query"],
                row_limit=5000,
            ),
        )

        recent_map = {r["query"]: r["position"] for r in recent}
        results = []
        for row in previous:
            q = row["query"]
            if q in recent_map:
                delta = recent_map[q] - row["position"]   # positive = dropped
                if delta > 1.0:
                    results.append(
                        {
                            "query": q,
                            "recent_position": recent_map[q],
                            "previous_position": row["position"],
                            "delta": round(delta, 1),
                            "impressions": row["impressions"],
                        }
                    )
        return sorted(results, key=lambda r: r["delta"], reverse=True)


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------

def _today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _days_ago(n: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=n)).strftime("%Y-%m-%d")


def _encode_site_url(site_url: str) -> str:
    """URL-encode the site_url for use in API paths (GSC requires this)."""
    from urllib.parse import quote
    return quote(site_url, safe="")


def _raise_for_gsc_error(resp: httpx.Response):
    if resp.status_code == 401:
        raise GSCError("GSC API: Unauthorized — token may be expired or revoked")
    if resp.status_code == 403:
        raise GSCError("GSC API: Forbidden — user has no access to this site")
    if resp.status_code == 429:
        raise GSCError("GSC API: Rate limited — too many requests")
    if resp.status_code >= 400:
        try:
            detail = resp.json().get("error", {}).get("message", resp.text)
        except Exception:
            detail = resp.text
        raise GSCError(f"GSC API error {resp.status_code}: {detail}")


async def _gather(*coros):
    """Run multiple coroutines concurrently."""
    import asyncio
    return await asyncio.gather(*coros)
