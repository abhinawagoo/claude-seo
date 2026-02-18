# Claude SEO — Project Context

## What This Is
A comprehensive SEO analysis toolkit with two parts:
1. **CLI Skills** — Claude Code skill package (`/seo audit`, `/seo page`, etc.) installed to `~/.claude/`
2. **FastAPI Backend** — Python API (`api/`) that wraps the analysis logic for the web frontend (engine-hoshloop)

## Owner
GitHub: [@abhinawagoo](https://github.com/abhinawagoo)

---

## Architecture

```
claude-seo/
├── seo/                    # Main skill entry point (SKILL.md)
│   └── references/         # Scoring criteria, thresholds, quality gates
├── skills/                 # 12 sub-skills (each has SKILL.md)
│   ├── seo-audit/          # Full site audit with parallel delegation
│   ├── seo-page/           # Single page deep analysis
│   ├── seo-technical/      # 8 technical categories
│   ├── seo-content/        # E-E-A-T + readability
│   ├── seo-schema/         # JSON-LD detection/validation/generation
│   ├── seo-sitemap/        # Sitemap analysis + generation
│   ├── seo-images/         # Image optimization
│   ├── seo-geo/            # AI Overviews / GEO
│   ├── seo-plan/           # Strategic planning (industry templates in assets/)
│   ├── seo-programmatic/   # Programmatic SEO at scale
│   ├── seo-competitor-pages/ # "X vs Y" comparison pages
│   └── seo-hreflang/       # Multi-language hreflang validation
├── agents/                 # 6 subagents (spawned in parallel during audits)
│   ├── seo-technical.md
│   ├── seo-content.md
│   ├── seo-schema.md
│   ├── seo-sitemap.md
│   ├── seo-performance.md
│   └── seo-visual.md
├── scripts/                # Python utilities
│   ├── fetch_page.py       # HTTP fetcher (requests)
│   ├── parse_html.py       # HTML parser (BeautifulSoup + lxml)
│   ├── capture_screenshot.py # Playwright browser automation
│   └── analyze_visual.py   # Visual analysis (Playwright)
├── api/                    # FastAPI backend (serves engine-hoshloop)
│   ├── main.py             # FastAPI app — POST /audit, GET /health
│   ├── engine.py           # Orchestrator (fetch → parse → 7 analyzers → score)
│   ├── fetcher.py          # Async page fetcher (httpx)
│   ├── parser.py           # HTML parser (BeautifulSoup)
│   ├── scorer.py           # Weighted scoring aggregator
│   ├── Dockerfile          # For Railway/Render deployment
│   ├── requirements.txt    # fastapi, uvicorn, anthropic, httpx, bs4, lxml
│   └── analyzers/
│       ├── technical.py    # 20% weight — title, meta, HTTPS, headers, robots, sitemap
│       ├── content.py      # 20% weight — word count, readability, Claude E-E-A-T
│       ├── onpage.py       # 15% weight — H1, headings, links, OG, URL structure
│       ├── geo.py          # 20% weight — AI search visibility, citability, crawlers
│       ├── schema_analyzer.py # 10% weight — JSON-LD validation, deprecated types
│       ├── performance.py  # 10% weight — scripts, CLS, image formats, CDN
│       └── images.py       # 5% weight — alt text, lazy loading, modern formats
├── schema/templates.json   # JSON-LD schema snippets
├── hooks/                  # Git pre-commit validation
├── docs/                   # ARCHITECTURE.md, COMMANDS.md, INSTALLATION.md, etc.
├── Procfile                # Railway deployment: uvicorn api.main:app
├── requirements.txt        # CLI skill Python deps (bs4, requests, playwright, Pillow)
├── install.sh / install.ps1 / uninstall.sh
└── engine-hoshloop/        # (gitignored — separate repo)
```

## SEO Audit Scoring

### Category Weights
| Category | Weight | Key Checks |
|----------|--------|------------|
| Technical SEO | 20% | Title, meta desc, canonical, HTTPS, security headers, robots.txt, sitemap |
| Content Quality | 20% | Word count, readability (Flesch), Claude AI E-E-A-T analysis |
| On-Page SEO | 15% | H1, heading hierarchy, internal links, OG tags, URL structure |
| AI Search (GEO) | 20% | Citability, structural readability, multi-modal, authority, AI crawlers |
| Schema | 10% | JSON-LD presence, deprecated types, required properties |
| Performance | 10% | Render-blocking scripts, image formats, CLS, CDN |
| Images | 5% | Alt text, dimensions, lazy loading, modern formats |

### E-E-A-T Weights (Content analyzer)
- Experience: 20%, Expertise: 25%, Authoritativeness: 25%, Trustworthiness: 30%

### Score Ranges
- 80-100: Excellent (green), 60-79: Good (blue), 40-59: Needs Work (yellow), 0-39: Poor (red)

### Severity Levels
- Critical → High → Medium → Low (top 10 issues returned as priority fixes)

## Key Thresholds
- Title: 30-60 chars
- Meta description: 120-160 chars
- Min word counts: Homepage 500, Blog 1500, Service 800, Product 400
- Location pages: WARNING at 30+, HARD STOP at 50+
- CWV targets: LCP ≤2.5s, INP ≤200ms, CLS ≤0.1

## API Backend

### Endpoints
- `POST /audit` — Accepts `{ url: "https://..." }`, returns full audit JSON
- `GET /health` — Returns `{ status: "ok" }`

### Auth
- `X-API-Key` header checked against `API_SECRET_KEY` env var

### Environment Variables
```
ANTHROPIC_API_KEY=sk-ant-xxx    # For Claude E-E-A-T analysis (uses claude-3-5-haiku-latest)
API_SECRET_KEY=xxx              # Shared secret with engine-hoshloop frontend
PORT=8000                       # Server port
```

### Deployment
- **Railway** (recommended) — auto-detects Procfile
- Or any platform supporting Python + Docker

### Running Locally
```bash
cd api
pip install -r requirements.txt
uvicorn api.main:app --reload --port 8000
```

## CLI Skills

### Installation
```bash
curl -fsSL https://raw.githubusercontent.com/abhinawagoo/claude-seo/main/install.sh | bash
```

### Key Commands
```
/seo audit <url>     — Full site audit (6 parallel subagents, 500 page crawl)
/seo page <url>      — Deep single-page analysis
/seo schema <url>    — Schema.org detection/validation/generation
/seo geo <url>       — AI Overviews / Generative Engine Optimization
/seo plan <type>     — Strategic planning (saas|local|ecommerce|publisher|agency)
```

## Python Dependencies
- CLI: beautifulsoup4, requests, lxml, playwright, Pillow, urllib3, validators
- API: fastapi, uvicorn, httpx, anthropic, beautifulsoup4, lxml, pydantic, python-dotenv

## Important Notes
- Skills are markdown-based prompts — Claude's reasoning does the analysis, Python handles I/O
- The API backend replicates the skill logic in pure Python for server-side execution
- AI model used: `claude-3-5-haiku-latest` (cost-optimized for batch E-E-A-T analysis)
- Schema types reference is kept up-to-date: HowTo deprecated (Sept 2023), FAQ restricted, SpecialAnnouncement deprecated (July 2025)
- E-E-A-T applies to ALL competitive queries since December 2025 update
