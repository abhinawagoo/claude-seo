"""On-Page SEO analyzer — 20% weight."""

from urllib.parse import urlparse


def analyze(parsed: dict, fetch_result: dict) -> dict:
    score = 100
    issues = []

    def issue(id, sev, title, desc, rec, impact, pts):
        nonlocal score
        score = max(0, score - pts)
        issues.append({
            "id": id, "category": "onpage", "severity": sev,
            "title": title, "description": desc,
            "recommendation": rec, "impact": impact,
        })

    # H1
    h1_count = len(parsed.get("h1", []))
    if h1_count == 0:
        issue("onpage-no-h1", "critical", "Missing H1 tag",
              "No H1 heading found on the page.",
              "Add a single, descriptive H1 tag.",
              "Primary on-page ranking signal", 15)
    elif h1_count > 1:
        issue("onpage-multiple-h1", "medium", "Multiple H1 tags",
              f"Found {h1_count} H1 tags. Use only one per page.",
              "Keep one H1 and convert others to H2.",
              "Dilutes heading hierarchy", 6)

    # Heading hierarchy
    has_h2 = bool(parsed.get("h2"))
    has_h3 = bool(parsed.get("h3"))
    has_h4 = bool(parsed.get("h4"))
    if has_h3 and not has_h2:
        issue("onpage-skip-h2", "medium", "H3 used without H2",
              "H3 headings found but no H2. Heading hierarchy is broken.",
              "Add H2 headings before H3.", "Poor document structure", 5)
    if has_h4 and not has_h3:
        issue("onpage-skip-h3", "low", "H4 used without H3",
              "Heading levels skipped.", "Maintain proper heading hierarchy.",
              "Minor structure issue", 3)

    # Internal links
    internal_links = parsed.get("links", {}).get("internal", [])
    if not internal_links:
        issue("onpage-no-internal-links", "high", "No internal links",
              "Page has zero internal links.",
              "Add 3-5 internal links to related pages.",
              "Poor crawlability and link equity distribution", 10)
    elif len(internal_links) < 3:
        issue("onpage-few-internal-links", "medium", "Few internal links",
              f"Only {len(internal_links)} internal links (recommended: 3-5).",
              "Add more contextual internal links.",
              "Suboptimal link equity", 5)

    # URL structure
    url = fetch_result.get("final_url", "")
    parsed_url = urlparse(url)
    path = parsed_url.path

    if len(path) > 100:
        issue("onpage-long-url", "low", "URL path too long",
              f"Path is {len(path)} characters.",
              "Use shorter, descriptive URLs.", "Hard to share", 3)

    if path != path.lower():
        issue("onpage-uppercase-url", "low", "URL contains uppercase letters",
              "URLs should be lowercase to avoid duplicate content.",
              "Use lowercase URLs.", "Duplicate content risk", 2)

    if "_" in path:
        issue("onpage-underscore-url", "low", "URL uses underscores",
              "Google treats underscores as word joiners, not separators.",
              "Use hyphens (-) instead of underscores (_).",
              "Minor SEO impact", 2)

    # Open Graph
    og = parsed.get("open_graph", {})
    missing_og = []
    if "og:title" not in og:
        missing_og.append("og:title")
    if "og:description" not in og:
        missing_og.append("og:description")
    if "og:image" not in og:
        missing_og.append("og:image")
    if missing_og:
        issue("onpage-missing-og", "medium", "Incomplete Open Graph tags",
              f"Missing: {', '.join(missing_og)}.",
              "Add all Open Graph tags for proper social sharing.",
              "Poor social sharing appearance", 5)

    # Twitter Card
    if "twitter:card" not in parsed.get("twitter_card", {}):
        issue("onpage-no-twitter-card", "low", "Missing Twitter Card",
              "No twitter:card meta tag found.",
              "Add <meta name='twitter:card' content='summary_large_image'>.",
              "Poor X/Twitter sharing", 3)

    # Language attribute
    if not parsed.get("language"):
        issue("onpage-no-lang", "medium", "Missing language attribute",
              "No lang attribute on <html> tag.",
              "Add lang='en' (or appropriate language) to the <html> tag.",
              "Helps search engines determine content language", 4)

    return {
        "name": "onpage",
        "label": "On-Page SEO",
        "score": max(0, score),
        "weight": 0.20,
        "issues": issues,
        "summary": f"On-page score: {max(0, score)}/100.",
    }
