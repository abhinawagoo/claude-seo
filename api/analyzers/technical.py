"""Technical SEO analyzer — 25% weight."""


SECURITY_HEADERS = [
    ("content-security-policy", 2, "low"),
    ("strict-transport-security", 3, "medium"),
    ("x-frame-options", 2, "low"),
    ("x-content-type-options", 2, "low"),
    ("referrer-policy", 2, "low"),
]

AI_CRAWLERS = {
    "GPTBot": "OpenAI",
    "ClaudeBot": "Anthropic",
    "PerplexityBot": "Perplexity",
    "Google-Extended": "Google AI",
}


def analyze(parsed: dict, fetch_result: dict) -> dict:
    score = 100
    issues = []

    def issue(id, sev, title, desc, rec, impact, pts):
        nonlocal score
        score = max(0, score - pts)
        issues.append({
            "id": id, "category": "technical", "severity": sev,
            "title": title, "description": desc,
            "recommendation": rec, "impact": impact,
        })

    # Title
    title = parsed.get("title")
    if not title:
        issue("tech-no-title", "critical", "Missing title tag",
              "No <title> tag found.", "Add a descriptive title tag (30-60 chars).",
              "Major ranking factor", 15)
    elif len(title) < 30:
        issue("tech-short-title", "high", "Title tag too short",
              f"Title is {len(title)} chars (min 30).",
              "Expand title to 30-60 characters.", "Reduced CTR", 8)
    elif len(title) > 60:
        issue("tech-long-title", "medium", "Title tag too long",
              f"Title is {len(title)} chars (max 60). Google will truncate.",
              "Shorten to under 60 characters.", "Truncated in SERPs", 5)

    # Meta description
    desc = parsed.get("meta_description")
    if not desc:
        issue("tech-no-meta-desc", "high", "Missing meta description",
              "No meta description found.",
              "Add a compelling meta description (120-160 chars).",
              "Lower CTR from search results", 10)
    elif len(desc) < 120:
        issue("tech-short-meta-desc", "medium", "Meta description too short",
              f"Meta description is {len(desc)} chars (min 120).",
              "Expand to 120-160 characters.", "Missed CTR opportunity", 5)
    elif len(desc) > 160:
        issue("tech-long-meta-desc", "low", "Meta description too long",
              f"Meta description is {len(desc)} chars (max 160).",
              "Shorten to under 160 characters.", "Truncated in SERPs", 3)

    # Canonical
    if not parsed.get("canonical"):
        issue("tech-no-canonical", "high", "Missing canonical tag",
              "No canonical URL specified.",
              "Add <link rel='canonical'> to prevent duplicate content.",
              "Duplicate content risk", 8)

    # Meta robots
    robots = parsed.get("meta_robots") or ""
    if "noindex" in robots.lower():
        issue("tech-noindex", "critical", "Page blocked from indexing",
              "Meta robots contains 'noindex'.",
              "Remove noindex if this page should appear in search.",
              "Page invisible to search engines", 20)

    # Viewport
    if not parsed.get("viewport"):
        issue("tech-no-viewport", "high", "Missing viewport meta tag",
              "No viewport meta tag found.",
              "Add <meta name='viewport' content='width=device-width, initial-scale=1'>.",
              "Mobile usability issues", 10)

    # HTTPS
    final_url = fetch_result.get("final_url", "")
    if final_url.startswith("http://"):
        issue("tech-no-https", "critical", "Not using HTTPS",
              "Site is served over HTTP.",
              "Migrate to HTTPS. It's a confirmed ranking signal.",
              "Security + ranking penalty", 15)

    # Security headers
    headers = fetch_result.get("headers", {})
    headers_lower = {k.lower(): v for k, v in headers.items()}
    for header_name, pts, sev in SECURITY_HEADERS:
        if header_name not in headers_lower:
            issue(f"tech-no-{header_name}", sev,
                  f"Missing {header_name} header",
                  f"The {header_name} security header is not set.",
                  f"Add {header_name} header for better security.",
                  "Security vulnerability", pts)

    # robots.txt
    if not fetch_result.get("robots_txt"):
        issue("tech-no-robots", "medium", "Missing robots.txt",
              "No robots.txt file found.",
              "Create a robots.txt to guide crawlers.",
              "No crawl guidance", 5)

    # Sitemap
    if not fetch_result.get("sitemap_xml"):
        issue("tech-no-sitemap", "medium", "Missing XML sitemap",
              "No sitemap.xml found at the root.",
              "Create and submit an XML sitemap.",
              "Slower page discovery", 5)

    # Redirect chain
    chain = fetch_result.get("redirect_chain", [])
    if len(chain) > 1:
        issue("tech-redirect-chain", "medium", "Redirect chain detected",
              f"{len(chain)} redirects before reaching the page.",
              "Reduce to a single redirect.",
              "Crawl budget waste", 5)

    # AI crawler access (informational)
    robots_txt = fetch_result.get("robots_txt") or ""
    blocked_crawlers = []
    for crawler, org in AI_CRAWLERS.items():
        if f"User-agent: {crawler}" in robots_txt and "Disallow: /" in robots_txt:
            blocked_crawlers.append(f"{crawler} ({org})")
    if blocked_crawlers:
        issues.append({
            "id": "tech-ai-crawlers-blocked", "category": "technical",
            "severity": "low",
            "title": "AI crawlers blocked in robots.txt",
            "description": f"Blocked: {', '.join(blocked_crawlers)}",
            "recommendation": "Consider allowing AI crawlers for visibility in AI search.",
            "impact": "Reduced AI search visibility",
        })

    return {
        "name": "technical",
        "label": "Technical SEO",
        "score": max(0, score),
        "weight": 0.25,
        "issues": issues,
        "summary": f"Technical SEO score: {max(0, score)}/100 with {len(issues)} issues found.",
    }
