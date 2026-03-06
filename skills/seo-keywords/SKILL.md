# SEO Keywords — Strike Zone Analysis

Find keywords where you're ranking positions 5–20. These are one good article or page update away from page 1.

## Usage

```
/seo keywords <domain>
/seo keywords <domain> --days 60
/seo keywords <domain> --min 8 --max 15
```

## What This Does

1. **Pulls real Google Search Console data** — actual positions, clicks, impressions
2. **Filters to the strike zone** — positions 5–20 with meaningful search volume
3. **Classifies by opportunity type**:
   - 🎯 Quick wins — positions 8–15, high impressions (update existing page)
   - 📉 Content gaps — high impressions, near-zero clicks (fix title/meta)
   - 🔻 Declining — dropped positions in last 28 days (refresh content urgently)
   - 📈 Climbing — improving positions (amplify with links)
4. **Groups by page** — shows which pages have the most strike zone keywords (highest ROI to update)
5. **Saves position snapshot to DB** — builds trend history over time

## Prerequisites

The domain must have GSC connected. Connect via:
```
GET /gsc/connect?domain=yourdomain.com
```

## Output Format

```
STRIKE ZONE ANALYSIS — yourdomain.com
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

📊 SUMMARY (last 90 days)
  Strike zone keywords:  47
  Quick wins available:  12
  Content gaps:           8
  Declining keywords:     5
  Total impression opp:  84,200/mo

🎯 QUICK WINS (positions 8–15, high volume)
  ┌─────────────────────────────────────────────────────┐
  │ Keyword                    Pos   Impr   CTR   Page  │
  │ "saas seo strategy"        9.2   2,400  1.2%  /blog │
  │ "ai seo tools"            11.4   1,800  0.8%  /     │
  │ "seo audit tool free"     13.1   1,200  0.5%  /audit│
  └─────────────────────────────────────────────────────┘

📉 CONTENT GAPS (ranking but not getting clicks)
  "seo checklist 2024"  pos 14 — 900 impressions, 0.3% CTR
  → Rewrite meta title to be more compelling

📈 CLIMBING (improving this month)
  "technical seo audit"  12 → 8  (+4 positions)

🔻 DECLINING (needs attention)
  "seo report tool"  7 → 14  (-7 positions, refresh content)

📄 PAGES WITH MOST OPPORTUNITIES
  /blog/seo-guide  →  8 strike zone keywords (update this page first)

🎯 TOP 3 ACTIONS
  1. [CRITICAL] Update /blog/seo-guide — 8 keywords near page 1
  2. [HIGH] Fix meta title on /audit — 900 impressions, 0.3% CTR
  3. [HIGH] Refresh "seo report tool" page — dropped 7 positions
```

## How to Use the Results

### Quick wins (positions 8–15)
These pages already rank. Small improvements push them to page 1:
- Add a FAQ section targeting the keyword as a question
- Improve the H1 and first paragraph to match search intent exactly
- Add 2–3 internal links from high-authority pages
- Build 1–2 external backlinks to the page

### Content gaps (high impressions, low CTR)
You rank but people don't click. Fix:
- Rewrite meta title to include the keyword + a hook ("Free", "2024", "Step-by-step")
- Improve meta description to 155 chars with a clear value proposition
- Add structured data (FAQ, HowTo) for rich snippets

### Declining keywords
Google is testing others ahead of you. Refresh the page:
- Update publish date + add new section with recent data
- Add author bio and credentials (E-E-A-T)
- Check if a competitor recently published something better

## Run This Weekly

Position tracking compounds over time. Run weekly to catch drops early and double down on climbers.

```
/seo monitor setup <domain>   — automates weekly runs
```
