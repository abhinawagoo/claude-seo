"""Performance analyzer — 10% weight."""


def analyze(parsed: dict, fetch_result: dict) -> dict:
    score = 100
    issues = []

    def issue(id, sev, title, desc, rec, impact, pts):
        nonlocal score
        score = max(0, score - pts)
        issues.append({
            "id": id, "category": "performance", "severity": sev,
            "title": title, "description": desc,
            "recommendation": rec, "impact": impact,
        })

    scripts = parsed.get("scripts", [])
    stylesheets = parsed.get("stylesheets", [])
    images = parsed.get("images", [])
    links = parsed.get("links", {})
    headings_count = sum(
        len(parsed.get(f"h{i}", [])) for i in range(1, 7)
    )

    # Render-blocking scripts
    blocking = [s for s in scripts if not s.get("async") and not s.get("defer")]
    if len(blocking) > 3:
        issue("perf-blocking-scripts", "high", "Many render-blocking scripts",
              f"{len(blocking)} scripts without async/defer.",
              "Add async or defer to non-critical scripts.",
              "Delays Largest Contentful Paint", min(15, len(blocking) * 3))
    elif blocking:
        issue("perf-some-blocking", "medium", "Render-blocking scripts found",
              f"{len(blocking)} scripts block rendering.",
              "Add async or defer attributes.",
              "Slows initial page load", min(9, len(blocking) * 3))

    # Stylesheets
    if len(stylesheets) > 5:
        issue("perf-many-css", "medium", "Many external stylesheets",
              f"{len(stylesheets)} external CSS files.",
              "Combine stylesheets or use critical CSS inlining.",
              "Increases render-blocking time", 5)

    # DOM size estimate
    dom_estimate = (
        len(images) + len(links.get("internal", []))
        + len(links.get("external", [])) + headings_count + len(scripts)
    )
    if dom_estimate > 800:
        issue("perf-large-dom", "medium", "Large DOM size detected",
              f"Estimated {dom_estimate}+ elements. Large DOMs slow INP.",
              "Simplify page structure. Target under 800 key elements.",
              "Poor Interaction to Next Paint (INP)", 8)

    # Image formats
    if images:
        modern_formats = {"webp", "avif", "svg"}
        old_format_count = 0
        for img in images:
            src = (img.get("src") or "").lower()
            ext = src.rsplit(".", 1)[-1] if "." in src else ""
            if ext in ("jpg", "jpeg", "png", "gif", "bmp"):
                old_format_count += 1
        pct = (old_format_count / len(images)) * 100 if images else 0
        if pct > 50:
            issue("perf-old-image-formats", "medium", "Legacy image formats",
                  f"{old_format_count}/{len(images)} images use JPEG/PNG.",
                  "Convert to WebP or AVIF for 30-50% smaller files.",
                  "Slower page load", 8)

    # Font loading
    for sheet in stylesheets:
        sheet_lower = sheet.lower()
        if any(kw in sheet_lower for kw in ("fonts.googleapis", "typekit", "use.fontawesome")):
            issue("perf-web-fonts", "low", "External web fonts detected",
                  "Web fonts add latency.",
                  "Use font-display: swap and preload critical fonts.",
                  "Flash of invisible text", 2)
            break

    # Image dimensions (CLS)
    no_dimensions = [
        img for img in images
        if not img.get("width") or not img.get("height")
    ]
    if len(no_dimensions) > 5:
        issue("perf-no-img-dimensions", "high", "Images without dimensions",
              f"{len(no_dimensions)} images missing width/height.",
              "Add width and height attributes to all images.",
              "#1 cause of CLS (Cumulative Layout Shift)", min(12, len(no_dimensions) * 2))
    elif no_dimensions:
        issue("perf-some-no-dimensions", "medium", "Some images lack dimensions",
              f"{len(no_dimensions)} images without width/height.",
              "Add explicit dimensions to prevent layout shifts.",
              "Contributes to CLS", min(6, len(no_dimensions) * 2))

    # CDN detection
    headers = fetch_result.get("headers", {})
    headers_lower = {k.lower(): v for k, v in headers.items()}
    cdn_headers = ["cf-ray", "x-cache", "x-cdn", "x-served-by", "x-amz-cf-id"]
    has_cdn = any(h in headers_lower for h in cdn_headers)
    if not has_cdn:
        issue("perf-no-cdn", "low", "No CDN detected",
              "No CDN headers found.",
              "Use a CDN (Cloudflare, CloudFront, Fastly) for faster delivery.",
              "Slower load times for distant users", 3)

    return {
        "name": "performance",
        "label": "Performance",
        "score": max(0, score),
        "weight": 0.10,
        "issues": issues,
        "summary": f"Performance score: {max(0, score)}/100.",
    }
