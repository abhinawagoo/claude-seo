"""
Strike Zone Keywords Analyzer — Hoshloop SEO Growth Platform

Finds keywords at positions 5–20 (one good article away from page 1).
Primary source: Google Search Console (real data, free).
Optional enrichment: DataForSEO (volume estimates, competitor comparison).

Workflow:
  1. Pull GSC data for the domain (positions + clicks + impressions)
  2. Filter to strike zone (positions 5–20, meaningful impressions)
  3. Detect trends: climbing vs. dropping vs. stable
  4. Optional: enrich with DataForSEO search volumes
  5. Save snapshot to keyword_positions table
  6. Return prioritised opportunity report
"""

import asyncio
import os
from datetime import datetime, timezone
from urllib.parse import urlparse

from ..db import (
    save_keyword_positions,
    get_strike_zone_keywords as db_strike_zone,
    get_keyword_trend,
    get_climbing_keywords,
    get_gsc_token,
    get_company,
    upsert_company,
)
from ..integrations.gsc import GSCClient


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

async def analyze_strike_zone(
    domain: str,
    company_id: int,
    min_pos: float = 5.0,
    max_pos: float = 20.0,
    days: int = 90,
    save_snapshot: bool = True,
) -> dict:
    """
    Run strike zone analysis for a domain.

    Returns a full opportunity report with:
      - Strike zone keywords (5–20)
      - Climbing keywords (moving up)
      - Declining keywords (dropping — need attention)
      - Quick wins (high impressions, near page 1)
      - Content gaps (high impressions, no clicks)
    """
    gsc_client = GSCClient()

    # Get stored GSC token for this company
    token_row = await get_gsc_token(company_id)
    if not token_row:
        return _error("GSC not connected. Connect via /gsc/connect first.")

    # Refresh token if needed
    try:
        access_token = await gsc_client.get_valid_token(token_row)
    except Exception as e:
        return _error(f"GSC token refresh failed: {e}")

    site_url = token_row.get("site_url", f"sc-domain:{domain}")

    # Run GSC queries in parallel
    try:
        strike_zone_rows, declining_rows, top_pages = await asyncio.gather(
            gsc_client.get_strike_zone_keywords(
                access_token=access_token,
                site_url=site_url,
                days=days,
                min_pos=min_pos,
                max_pos=max_pos,
            ),
            gsc_client.get_declining_keywords(
                access_token=access_token,
                site_url=site_url,
                compare_days=28,
            ),
            gsc_client.get_top_pages(
                access_token=access_token,
                site_url=site_url,
                days=30,
            ),
        )
    except Exception as e:
        return _error(f"GSC query failed: {e}")

    # Save snapshot to DB
    if save_snapshot and strike_zone_rows:
        positions_to_save = [
            {
                "keyword": r["query"],
                "position": r["position"],
                "volume": r["impressions"],   # impressions as proxy for volume
                "url": r.get("page", ""),
                "source": "gsc",
            }
            for r in strike_zone_rows
        ]
        try:
            await save_keyword_positions(domain, positions_to_save)
        except Exception:
            pass  # Don't fail the response if DB write fails

    # Also get historical climbing data from DB
    try:
        climbing = await get_climbing_keywords(domain, days=30)
    except Exception:
        climbing = []

    # Process and classify keywords
    quick_wins = _quick_wins(strike_zone_rows)
    content_gaps = _content_gaps(strike_zone_rows)
    by_page = _group_by_page(strike_zone_rows)

    return {
        "domain": domain,
        "analysedAt": datetime.now(timezone.utc).isoformat(),
        "daysAnalysed": days,
        "summary": {
            "strikeZoneCount": len(strike_zone_rows),
            "quickWinsCount": len(quick_wins),
            "contentGapsCount": len(content_gaps),
            "decliningCount": len(declining_rows),
            "climbingCount": len(climbing),
            "totalImpressionOpportunity": sum(r["impressions"] for r in strike_zone_rows),
        },
        "strikeZone": _format_keywords(strike_zone_rows[:50]),
        "quickWins": _format_keywords(quick_wins[:20]),
        "contentGaps": _format_keywords(content_gaps[:20]),
        "declining": [
            {
                "keyword": r["query"],
                "recentPosition": r["recent_position"],
                "previousPosition": r["previous_position"],
                "dropped": r["delta"],
                "impressions": r["impressions"],
            }
            for r in declining_rows[:20]
        ],
        "climbing": [
            {
                "keyword": r["keyword"],
                "from": r["first_pos"],
                "to": r["last_pos"],
                "gained": round(r["delta"], 1),
            }
            for r in climbing[:20]
        ],
        "topPages": [
            {
                "page": r.get("page", ""),
                "clicks": r["clicks"],
                "impressions": r["impressions"],
                "position": r["position"],
            }
            for r in top_pages[:10]
        ],
        "pageOpportunities": by_page[:10],
        "recommendations": _build_recommendations(
            strike_zone_rows, quick_wins, content_gaps, declining_rows
        ),
    }


async def get_keyword_history(domain: str, keyword: str, days: int = 90) -> dict:
    """Return position trend for a single keyword from DB history."""
    trend = await get_keyword_trend(domain, keyword, days)
    if not trend:
        return {"keyword": keyword, "domain": domain, "trend": [], "message": "No history yet"}

    positions = [r["position"] for r in trend if r["position"] is not None]
    return {
        "keyword": keyword,
        "domain": domain,
        "currentPosition": positions[-1] if positions else None,
        "bestPosition": min(positions) if positions else None,
        "worstPosition": max(positions) if positions else None,
        "trend": [
            {
                "date": r["recorded_at"].isoformat() if hasattr(r["recorded_at"], "isoformat") else str(r["recorded_at"]),
                "position": r["position"],
            }
            for r in trend
        ],
    }


# ---------------------------------------------------------------------------
# Classification helpers
# ---------------------------------------------------------------------------

def _quick_wins(rows: list[dict]) -> list[dict]:
    """
    Keywords closest to page 1 with high impressions.
    Position 8–15 + impressions > median = biggest opportunity.
    """
    if not rows:
        return []
    median_impressions = sorted(r["impressions"] for r in rows)[len(rows) // 2]
    return [
        r for r in rows
        if 8 <= r["position"] <= 15
        and r["impressions"] >= median_impressions
    ]


def _content_gaps(rows: list[dict]) -> list[dict]:
    """
    High impression keywords with zero or near-zero clicks.
    Site ranks but the title/meta isn't compelling — fix meta or write dedicated page.
    """
    return [
        r for r in rows
        if r["impressions"] > 100
        and r.get("ctr", 0) < 1.0   # less than 1% CTR
    ]


def _group_by_page(rows: list[dict]) -> list[dict]:
    """
    Group strike zone keywords by the ranking page.
    Pages with many strike zone keywords are highest ROI to update.
    """
    pages: dict[str, dict] = {}
    for r in rows:
        page = r.get("page", "unknown")
        if page not in pages:
            pages[page] = {"page": page, "keywords": [], "totalImpressions": 0}
        pages[page]["keywords"].append(r["query"])
        pages[page]["totalImpressions"] += r["impressions"]

    return sorted(pages.values(), key=lambda p: p["totalImpressions"], reverse=True)


def _format_keywords(rows: list[dict]) -> list[dict]:
    return [
        {
            "keyword": r.get("query", r.get("keyword", "")),
            "position": round(r["position"], 1),
            "impressions": r.get("impressions", r.get("volume", 0)),
            "clicks": r.get("clicks", 0),
            "ctr": r.get("ctr", 0),
            "page": r.get("page", ""),
        }
        for r in rows
    ]


def _build_recommendations(
    strike_zone: list,
    quick_wins: list,
    content_gaps: list,
    declining: list,
) -> list[dict]:
    """Generate prioritised action items from the data."""
    recs = []

    if quick_wins:
        top = quick_wins[0]
        recs.append({
            "priority": "critical",
            "action": "Update existing page for quick win",
            "detail": (
                f'"{top.get("query", top.get("keyword", ""))}" is at position '
                f'{round(top["position"], 0):.0f} with {top["impressions"]:,} impressions. '
                f'Strengthen the title tag, add an FAQ section, and build 2–3 internal links to this page.'
            ),
        })

    if len(strike_zone) > 10:
        recs.append({
            "priority": "high",
            "action": "Create a topic cluster",
            "detail": (
                f"You have {len(strike_zone)} keywords in the strike zone. "
                "Group related ones and create a pillar page with supporting articles — "
                "this lifts all of them simultaneously."
            ),
        })

    if content_gaps:
        top_gap = content_gaps[0]
        recs.append({
            "priority": "high",
            "action": "Fix meta title & description for high-impression pages",
            "detail": (
                f'"{top_gap.get("query", top_gap.get("keyword", ""))}" gets {top_gap["impressions"]:,} impressions '
                f'but only {top_gap.get("ctr", 0):.1f}% CTR. '
                "Rewrite the meta title to be more compelling — you rank but people don't click."
            ),
        })

    if declining:
        top_drop = declining[0]
        recs.append({
            "priority": "high",
            "action": "Recover declining keyword",
            "detail": (
                f'"{top_drop["query"]}" dropped {top_drop["dropped"]:.1f} positions. '
                "Update the page: refresh content, add recent stats, improve E-E-A-T signals."
            ),
        })

    if not recs:
        recs.append({
            "priority": "medium",
            "action": "Start weekly keyword tracking",
            "detail": "Run this analysis weekly to build position history and spot trends early.",
        })

    return recs


def _error(message: str) -> dict:
    return {
        "error": message,
        "strikeZone": [],
        "quickWins": [],
        "declining": [],
        "recommendations": [],
    }
