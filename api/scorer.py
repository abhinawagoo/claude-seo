"""
Score aggregator — builds final AuditResults from category results.

Weights:
  technical: 25%, content: 25%, onpage: 20%,
  schema: 10%, performance: 10%, images: 5%, ai-readiness: 5%
"""

from urllib.parse import urlparse


SEVERITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3}


def build_results(
    categories: list[dict],
    url: str,
    title: str | None,
    meta_description: str | None,
    duration_ms: int,
) -> dict:
    """Aggregate category results into final audit output."""

    # Overall score (weighted average)
    total_weight = sum(c["weight"] for c in categories)
    overall_score = round(
        sum(c["score"] * c["weight"] for c in categories) / total_weight
    ) if total_weight else 0

    # Top 10 priority fixes
    all_issues = []
    for cat in categories:
        all_issues.extend(cat.get("issues", []))

    all_issues.sort(key=lambda i: (
        SEVERITY_ORDER.get(i.get("severity", "low"), 3),
        -next(
            (c["weight"] for c in categories if c["name"] == i.get("category")),
            0,
        ),
    ))
    top_fixes = all_issues[:10]

    # Extract domain
    parsed = urlparse(url)
    domain = parsed.netloc.replace("www.", "")

    return {
        "overallScore": overall_score,
        "categories": categories,
        "topFixes": top_fixes,
        "url": url,
        "domain": domain,
        "fetchedAt": __import__("datetime").datetime.utcnow().isoformat() + "Z",
        "auditDuration": duration_ms,
        "pageTitle": title,
        "metaDescription": meta_description,
    }
