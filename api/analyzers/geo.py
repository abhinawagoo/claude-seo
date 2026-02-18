"""AI Search (GEO) analyzer — 20% weight.

Replaces the old ai_readiness analyzer with comprehensive GEO scoring:
  A. Citability (25 pts)
  B. Structural Readability (20 pts)
  C. Multi-Modal Content (15 pts)
  D. Authority & Brand Signals (20 pts)
  E. Technical AI Accessibility (20 pts)
  F. AI Query Simulation (enrichment, no deduction)
  G. Competitor Comparison (optional)
"""

import json
import os
import re

import anthropic


# --- AI crawler definitions ---

AI_CRAWLERS = [
    "GPTBot", "ChatGPT-User", "ClaudeBot", "PerplexityBot",
    "Google-Extended", "Amazonbot", "Meta-ExternalAgent",
    "Bytespider", "Applebot-Extended",
]


def _check_crawler_blocked(robots_txt: str, crawler: str) -> bool:
    """Check if a specific crawler is blocked in robots.txt."""
    if not robots_txt:
        return False
    pattern = rf"User-agent:\s*{re.escape(crawler)}.*?Disallow:\s*/\s*$"
    return bool(re.search(pattern, robots_txt, re.IGNORECASE | re.MULTILINE | re.DOTALL))


def _check_wildcard_block(robots_txt: str) -> bool:
    """Check if all bots are blocked via wildcard."""
    if not robots_txt:
        return False
    return bool(re.search(
        r"User-agent:\s*\*\s*\n\s*Disallow:\s*/\s*$",
        robots_txt, re.MULTILINE,
    ))


def _count_citable_passages(paragraphs: list[str]) -> int:
    """Count paragraphs in the 50-200 word sweet spot for AI citations."""
    count = 0
    for p in paragraphs:
        words = len(p.split())
        if 50 <= words <= 200:
            count += 1
    return count


def _avg_paragraph_words(paragraphs: list[str]) -> float:
    """Average word count per paragraph."""
    if not paragraphs:
        return 0
    return sum(len(p.split()) for p in paragraphs) / len(paragraphs)


async def _simulate_ai_queries(body_text: str, url: str, title: str) -> dict | None:
    """Call Claude Haiku to simulate AI search queries for this content."""
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        return None

    words = body_text.split()[:2000]
    truncated = " ".join(words)

    prompt = f"""Analyze this webpage and simulate how AI search engines would use it.

URL: {url}
Title: {title or "N/A"}
Content (truncated): {truncated}

Return ONLY valid JSON:
{{
  "simulatedQueries": [
    {{"query": "example question a user might ask", "citationLikelihood": "high|medium|low", "reason": "brief reason"}},
    {{"query": "...", "citationLikelihood": "...", "reason": "..."}},
    {{"query": "...", "citationLikelihood": "...", "reason": "..."}}
  ],
  "topChange": "The single most impactful change to improve AI citation likelihood",
  "aiVisibilityRating": "high|medium|low"
}}

Generate 3 realistic queries users might ask where this page could be cited. Rate citation likelihood based on content quality, structure, and authority signals."""

    try:
        client = anthropic.AsyncAnthropic(api_key=api_key)
        response = await client.messages.create(
            model="claude-3-5-haiku-latest",
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}],
        )
        text = response.content[0].text.strip()
        if "```" in text:
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
            text = text.strip()
        return json.loads(text)
    except Exception:
        return None


def _run_checks(parsed: dict, fetch_result: dict) -> tuple[int, list, dict]:
    """Run all GEO checks. Returns (score, issues, sub_scores)."""
    score = 100
    issues = []
    sub_scores = {
        "citability": 25,
        "structure": 20,
        "multiModal": 15,
        "authority": 20,
        "technical": 20,
    }

    def issue(id, sev, title, desc, rec, impact, pts, sub_key):
        nonlocal score
        score = max(0, score - pts)
        sub_scores[sub_key] = max(0, sub_scores[sub_key] - pts)
        issues.append({
            "id": id, "category": "geo", "severity": sev,
            "title": title, "description": desc,
            "recommendation": rec, "impact": impact,
        })

    word_count = parsed.get("word_count", 0)
    body_text = parsed.get("body_text", "")
    paragraphs = parsed.get("paragraphs", [])
    robots_txt = fetch_result.get("robots_txt") or ""
    llms_txt = fetch_result.get("llms_txt")

    # ---- A. Citability (25 pts) ----
    citable_count = _count_citable_passages(paragraphs)

    if citable_count == 0 and word_count > 200:
        issue("geo-no-citable-passages", "high",
              "No citable passages",
              "Zero paragraphs in the 50-200 word sweet spot for AI citations.",
              "Structure content with 50-200 word paragraphs (optimal: 134-167 words).",
              "AI systems cannot extract clean citations", 12, "citability")
    elif citable_count < 3 and word_count > 500:
        issue("geo-few-citable-passages", "medium",
              "Few citable passages",
              f"Only {citable_count} passage(s) in the AI-citation sweet spot.",
              "Break content into more 50-200 word paragraphs.",
              "Limited citation opportunities", 6, "citability")

    opening = body_text[:500].lower() if body_text else ""
    has_direct_answer = any(
        pattern in opening
        for pattern in [" is ", " refers to ", " defined as ", " means ", " are "]
    )
    if not has_direct_answer and word_count > 200:
        issue("geo-no-direct-answer", "medium",
              "No direct answer pattern",
              "Opening content doesn't include direct definitions (e.g., 'X is...').",
              "Start with a clear definition. AI search prefers direct answers early.",
              "Lower citation priority", 5, "citability")

    has_statistics = bool(re.search(r"\d+%|\d+\.\d+|\$\d+|[\d,]+\s*(users|customers|companies|revenue|growth)", body_text))
    if not has_statistics and word_count > 200:
        issue("geo-no-statistics", "low",
              "No data points or statistics",
              "No quantitative data found in body content.",
              "Add specific numbers, percentages, or data points to strengthen citations.",
              "Weaker citation authority", 4, "citability")

    # ---- B. Structural Readability (20 pts) ----
    all_headings = []
    for level in range(1, 7):
        all_headings.extend(parsed.get(f"h{level}", []))

    question_headings = [
        h for h in all_headings
        if any(h.lower().startswith(q) for q in ("what ", "how ", "why ", "when ", "where ", "which ", "who "))
        or h.endswith("?")
    ]
    if not question_headings and word_count > 500:
        issue("geo-no-question-headings", "medium",
              "No question-based headings",
              "No headings match AI query patterns (What, How, Why...).",
              "Add question-based H2/H3 headings that match how users ask AI.",
              "Lower AI Overviews citation chance", 6, "structure")

    has_h2 = bool(parsed.get("h2"))
    has_h3 = bool(parsed.get("h3"))
    has_h4 = bool(parsed.get("h4"))
    if (has_h3 and not has_h2) or (has_h4 and not has_h3):
        issue("geo-broken-hierarchy", "medium",
              "Broken heading hierarchy",
              "Heading levels are skipped (e.g., H3 without H2).",
              "Maintain proper H1 → H2 → H3 hierarchy for AI parsing.",
              "AI may misinterpret content structure", 5, "structure")

    lists = parsed.get("lists", {"ul": 0, "ol": 0})
    total_lists = lists.get("ul", 0) + lists.get("ol", 0)
    if total_lists == 0 and word_count > 300:
        issue("geo-no-lists", "low",
              "No list elements",
              "No unordered or ordered lists found.",
              "Use bullet/numbered lists. AI search frequently cites list content.",
              "Missed featured snippet opportunity", 4, "structure")

    avg_para_words = _avg_paragraph_words(paragraphs)
    if avg_para_words > 100 and word_count > 300:
        issue("geo-wall-of-text", "medium",
              "Wall of text detected",
              f"Average paragraph length: {avg_para_words:.0f} words.",
              "Break into shorter paragraphs (50-100 words max).",
              "AI struggles to extract specific claims", 5, "structure")

    # ---- C. Multi-Modal Content (15 pts) ----
    image_count = len(parsed.get("images", []))
    if image_count == 0 and word_count > 300:
        issue("geo-no-images", "medium",
              "No images",
              "Page has no images despite substantial text content.",
              "Add relevant images. Multi-modal pages rank higher in AI results.",
              "Lower engagement and AI ranking signals", 8, "multiModal")

    video_count = len(parsed.get("videos", []))
    if video_count == 0:
        issue("geo-no-video", "low",
              "No video content",
              "No video or video embeds detected.",
              "Consider adding video. AI platforms increasingly surface video content.",
              "Missing multi-modal signal", 4, "multiModal")

    images_without_alt = sum(
        1 for img in parsed.get("images", [])
        if not img.get("alt")
    )
    if image_count > 0 and images_without_alt / image_count > 0.5:
        issue("geo-images-no-alt", "low",
              "Most images lack alt text",
              f"{images_without_alt}/{image_count} images have no alt text.",
              "Add descriptive alt text to all images for AI understanding.",
              "AI cannot understand image content", 3, "multiModal")

    # ---- D. Authority & Brand Signals (20 pts) ----
    schemas = parsed.get("schema", [])

    has_person = any(
        isinstance(s, dict) and s.get("@type") in ("Person", "ProfilePage")
        for s in schemas
    )
    # Also check for author bylines in HTML
    has_byline = bool(re.search(
        r'(rel=["\']author["\']|class=["\'][^"\']*author[^"\']*["\']|itemprop=["\']author["\'])',
        fetch_result.get("html", ""),
        re.IGNORECASE,
    ))
    if not has_person and not has_byline and word_count > 300:
        issue("geo-no-author", "medium",
              "No author attribution",
              "No Person schema or author byline found.",
              "Add author information with Person schema. AI values attributed content.",
              "Weaker E-E-A-T signal for AI", 6, "authority")

    has_dates = any(
        isinstance(s, dict) and (s.get("datePublished") or s.get("dateModified"))
        for s in schemas
    )
    if not has_dates and word_count > 300:
        issue("geo-no-dates", "medium",
              "No publication dates",
              "No datePublished or dateModified in schema.",
              "Add date metadata. AI search prioritizes fresh, dated content.",
              "AI cannot determine content freshness", 5, "authority")

    has_org = any(
        isinstance(s, dict) and s.get("@type") == "Organization"
        for s in schemas
    )
    if not has_org:
        issue("geo-no-org-schema", "low",
              "No Organization schema",
              "No Organization structured data found.",
              "Add Organization JSON-LD to establish brand authority.",
              "Weaker brand signal for AI", 4, "authority")

    external_links = parsed.get("links", {}).get("external", [])
    if len(external_links) < 2 and word_count > 300:
        issue("geo-no-source-citations", "low",
              "Few source citations",
              f"Only {len(external_links)} external link(s). AI values well-sourced content.",
              "Add citations to authoritative sources.",
              "Lower perceived trustworthiness", 3, "authority")

    has_same_as = any(
        isinstance(s, dict) and s.get("sameAs")
        for s in schemas
    )
    if not has_same_as:
        issue("geo-no-same-as", "low",
              "No sameAs in schema",
              "No sameAs property linking to social profiles.",
              "Add sameAs URLs to Organization/Person schema.",
              "Weaker entity recognition", 2, "authority")

    # ---- E. Technical AI Accessibility (20 pts) ----
    if _check_wildcard_block(robots_txt):
        issue("geo-wildcard-block", "critical",
              "All bots blocked via wildcard",
              "robots.txt blocks all crawlers with 'Disallow: /'. Site is invisible to AI search.",
              "Remove the wildcard block or allow specific AI crawlers.",
              "Completely invisible to AI search", 10, "technical")

    blocked_crawlers = [c for c in AI_CRAWLERS if _check_crawler_blocked(robots_txt, c)]
    key_blocked = [c for c in blocked_crawlers if c in ("GPTBot", "ClaudeBot", "PerplexityBot")]
    if key_blocked and not _check_wildcard_block(robots_txt):
        issue("geo-crawlers-blocked", "high",
              "AI crawlers blocked",
              f"Blocked in robots.txt: {', '.join(key_blocked)}.",
              "Allow GPTBot, ClaudeBot, PerplexityBot to crawl your site.",
              "Invisible to major AI search engines", 8, "technical")

    if not llms_txt:
        issue("geo-no-llms-txt", "medium",
              "No llms.txt file",
              "No /llms.txt found. This standard helps AI systems understand your site.",
              "Create a /llms.txt file describing your site for AI systems.",
              "Missed AI discoverability signal", 5, "technical")

    render_blocking = [
        s for s in parsed.get("scripts", [])
        if not s.get("async") and not s.get("defer")
    ]
    if len(render_blocking) > 10:
        issue("geo-js-dependent", "medium",
              "Heavy JavaScript dependency",
              f"{len(render_blocking)} render-blocking scripts. AI crawlers may not execute JS.",
              "Add async/defer to scripts. Ensure content is in initial HTML.",
              "AI crawlers may see empty page", 5, "technical")

    # Build crawler status map
    crawler_status = {}
    for crawler in AI_CRAWLERS:
        if _check_wildcard_block(robots_txt):
            crawler_status[crawler] = "blocked"
        elif _check_crawler_blocked(robots_txt, crawler):
            crawler_status[crawler] = "blocked"
        else:
            crawler_status[crawler] = "allowed"

    # llms.txt status
    if llms_txt and len(llms_txt.strip()) >= 50:
        llms_status = "present"
    elif llms_txt:
        llms_status = "thin"
    else:
        llms_status = "missing"

    return score, issues, sub_scores, citable_count, crawler_status, llms_status


async def analyze(
    parsed: dict,
    fetch_result: dict,
    competitor_parsed: dict | None = None,
    competitor_fetch: dict | None = None,
) -> dict:
    """Run GEO analysis, optionally with competitor comparison."""

    score, issues, sub_scores, citable_count, crawler_status, llms_status = _run_checks(parsed, fetch_result)

    # AI Query Simulation
    url = fetch_result.get("final_url", fetch_result.get("url", ""))
    title = parsed.get("title", "")
    body_text = parsed.get("body_text", "")
    ai_simulation = await _simulate_ai_queries(body_text, url, title)

    # Competitor comparison
    competitor_comparison = None
    if competitor_parsed and competitor_fetch:
        comp_score, comp_issues, comp_sub_scores, comp_citable, comp_crawler_status, comp_llms = _run_checks(
            competitor_parsed, competitor_fetch,
        )
        advantages = []
        gaps = []
        for key in sub_scores:
            diff = sub_scores[key] - comp_sub_scores[key]
            label = {"citability": "Citability", "structure": "Structure", "multiModal": "Multi-Modal",
                     "authority": "Authority", "technical": "Technical AI Access"}[key]
            if diff > 3:
                advantages.append(f"{label} (+{diff})")
            elif diff < -3:
                gaps.append(f"{label} ({diff})")

        competitor_comparison = {
            "competitorUrl": competitor_fetch.get("final_url", ""),
            "yourScore": max(0, score),
            "competitorScore": max(0, comp_score),
            "yourSubScores": sub_scores,
            "competitorSubScores": comp_sub_scores,
            "advantages": advantages,
            "gaps": gaps,
            "competitorIssueCount": len(comp_issues),
        }

    geo_details = {
        "subScores": sub_scores,
        "aiCrawlerStatus": crawler_status,
        "llmsTxtStatus": llms_status,
        "citablePassageCount": citable_count,
        "aiSimulation": ai_simulation,
    }

    return {
        "name": "geo",
        "label": "AI Search (GEO)",
        "score": max(0, score),
        "weight": 0.20,
        "issues": issues,
        "summary": f"AI Search (GEO) score: {max(0, score)}/100. {citable_count} citable passages. {sum(1 for v in crawler_status.values() if v == 'allowed')}/{len(crawler_status)} AI crawlers allowed.",
        "geoDetails": geo_details,
        "competitorComparison": competitor_comparison,
    }
