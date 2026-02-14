"""
Fetch a web page + supplementary files (robots.txt, sitemap.xml, llms.txt).
Wraps the existing scripts/fetch_page.py logic with async httpx.
"""

import asyncio
from urllib.parse import urlparse

import httpx

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; HoshloopSEO/1.0)",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
    "Accept-Encoding": "gzip, deflate",
    "Connection": "keep-alive",
}

TIMEOUT = 15.0


async def fetch_page(url: str) -> dict:
    """Fetch main page + robots.txt, sitemap.xml, llms.txt in parallel."""
    parsed = urlparse(url)
    if not parsed.scheme:
        url = f"https://{url}"
        parsed = urlparse(url)

    if parsed.scheme not in ("http", "https"):
        return {"error": f"Invalid URL scheme: {parsed.scheme}"}

    origin = f"{parsed.scheme}://{parsed.netloc}"

    result = {
        "url": url,
        "final_url": url,
        "status_code": None,
        "html": None,
        "headers": {},
        "redirect_chain": [],
        "robots_txt": None,
        "sitemap_xml": None,
        "llms_txt": None,
        "error": None,
    }

    async with httpx.AsyncClient(
        headers=HEADERS,
        follow_redirects=True,
        timeout=TIMEOUT,
    ) as client:
        # Fetch main page + supplementary files in parallel
        main_task = client.get(url)
        robots_task = client.get(f"{origin}/robots.txt")
        sitemap_task = client.get(f"{origin}/sitemap.xml")
        llms_task = client.get(f"{origin}/llms.txt")

        responses = await asyncio.gather(
            main_task, robots_task, sitemap_task, llms_task,
            return_exceptions=True,
        )

        # Main page
        main_resp = responses[0]
        if isinstance(main_resp, Exception):
            result["error"] = str(main_resp)
            return result

        result["final_url"] = str(main_resp.url)
        result["status_code"] = main_resp.status_code
        result["html"] = main_resp.text
        result["headers"] = dict(main_resp.headers)
        result["redirect_chain"] = [
            str(r.url) for r in main_resp.history
        ]

        # Supplementary files
        for i, key in enumerate(["robots_txt", "sitemap_xml", "llms_txt"], 1):
            resp = responses[i]
            if not isinstance(resp, Exception) and resp.status_code == 200:
                result[key] = resp.text

    return result
