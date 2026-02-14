"""Content Quality analyzer with Claude AI E-E-A-T — 25% weight."""

import json
import re
import os

import anthropic


def _flesch_reading_ease(text: str) -> float:
    """Calculate Flesch Reading Ease score."""
    sentences = re.split(r"[.!?]+", text)
    sentences = [s.strip() for s in sentences if s.strip()]
    words = re.findall(r"\b\w+\b", text)
    if not sentences or not words:
        return 60.0

    syllable_count = 0
    for word in words:
        word = word.lower()
        count = 0
        vowels = "aeiouy"
        if word[0] in vowels:
            count += 1
        for i in range(1, len(word)):
            if word[i] in vowels and word[i - 1] not in vowels:
                count += 1
        if word.endswith("e"):
            count -= 1
        if count == 0:
            count = 1
        syllable_count += count

    avg_sentence_length = len(words) / len(sentences)
    avg_syllables_per_word = syllable_count / len(words)

    score = 206.835 - 1.015 * avg_sentence_length - 84.6 * avg_syllables_per_word
    return max(0, min(100, score))


async def _analyze_eeat_with_claude(body_text: str, url: str, title: str) -> dict | None:
    """Call Claude API for E-E-A-T analysis."""
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        return None

    # Truncate to 3000 words
    words = body_text.split()[:3000]
    truncated = " ".join(words)

    prompt = f"""Analyze this webpage content for E-E-A-T (Experience, Expertise, Authoritativeness, Trustworthiness) quality signals. Return ONLY valid JSON.

URL: {url}
Title: {title or "N/A"}
Content (truncated): {truncated}

Return this exact JSON structure:
{{
  "experience": {{ "score": 0-100, "signals": ["signal1", "signal2"] }},
  "expertise": {{ "score": 0-100, "signals": ["signal1", "signal2"] }},
  "authoritativeness": {{ "score": 0-100, "signals": ["signal1", "signal2"] }},
  "trustworthiness": {{ "score": 0-100, "signals": ["signal1", "signal2"] }},
  "overallScore": 0-100,
  "summary": "Brief E-E-A-T assessment",
  "aiContentRisk": "low|medium|high"
}}

Score each dimension 0-100. Identify specific signals.
Assess AI content risk based on generic phrasing, lack of specificity,
and absence of first-hand experience markers.

Weights: Experience 20%, Expertise 25%, Authoritativeness 25%, Trustworthiness 30%."""

    try:
        client = anthropic.AsyncAnthropic(api_key=api_key)
        response = await client.messages.create(
            model="claude-3-5-haiku-latest",
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}],
        )
        text = response.content[0].text.strip()
        # Extract JSON from response
        if "```" in text:
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
            text = text.strip()
        return json.loads(text)
    except Exception:
        return None


async def analyze(parsed: dict, fetch_result: dict) -> dict:
    score = 100
    issues = []
    url = fetch_result.get("final_url", fetch_result.get("url", ""))
    eeat_data = None

    def issue(id, sev, title, desc, rec, impact, pts):
        nonlocal score
        score = max(0, score - pts)
        issues.append({
            "id": id, "category": "content", "severity": sev,
            "title": title, "description": desc,
            "recommendation": rec, "impact": impact,
        })

    word_count = parsed.get("word_count", 0)

    # Word count
    if word_count < 200:
        issue("content-thin", "critical", "Thin content",
              f"Only {word_count} words. Google considers this thin content.",
              "Add substantial, valuable content (500+ words recommended).",
              "Major ranking penalty", 20)
    elif word_count < 500:
        issue("content-short", "high", "Short content",
              f"Page has {word_count} words (recommended: 500+).",
              "Expand content with valuable information.",
              "Reduced ranking potential", 12)

    # Readability
    body_text = parsed.get("body_text", "")
    if body_text:
        readability = _flesch_reading_ease(body_text)
        if readability < 30:
            issue("content-hard-read", "medium", "Very difficult to read",
                  f"Flesch score: {readability:.0f}/100. Content is hard to understand.",
                  "Simplify language. Target 60-70 for general audiences.",
                  "Poor user engagement", 8)
        elif readability < 50:
            issue("content-readability", "low", "Readability could improve",
                  f"Flesch score: {readability:.0f}/100.",
                  "Use shorter sentences and simpler words.",
                  "User engagement", 4)

    # H2 structure
    if not parsed.get("h2") and word_count > 300:
        issue("content-no-h2", "medium", "No H2 headings",
              "Long content without subheadings.",
              "Break content into sections with H2 headings.",
              "Poor readability and SEO structure", 6)

    # Date signals
    has_date = False
    for schema in parsed.get("schema", []):
        if isinstance(schema, dict):
            if schema.get("datePublished") or schema.get("dateModified"):
                has_date = True
                break
    if not has_date and word_count > 500:
        issue("content-no-date", "low", "No publication date signals",
              "No datePublished or dateModified found.",
              "Add date metadata via schema markup.",
              "Content freshness signals missing", 3)

    # Claude E-E-A-T analysis
    title = parsed.get("title", "")
    if body_text and len(body_text) > 100:
        eeat_data = await _analyze_eeat_with_claude(body_text, url, title)

    if eeat_data:
        eeat_score = eeat_data.get("overallScore", 50)
        if eeat_score < 40:
            issue("content-weak-eeat", "high", "Weak E-E-A-T signals",
                  f"E-E-A-T score: {eeat_score}/100. {eeat_data.get('summary', '')}",
                  "Add author credentials, first-hand experience, citations, and trust signals.",
                  "Major ranking factor since Dec 2025", 15)
        elif eeat_score < 60:
            issue("content-moderate-eeat", "medium", "Moderate E-E-A-T signals",
                  f"E-E-A-T score: {eeat_score}/100. {eeat_data.get('summary', '')}",
                  "Strengthen expertise signals: add author bio, credentials, case studies.",
                  "Competitive ranking disadvantage", 8)

        ai_risk = eeat_data.get("aiContentRisk", "low")
        if ai_risk == "high":
            issue("content-ai-risk-high", "high", "High AI-generated content risk",
                  "Content shows strong AI-generation patterns.",
                  "Add personal anecdotes, specific data, and first-hand experience.",
                  "Google's helpful content system penalizes generic AI content", 12)
        elif ai_risk == "medium":
            issue("content-ai-risk-medium", "medium", "Moderate AI content risk",
                  "Some AI-generation patterns detected.",
                  "Add more specificity and personal expertise signals.",
                  "Potential ranking impact", 6)

    return {
        "name": "content",
        "label": "Content Quality",
        "score": max(0, score),
        "weight": 0.25,
        "issues": issues,
        "summary": f"Content quality score: {max(0, score)}/100. Word count: {word_count}.",
        "eeat": eeat_data,
    }
