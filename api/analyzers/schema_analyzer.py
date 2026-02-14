"""Schema & Structured Data analyzer — 10% weight."""

DEPRECATED_TYPES = {
    "HowTo": "September 2023",
    "SpecialAnnouncement": "July 2025",
    "CourseInfo": "June 2025",
    "EstimatedSalary": "June 2025",
    "LearningVideo": "June 2025",
    "ClaimReview": "June 2025",
    "VehicleListing": "June 2025",
    "Dataset": "Late 2025",
}

RESTRICTED_TYPES = {
    "FAQPage": "Government and healthcare authority sites only (Aug 2023)",
}

REQUIRED_PROPS = {
    "Organization": ["name", "url"],
    "LocalBusiness": ["name", "address"],
    "Product": ["name"],
    "Article": ["headline", "author", "datePublished"],
    "BlogPosting": ["headline", "author", "datePublished"],
    "NewsArticle": ["headline", "author", "datePublished"],
    "WebSite": ["name", "url"],
    "BreadcrumbList": ["itemListElement"],
    "VideoObject": ["name", "uploadDate"],
    "Event": ["name", "startDate"],
}


def _get_type(schema: dict) -> str | None:
    t = schema.get("@type")
    if isinstance(t, list):
        return t[0] if t else None
    return t


def analyze(parsed: dict, fetch_result: dict) -> dict:
    score = 100
    issues = []
    schemas = parsed.get("schema", [])

    def issue(id, sev, title, desc, rec, impact, pts):
        nonlocal score
        score = max(0, score - pts)
        issues.append({
            "id": id, "category": "schema", "severity": sev,
            "title": title, "description": desc,
            "recommendation": rec, "impact": impact,
        })

    if not schemas:
        issue("schema-none", "high", "No structured data found",
              "No JSON-LD schema markup detected.",
              "Add JSON-LD schema (Organization, WebSite, BreadcrumbList at minimum). Pages with schema have ~2.5x higher chance in AI answers.",
              "Missing rich results + AI visibility", 25)
        return {
            "name": "schema", "label": "Schema & Structured Data",
            "score": max(0, score), "weight": 0.10,
            "issues": issues,
            "summary": f"Schema score: {max(0, score)}/100. No structured data found.",
        }

    found_types = set()

    for schema in schemas:
        if not isinstance(schema, dict):
            continue

        # @context check
        ctx = schema.get("@context", "")
        if not ctx:
            issue("schema-no-context", "high", "Schema missing @context",
                  "JSON-LD block has no @context property.",
                  "Add '@context': 'https://schema.org'.", "Invalid schema", 8)
        elif "http://schema.org" in ctx and "https" not in ctx:
            issue("schema-http-context", "medium", "Schema uses http:// context",
                  "Use https://schema.org instead of http://.",
                  "Change @context to 'https://schema.org'.",
                  "May cause validation warnings", 3)

        schema_type = _get_type(schema)
        if schema_type:
            found_types.add(schema_type)

            # Deprecated check
            if schema_type in DEPRECATED_TYPES:
                issue(f"schema-deprecated-{schema_type.lower()}", "high",
                      f"Deprecated schema type: {schema_type}",
                      f"{schema_type} was deprecated in {DEPRECATED_TYPES[schema_type]}.",
                      f"Remove {schema_type} schema — Google no longer supports it.",
                      "No rich results, wasted markup", 10)

            # Restricted check
            if schema_type in RESTRICTED_TYPES:
                issue(f"schema-restricted-{schema_type.lower()}", "medium",
                      f"Restricted schema type: {schema_type}",
                      f"{RESTRICTED_TYPES[schema_type]}.",
                      f"Only use {schema_type} if your site qualifies.",
                      "May not generate rich results", 5)

            # Required properties
            if schema_type in REQUIRED_PROPS:
                missing = [
                    p for p in REQUIRED_PROPS[schema_type]
                    if p not in schema
                ]
                if missing:
                    issue(f"schema-missing-props-{schema_type.lower()}", "medium",
                          f"{schema_type} missing required properties",
                          f"Missing: {', '.join(missing)}.",
                          f"Add {', '.join(missing)} to your {schema_type} schema.",
                          "Incomplete rich results", 5)

    # Missing common schemas
    if schemas and not found_types & {"Organization", "LocalBusiness"}:
        issue("schema-no-org", "medium", "No Organization/LocalBusiness schema",
              "Missing organizational identity schema.",
              "Add Organization or LocalBusiness schema.",
              "Missing brand knowledge panel", 5)

    if schemas and "BreadcrumbList" not in found_types:
        issue("schema-no-breadcrumb", "low", "No BreadcrumbList schema",
              "Breadcrumb navigation not marked up.",
              "Add BreadcrumbList schema for better SERP display.",
              "Missing breadcrumb rich results", 3)

    if schemas and "WebSite" not in found_types:
        issue("schema-no-website", "low", "No WebSite schema",
              "Missing WebSite schema with search action.",
              "Add WebSite schema for sitelinks searchbox.",
              "Missing sitelinks searchbox", 3)

    # OG check
    if not parsed.get("open_graph"):
        score = max(0, score - 5)

    return {
        "name": "schema", "label": "Schema & Structured Data",
        "score": max(0, score), "weight": 0.10,
        "issues": issues,
        "summary": f"Schema score: {max(0, score)}/100. Found {len(schemas)} schema blocks ({', '.join(found_types) or 'none'}).",
    }
