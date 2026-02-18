"""
Main audit engine — orchestrates fetch, parse, analyze, score.
"""

import time

from .fetcher import fetch_page
from .parser import parse_html
from .scorer import build_results
from .analyzers import technical, content, onpage, schema_analyzer, performance, images, geo


async def run_audit(url: str, competitor_url: str | None = None, on_progress=None) -> dict:
    """
    Run a full SEO audit on the given URL.

    Args:
        url: The URL to audit
        competitor_url: Optional competitor URL for GEO comparison
        on_progress: Optional callback(step: str, progress: int)

    Returns:
        Complete AuditResults dict
    """
    start = time.time()

    # Phase 1: Fetch
    if on_progress:
        await on_progress("Fetching page...", 5)

    fetch_result = await fetch_page(url)

    if fetch_result.get("error"):
        return {
            "error": fetch_result["error"],
            "url": url,
            "overallScore": 0,
            "categories": [],
            "topFixes": [],
        }

    # Fetch competitor in parallel if provided
    competitor_fetch = None
    competitor_parsed = None
    if competitor_url:
        competitor_fetch = await fetch_page(competitor_url)
        if not competitor_fetch.get("error"):
            competitor_parsed = parse_html(
                competitor_fetch["html"],
                base_url=competitor_fetch.get("final_url", competitor_url),
            )
        else:
            competitor_fetch = None

    if on_progress:
        await on_progress("Parsing HTML...", 15)

    # Phase 2: Parse
    parsed = parse_html(
        fetch_result["html"],
        base_url=fetch_result.get("final_url", url),
    )

    if on_progress:
        await on_progress("Analyzing technical SEO...", 25)

    # Phase 3: Analyze all 7 categories
    tech_result = technical.analyze(parsed, fetch_result)

    if on_progress:
        await on_progress("Analyzing content quality (AI-powered)...", 35)

    content_result = await content.analyze(parsed, fetch_result)

    if on_progress:
        await on_progress("Analyzing on-page SEO...", 55)

    onpage_result = onpage.analyze(parsed, fetch_result)

    if on_progress:
        await on_progress("Analyzing structured data...", 65)

    schema_result = schema_analyzer.analyze(parsed, fetch_result)

    if on_progress:
        await on_progress("Analyzing performance...", 75)

    perf_result = performance.analyze(parsed, fetch_result)

    if on_progress:
        await on_progress("Analyzing images...", 85)

    images_result = images.analyze(parsed, fetch_result)

    if on_progress:
        await on_progress("Analyzing AI search visibility...", 90)

    geo_result = await geo.analyze(parsed, fetch_result, competitor_parsed, competitor_fetch)

    if on_progress:
        await on_progress("Generating report...", 95)

    # Phase 4: Score & aggregate
    categories = [
        tech_result,
        content_result,
        onpage_result,
        schema_result,
        perf_result,
        images_result,
        geo_result,
    ]

    duration_ms = int((time.time() - start) * 1000)

    results = build_results(
        categories=categories,
        url=fetch_result.get("final_url", url),
        title=parsed.get("title"),
        meta_description=parsed.get("meta_description"),
        duration_ms=duration_ms,
    )

    if on_progress:
        await on_progress("Complete", 100)

    return results
