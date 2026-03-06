"""
DataForSEO REST API client — Hoshloop SEO Growth Platform

Covers:
  - Ranked keywords for a domain (what it ranks for + positions)
  - Keyword position tracking (specific keywords over time)
  - Competitor backlinks (link gap analysis)
  - Domain backlinks (full backlink profile)
  - Unlinked brand mentions (content analysis search)
  - Broken backlinks (link reclamation opportunities)

Auth: HTTP Basic Auth — DATAFORSEO_LOGIN / DATAFORSEO_PASSWORD env vars
Base: https://api.dataforseo.com/v3

Pricing note: DataForSEO charges per task result (~$0.0001–$0.002 each).
  Live endpoints return results immediately; sandbox mode is free.
"""

import os
from base64 import b64encode
from typing import Optional

import httpx

BASE_URL = "https://api.dataforseo.com/v3"


def _auth_header() -> str:
    login = os.environ.get("DATAFORSEO_LOGIN", "")
    password = os.environ.get("DATAFORSEO_PASSWORD", "")
    token = b64encode(f"{login}:{password}".encode()).decode()
    return f"Basic {token}"


def _headers() -> dict:
    return {
        "Authorization": _auth_header(),
        "Content-Type": "application/json",
    }


class DataForSEOError(Exception):
    """Raised when the DataForSEO API returns an error."""


class DataForSEOClient:
    """
    Async DataForSEO client.

    Usage:
        client = DataForSEOClient()
        keywords = await client.get_ranked_keywords("example.com")
    """

    def __init__(self, timeout: int = 30):
        self._timeout = timeout

    async def _post(self, endpoint: str, payload: list[dict]) -> dict:
        """Send a POST request and return the parsed response."""
        url = f"{BASE_URL}/{endpoint}"
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.post(url, headers=_headers(), json=payload)
            resp.raise_for_status()
            data = resp.json()

        if data.get("status_code") not in (20000, None):
            raise DataForSEOError(
                f"DataForSEO error {data.get('status_code')}: {data.get('status_message')}"
            )
        return data

    # ------------------------------------------------------------------
    # Ranked keywords
    # ------------------------------------------------------------------

    async def get_ranked_keywords(
        self,
        domain: str,
        location_code: int = 2840,   # 2840 = United States
        language_code: str = "en",
        limit: int = 1000,
        filters: Optional[list] = None,
    ) -> list[dict]:
        """
        Return all keywords a domain currently ranks for on Google.

        Each result dict:
          keyword, position, search_volume, url, cpc, competition, traffic_cost
        """
        payload = [
            {
                "target": domain,
                "location_code": location_code,
                "language_code": language_code,
                "limit": limit,
                "filters": filters or [],
            }
        ]
        data = await self._post(
            "dataforseo_labs/google/ranked_keywords/live", payload
        )
        results = []
        for task in data.get("tasks", []):
            for item in (task.get("result") or []):
                for kw in (item.get("items") or []):
                    kd = kw.get("keyword_data", {})
                    si = kw.get("ranked_serp_element", {}).get("serp_item", {})
                    kw_info = kd.get("keyword_info", {})
                    results.append(
                        {
                            "keyword": kd.get("keyword", ""),
                            "position": si.get("rank_absolute"),
                            "search_volume": kw_info.get("search_volume", 0),
                            "url": si.get("url", ""),
                            "cpc": kw_info.get("cpc", 0.0),
                            "competition": kw_info.get("competition", 0.0),
                        }
                    )
        return results

    async def get_strike_zone_keywords(
        self,
        domain: str,
        location_code: int = 2840,
        language_code: str = "en",
        min_pos: int = 5,
        max_pos: int = 20,
        min_volume: int = 100,
    ) -> list[dict]:
        """
        Shortcut: ranked keywords filtered to positions 5-20 with meaningful volume.
        These are the 'one good article can push to page 1' opportunities.
        """
        filters = [
            ["ranked_serp_element.serp_item.rank_absolute", ">=", min_pos],
            "and",
            ["ranked_serp_element.serp_item.rank_absolute", "<=", max_pos],
            "and",
            ["keyword_data.keyword_info.search_volume", ">=", min_volume],
        ]
        keywords = await self.get_ranked_keywords(
            domain=domain,
            location_code=location_code,
            language_code=language_code,
            filters=filters,
            limit=500,
        )
        # Sort by volume desc so highest-opportunity keywords come first
        return sorted(keywords, key=lambda k: k.get("search_volume", 0), reverse=True)

    # ------------------------------------------------------------------
    # Backlinks
    # ------------------------------------------------------------------

    async def get_domain_backlinks(
        self, domain: str, limit: int = 500
    ) -> list[dict]:
        """
        Return backlinks pointing to a domain.

        Each result dict:
          source_url, target_url, anchor, domain_from_rank, dofollow, first_seen
        """
        payload = [
            {
                "target": domain,
                "limit": limit,
                "mode": "as_is",
                "filters": [["dofollow", "=", True]],
                "order_by": ["domain_from_rank,desc"],
                "include_subdomains": True,
            }
        ]
        data = await self._post("backlinks/backlinks/live", payload)
        results = []
        for task in data.get("tasks", []):
            for item in (task.get("result") or []):
                for bl in (item.get("items") or []):
                    results.append(
                        {
                            "source_url": bl.get("url_from", ""),
                            "target_url": bl.get("url_to", ""),
                            "anchor": bl.get("anchor", ""),
                            "domain_authority": bl.get("domain_from_rank", 0),
                            "dofollow": bl.get("dofollow", False),
                            "first_seen": bl.get("first_seen", ""),
                        }
                    )
        return results

    async def get_competitor_backlink_gap(
        self,
        your_domain: str,
        competitor_domain: str,
        limit: int = 500,
    ) -> list[dict]:
        """
        Find domains that link to the competitor but NOT to your domain.
        These are the highest-value link-building targets.

        Returns list of referring domains with authority scores.
        """
        payload = [
            {
                "targets": [your_domain, competitor_domain],
                "limit": limit,
                "mode": "one_per_domain",
                "filters": [
                    ["intersection_count", "=", 1],
                    "and",
                    ["intersection_count_1", "=", 0],   # not linking to you
                ],
                "order_by": ["domain_rank,desc"],
            }
        ]
        data = await self._post("backlinks/domain_intersection/live", payload)
        results = []
        for task in data.get("tasks", []):
            for item in (task.get("result") or []):
                for ref in (item.get("items") or []):
                    results.append(
                        {
                            "referring_domain": ref.get("domain", ""),
                            "domain_authority": ref.get("domain_rank", 0),
                            "backlinks_to_competitor": ref.get("backlinks_count_1", 0),
                            "first_seen": ref.get("first_seen", ""),
                        }
                    )
        return results

    async def find_broken_backlinks(
        self, domain: str, limit: int = 200
    ) -> list[dict]:
        """
        Find URLs on other sites that link to broken pages on your domain.
        These are reclamation opportunities — redirect the broken URL to fix them.

        Each result dict:
          source_url, broken_url, anchor, domain_authority, response_code
        """
        payload = [
            {
                "target": domain,
                "limit": limit,
                "order_by": ["domain_from_rank,desc"],
            }
        ]
        data = await self._post("backlinks/broken_backlinks/live", payload)
        results = []
        for task in data.get("tasks", []):
            for item in (task.get("result") or []):
                for bl in (item.get("items") or []):
                    results.append(
                        {
                            "source_url": bl.get("url_from", ""),
                            "broken_url": bl.get("url_to", ""),
                            "anchor": bl.get("anchor", ""),
                            "domain_authority": bl.get("domain_from_rank", 0),
                            "response_code": bl.get("response_code", 0),
                        }
                    )
        return results

    # ------------------------------------------------------------------
    # Unlinked brand mentions
    # ------------------------------------------------------------------

    async def find_unlinked_mentions(
        self,
        brand_name: str,
        target_domain: str,
        limit: int = 100,
    ) -> list[dict]:
        """
        Find pages that mention the brand by name but don't link to the domain.
        Uses DataForSEO Content Analysis API.

        Each result dict:
          page_url, title, mentions, domain_authority, has_link
        """
        payload = [
            {
                "keyword": brand_name,
                "limit": limit,
                "internal_list_limit": 10,
                "tag": "unlinked_mentions",
                "filters": [
                    ["content_info.connotation_types.positive", ">", 0],
                ],
            }
        ]
        data = await self._post("content_analysis/search/live", payload)
        results = []
        for task in data.get("tasks", []):
            for item in (task.get("result") or []):
                for page in (item.get("items") or []):
                    page_url = page.get("page_url", "")
                    # Skip pages from your own domain
                    if target_domain.lower() in page_url.lower():
                        continue
                    # Check if page already links to target domain
                    links_on_page = page.get("content_info", {}).get("external_links", [])
                    has_link = any(
                        target_domain.lower() in (link or "").lower()
                        for link in links_on_page
                    )
                    results.append(
                        {
                            "page_url": page_url,
                            "title": page.get("title", ""),
                            "mentions": page.get("content_info", {}).get("count", 0),
                            "domain_authority": page.get("domain_rank", 0),
                            "has_link": has_link,
                        }
                    )
        # Only return pages that mention but DON'T link
        return [r for r in results if not r["has_link"]]

    # ------------------------------------------------------------------
    # Keyword volume & ideas
    # ------------------------------------------------------------------

    async def get_keyword_ideas(
        self,
        seed_keywords: list[str],
        location_code: int = 2840,
        language_code: str = "en",
        limit: int = 200,
    ) -> list[dict]:
        """
        Expand a list of seed keywords into related keyword ideas.
        Useful for building topic clusters.

        Each result dict:
          keyword, search_volume, keyword_difficulty, cpc, competition
        """
        payload = [
            {
                "keywords": seed_keywords,
                "location_code": location_code,
                "language_code": language_code,
                "limit": limit,
                "order_by": ["keyword_info.search_volume,desc"],
            }
        ]
        data = await self._post(
            "dataforseo_labs/google/keyword_ideas/live", payload
        )
        results = []
        for task in data.get("tasks", []):
            for item in (task.get("result") or []):
                for kw in (item.get("items") or []):
                    kw_info = kw.get("keyword_info", {})
                    results.append(
                        {
                            "keyword": kw.get("keyword", ""),
                            "search_volume": kw_info.get("search_volume", 0),
                            "keyword_difficulty": kw.get("keyword_properties", {}).get(
                                "keyword_difficulty", 0
                            ),
                            "cpc": kw_info.get("cpc", 0.0),
                            "competition": kw_info.get("competition", 0.0),
                        }
                    )
        return results

    async def get_serp_competitors(
        self,
        domain: str,
        location_code: int = 2840,
        language_code: str = "en",
        limit: int = 20,
    ) -> list[dict]:
        """
        Find domains that compete for the same keywords.
        Useful for identifying who to analyse for backlink gaps.

        Each result dict:
          domain, intersections, avg_position, sum_position, overlap_score
        """
        payload = [
            {
                "target": domain,
                "location_code": location_code,
                "language_code": language_code,
                "limit": limit,
                "order_by": ["intersections,desc"],
            }
        ]
        data = await self._post(
            "dataforseo_labs/google/competitors_domain/live", payload
        )
        results = []
        for task in data.get("tasks", []):
            for item in (task.get("result") or []):
                for comp in (item.get("items") or []):
                    results.append(
                        {
                            "domain": comp.get("domain", ""),
                            "intersections": comp.get("intersections", 0),
                            "avg_position": comp.get("avg_position", 0.0),
                            "sum_position": comp.get("sum_position", 0),
                            "overlap_score": comp.get("se_type", ""),
                        }
                    )
        return results
