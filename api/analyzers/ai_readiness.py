"""AI Search Readiness (GEO) analyzer — 5% weight."""

import re


def analyze(parsed: dict, fetch_result: dict) -> dict:
    score = 100
    issues = []

    def issue(id, sev, title, desc, rec, impact, pts):
        nonlocal score
        score = max(0, score - pts)
        issues.append({
            "id": id, "category": "ai-readiness", "severity": sev,
            "title": title, "description": desc,
            "recommendation": rec, "impact": impact,
        })

    # llms.txt
    llms_txt = fetch_result.get("llms_txt")
    if not llms_txt:
        issue("ai-no-llms-txt", "medium", "No llms.txt file",
              "No llms.txt found. This emerging standard helps AI crawlers understand your site.",
              "Create a /llms.txt file describing your site for AI systems.",
              "Reduced AI search visibility", 15)
    elif len(llms_txt.strip()) < 50:
        issue("ai-thin-llms-txt", "low", "llms.txt too thin",
              "llms.txt exists but has very little content.",
              "Expand llms.txt with a proper site description.",
              "Weak AI signal", 5)

    # AI crawler access
    robots_txt = fetch_result.get("robots_txt") or ""
    key_crawlers = ["GPTBot", "ClaudeBot", "PerplexityBot"]
    blocked = []

    for crawler in key_crawlers:
        # Simple check: look for User-agent: <crawler> followed by Disallow: /
        pattern = rf"User-agent:\s*{crawler}.*?Disallow:\s*/\s*$"
        if re.search(pattern, robots_txt, re.IGNORECASE | re.MULTILINE):
            blocked.append(crawler)

    if blocked:
        issue("ai-crawlers-blocked", "medium", "AI crawlers blocked",
              f"Blocked in robots.txt: {', '.join(blocked)}. AI search grew 527% in 2025.",
              "Allow GPTBot, ClaudeBot, PerplexityBot to crawl your site.",
              "Invisible to AI-powered search", 15)

    # Wildcard block check
    wildcard_block = bool(re.search(
        r"User-agent:\s*\*\s*\n\s*Disallow:\s*/\s*$",
        robots_txt, re.MULTILINE
    ))
    if wildcard_block and not blocked:
        issue("ai-wildcard-block", "high", "All bots blocked via wildcard",
              "robots.txt blocks all crawlers with 'Disallow: /'.",
              "Allow specific crawlers or remove the wildcard block.",
              "Completely invisible to all search engines", 20)

    # Citable passage structure
    body_text = parsed.get("body_text", "")
    paragraphs = [p.strip() for p in body_text.split("\n") if p.strip()]
    citable_count = 0
    for p in paragraphs:
        words = len(p.split())
        if 50 <= words <= 200:
            citable_count += 1

    if not citable_count and len(body_text.split()) > 200:
        issue("ai-no-citable", "medium", "No citable passages",
              "No paragraphs in the 50-200 word sweet spot for AI citations.",
              "Structure content with 50-200 word paragraphs (optimal: 134-167 words).",
              "AI systems prefer well-structured passages for citations", 10)

    # Question-based headings
    all_headings = []
    for level in range(1, 7):
        all_headings.extend(parsed.get(f"h{level}", []))

    word_count = parsed.get("word_count", 0)
    question_headings = [
        h for h in all_headings
        if any(h.lower().startswith(q) for q in ("what ", "how ", "why ", "when ", "where ", "which ", "who "))
        or h.endswith("?")
    ]
    if not question_headings and word_count > 500:
        issue("ai-no-question-headings", "low", "No question-based headings",
              "No headings match common query patterns (What, How, Why...).",
              "Add question-based H2/H3 headings that match AI query patterns.",
              "Lower AI Overviews citation chance", 5)

    # Article schema for AI
    schemas = parsed.get("schema", [])
    has_article = any(
        isinstance(s, dict) and s.get("@type") in ("Article", "BlogPosting", "NewsArticle")
        for s in schemas
    )
    if not has_article and word_count > 500:
        issue("ai-no-article-schema", "low", "No Article schema for long content",
              "Pages with 500+ words benefit from Article/BlogPosting schema for AI systems.",
              "Add Article or BlogPosting JSON-LD schema.",
              "Helps AI parse and attribute content", 5)

    # Direct answer patterns
    opening = body_text[:500].lower() if body_text else ""
    has_direct_answer = any(
        pattern in opening
        for pattern in [" is ", " refers to ", " defined as ", " means ", " are "]
    )
    if not has_direct_answer and word_count > 300:
        issue("ai-no-direct-answer", "low", "No direct answer pattern",
              "Opening content doesn't include direct definitions.",
              "Start with 'X is...' or 'X refers to...' patterns. AI prefers direct definitions early.",
              "Lower citation priority", 3)

    return {
        "name": "ai-readiness",
        "label": "AI Search Readiness",
        "score": max(0, score),
        "weight": 0.05,
        "issues": issues,
        "summary": f"AI readiness score: {max(0, score)}/100.",
    }
