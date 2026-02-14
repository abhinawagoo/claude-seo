"""Image Optimization analyzer — 5% weight."""


def analyze(parsed: dict, fetch_result: dict) -> dict:
    score = 100
    issues = []
    images = parsed.get("images", [])

    def issue(id, sev, title, desc, rec, impact, pts):
        nonlocal score
        score = max(0, score - pts)
        issues.append({
            "id": id, "category": "images", "severity": sev,
            "title": title, "description": desc,
            "recommendation": rec, "impact": impact,
        })

    if not images:
        return {
            "name": "images", "label": "Image Optimization",
            "score": 100, "weight": 0.05,
            "issues": [],
            "summary": "No images found on page. Score: 100/100.",
        }

    # Alt text presence
    no_alt = [img for img in images if not img.get("alt")]
    if len(no_alt) > 3:
        issue("img-no-alt-many", "high", "Many images without alt text",
              f"{len(no_alt)}/{len(images)} images missing alt text.",
              "Add descriptive alt text to all non-decorative images.",
              "Accessibility + image search ranking", min(20, len(no_alt) * 4))
    elif no_alt:
        issue("img-no-alt-some", "medium", "Some images without alt text",
              f"{len(no_alt)} images missing alt text.",
              "Add alt text describing each image.",
              "Accessibility issue", min(12, len(no_alt) * 4))

    # Alt text quality
    for img in images:
        alt = img.get("alt") or ""
        if alt and len(alt) < 10:
            issue("img-short-alt", "low", "Very short alt text",
                  f"Alt text '{alt}' is too brief.",
                  "Use 10-125 character descriptive alt text.",
                  "Weak image SEO signal", 5)
            break

    # Image formats
    old_format_count = 0
    for img in images:
        src = (img.get("src") or "").lower()
        ext = src.rsplit(".", 1)[-1] if "." in src else ""
        if ext in ("jpg", "jpeg", "png", "gif", "bmp"):
            old_format_count += 1
    if images and (old_format_count / len(images)) > 0.5:
        issue("img-old-formats", "medium", "Legacy image formats",
              f"{old_format_count}/{len(images)} images use JPEG/PNG.",
              "Convert to WebP or AVIF for better compression.",
              "Slower page load", min(10, round(old_format_count / len(images) * 10)))

    # Dimensions
    no_dims = [
        img for img in images
        if not img.get("width") or not img.get("height")
    ]
    if len(no_dims) > 5:
        issue("img-no-dims-many", "high", "Images without dimensions",
              f"{len(no_dims)} images missing width/height.",
              "Add width and height attributes.",
              "Causes Cumulative Layout Shift", min(15, len(no_dims) * 2))
    elif no_dims:
        issue("img-no-dims-some", "medium", "Some images lack dimensions",
              f"{len(no_dims)} images without dimensions.",
              "Add width/height to prevent layout shifts.",
              "Contributes to CLS", min(6, len(no_dims) * 2))

    # Lazy loading
    non_lazy = [
        img for img in images[1:]  # skip first/hero image
        if img.get("loading") != "lazy"
    ]
    if len(non_lazy) > 3:
        issue("img-no-lazy", "medium", "Images not lazy loaded",
              f"{len(non_lazy)} below-fold images without loading='lazy'.",
              "Add loading='lazy' to images below the fold.",
              "Wasted bandwidth on initial load", min(10, round(len(non_lazy) / 2)))

    # Hero/LCP image
    if images:
        first = images[0]
        if first.get("fetchpriority") != "high" and not first.get("loading") == "lazy":
            issue("img-hero-no-priority", "low", "Hero image not prioritized",
                  "First image doesn't have fetchpriority='high'.",
                  "Add fetchpriority='high' to the hero/LCP image.",
                  "Slower LCP", 3)
        if first.get("loading") == "lazy":
            issue("img-hero-lazy", "high", "Hero image is lazy loaded",
                  "The first image has loading='lazy' which delays LCP.",
                  "Remove loading='lazy' from the hero image.",
                  "Directly harms Largest Contentful Paint", 10)

    return {
        "name": "images", "label": "Image Optimization",
        "score": max(0, score), "weight": 0.05,
        "issues": issues,
        "summary": f"Image score: {max(0, score)}/100. {len(images)} images analyzed.",
    }
