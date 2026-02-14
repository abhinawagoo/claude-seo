"""
Parse HTML and extract SEO-relevant elements.
Wraps scripts/parse_html.py logic.
"""

import json
import re
from typing import Optional
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup


def parse_html(html: str, base_url: Optional[str] = None) -> dict:
    """Parse HTML and extract all SEO-relevant data."""
    soup = BeautifulSoup(html, "lxml")

    result = {
        "title": None,
        "meta_description": None,
        "meta_robots": None,
        "canonical": None,
        "viewport": None,
        "charset": None,
        "language": None,
        "h1": [],
        "h2": [],
        "h3": [],
        "h4": [],
        "h5": [],
        "h6": [],
        "images": [],
        "links": {"internal": [], "external": []},
        "scripts": [],
        "stylesheets": [],
        "schema": [],
        "open_graph": {},
        "twitter_card": {},
        "word_count": 0,
        "body_text": "",
        "hreflang": [],
    }

    # Language
    html_tag = soup.find("html")
    if html_tag:
        result["language"] = html_tag.get("lang")

    # Title
    title_tag = soup.find("title")
    if title_tag:
        result["title"] = title_tag.get_text(strip=True)

    # Meta tags
    for meta in soup.find_all("meta"):
        name = meta.get("name", "").lower()
        prop = meta.get("property", "").lower()
        content = meta.get("content", "")
        charset = meta.get("charset")

        if charset:
            result["charset"] = charset
        if name == "description":
            result["meta_description"] = content
        elif name == "robots":
            result["meta_robots"] = content
        elif name == "viewport":
            result["viewport"] = content

        # Open Graph
        if prop.startswith("og:"):
            result["open_graph"][prop] = content
        # Twitter Card
        if name.startswith("twitter:"):
            result["twitter_card"][name] = content

    # Canonical
    canonical = soup.find("link", rel="canonical")
    if canonical:
        result["canonical"] = canonical.get("href")

    # Hreflang
    for link in soup.find_all("link", rel="alternate"):
        hreflang = link.get("hreflang")
        if hreflang:
            result["hreflang"].append({"lang": hreflang, "href": link.get("href")})

    # Headings
    for level in range(1, 7):
        tag = f"h{level}"
        for heading in soup.find_all(tag):
            text = heading.get_text(strip=True)
            if text:
                result[tag].append(text)

    # Images
    for img in soup.find_all("img"):
        src = img.get("src", "")
        if base_url and src:
            src = urljoin(base_url, src)
        result["images"].append({
            "src": src,
            "alt": img.get("alt"),
            "width": img.get("width"),
            "height": img.get("height"),
            "loading": img.get("loading"),
            "fetchpriority": img.get("fetchpriority"),
            "decoding": img.get("decoding"),
        })

    # Links
    if base_url:
        base_domain = urlparse(base_url).netloc
        for a in soup.find_all("a", href=True):
            href = a.get("href", "")
            if not href or href.startswith("#") or href.startswith("javascript:"):
                continue
            full_url = urljoin(base_url, href)
            parsed = urlparse(full_url)
            link_data = {
                "href": full_url,
                "text": a.get_text(strip=True)[:100],
                "rel": a.get("rel", []),
                "nofollow": "nofollow" in a.get("rel", []),
            }
            if parsed.netloc == base_domain:
                result["links"]["internal"].append(link_data)
            else:
                result["links"]["external"].append(link_data)

    # Scripts
    for script in soup.find_all("script"):
        if script.get("type") == "application/ld+json":
            continue
        src = script.get("src")
        if src:
            result["scripts"].append({
                "src": urljoin(base_url, src) if base_url else src,
                "async": script.has_attr("async"),
                "defer": script.has_attr("defer"),
                "type": script.get("type"),
            })

    # Stylesheets
    for link in soup.find_all("link", rel="stylesheet"):
        href = link.get("href")
        if href:
            result["stylesheets"].append(
                urljoin(base_url, href) if base_url else href
            )

    # Schema (JSON-LD)
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            result["schema"].append(json.loads(script.string))
        except (json.JSONDecodeError, TypeError):
            pass

    # Body text + word count
    text_soup = BeautifulSoup(html, "lxml")
    for el in text_soup(["script", "style", "nav", "footer", "header", "noscript"]):
        el.decompose()
    body_text = text_soup.get_text(separator=" ", strip=True)
    result["body_text"] = body_text[:15000]
    result["word_count"] = len(re.findall(r"\b\w+\b", body_text))

    return result
