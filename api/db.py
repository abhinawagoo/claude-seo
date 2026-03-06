"""
Database layer — Hoshloop SEO Growth Platform

Postgres + pgvector via asyncpg.
Covers both pillars:
  - Pillar 1: SEO Automation (keywords, brand profiles, backlinks, audit history, monitor jobs)
  - Pillar 2: Social Intelligence (companies, memory embeddings, Slack, content suggestions)

Usage:
    from api.db import get_pool, init_schema
    await init_schema()          # call once at startup
    pool = await get_pool()      # use anywhere
"""

import json
import os
from typing import Optional

import asyncpg

_pool: Optional[asyncpg.Pool] = None


# ---------------------------------------------------------------------------
# Connection pool
# ---------------------------------------------------------------------------

async def get_pool() -> asyncpg.Pool:
    global _pool
    if _pool is None:
        dsn = os.environ.get("DATABASE_URL")
        if not dsn:
            raise RuntimeError("DATABASE_URL environment variable not set")
        _pool = await asyncpg.create_pool(dsn, min_size=2, max_size=10)
    return _pool


async def close_pool():
    global _pool
    if _pool:
        await _pool.close()
        _pool = None


# ---------------------------------------------------------------------------
# Schema initialisation
# ---------------------------------------------------------------------------

async def init_schema():
    """
    Create all tables and indexes.
    Safe to call on every startup (CREATE TABLE IF NOT EXISTS).
    Requires the pgvector extension to be available on the Postgres server.
    """
    pool = await get_pool()
    async with pool.acquire() as conn:

        # pgvector extension
        await conn.execute("CREATE EXTENSION IF NOT EXISTS vector")

        # ----------------------------------------------------------------
        # Pillar 1: SEO Automation
        # ----------------------------------------------------------------

        await conn.execute("""
            CREATE TABLE IF NOT EXISTS keyword_positions (
                id          BIGSERIAL PRIMARY KEY,
                domain      TEXT      NOT NULL,
                keyword     TEXT      NOT NULL,
                position    REAL,
                volume      INTEGER   DEFAULT 0,
                url         TEXT,
                source      TEXT      DEFAULT 'dataforseo',  -- 'gsc' | 'dataforseo'
                recorded_at TIMESTAMPTZ DEFAULT now()
            );
            CREATE INDEX IF NOT EXISTS idx_kp_domain_date
                ON keyword_positions (domain, recorded_at DESC);
            CREATE INDEX IF NOT EXISTS idx_kp_domain_keyword
                ON keyword_positions (domain, keyword);
        """)

        await conn.execute("""
            CREATE TABLE IF NOT EXISTS brand_profiles (
                id                 BIGSERIAL PRIMARY KEY,
                domain             TEXT UNIQUE NOT NULL,
                voice              JSONB DEFAULT '{}',
                audience           JSONB DEFAULT '{}',
                key_topics         TEXT[]    DEFAULT '{}',
                interview_answers  JSONB DEFAULT '{}',
                created_at         TIMESTAMPTZ DEFAULT now(),
                updated_at         TIMESTAMPTZ DEFAULT now()
            );
        """)

        await conn.execute("""
            CREATE TABLE IF NOT EXISTS backlink_opportunities (
                id                BIGSERIAL PRIMARY KEY,
                domain            TEXT NOT NULL,
                type              TEXT NOT NULL,
                source_url        TEXT,
                target_url        TEXT,
                anchor_text       TEXT,
                domain_authority  INTEGER DEFAULT 0,
                status            TEXT DEFAULT 'new',
                found_at          TIMESTAMPTZ DEFAULT now(),
                UNIQUE (domain, type, source_url)
            );
            CREATE INDEX IF NOT EXISTS idx_bo_domain_status
                ON backlink_opportunities (domain, status);
        """)

        await conn.execute("""
            CREATE TABLE IF NOT EXISTS monitor_jobs (
                id           BIGSERIAL PRIMARY KEY,
                domain       TEXT UNIQUE NOT NULL,
                schedule     TEXT DEFAULT 'weekly',
                last_run     TIMESTAMPTZ,
                next_run     TIMESTAMPTZ,
                alert_email  TEXT,
                active       BOOLEAN DEFAULT true,
                created_at   TIMESTAMPTZ DEFAULT now()
            );
        """)

        await conn.execute("""
            CREATE TABLE IF NOT EXISTS audit_history (
                id            BIGSERIAL PRIMARY KEY,
                domain        TEXT NOT NULL,
                overall_score INTEGER,
                categories    JSONB DEFAULT '[]',
                recorded_at   TIMESTAMPTZ DEFAULT now()
            );
            CREATE INDEX IF NOT EXISTS idx_ah_domain_date
                ON audit_history (domain, recorded_at DESC);
        """)

        # ----------------------------------------------------------------
        # Pillar 2: Social Intelligence
        # ----------------------------------------------------------------

        await conn.execute("""
            CREATE TABLE IF NOT EXISTS companies (
                id            BIGSERIAL PRIMARY KEY,
                domain        TEXT UNIQUE NOT NULL,
                name          TEXT,
                icp           JSONB DEFAULT '{}',
                slack_token   TEXT,
                slack_team_id TEXT,
                created_at    TIMESTAMPTZ DEFAULT now()
            );
        """)

        # 1536-dim matches OpenAI text-embedding-3-small and Voyage AI.
        # Swap dimension here if using a different embedding model.
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS company_memory (
                id          BIGSERIAL PRIMARY KEY,
                company_id  BIGINT REFERENCES companies(id) ON DELETE CASCADE,
                content     TEXT NOT NULL,
                embedding   vector(1536),
                source      TEXT,   -- 'slack' | 'interview' | 'website' | 'manual'
                metadata    JSONB DEFAULT '{}',
                created_at  TIMESTAMPTZ DEFAULT now()
            );
            CREATE INDEX IF NOT EXISTS idx_cm_company
                ON company_memory (company_id);
            CREATE INDEX IF NOT EXISTS idx_cm_embedding
                ON company_memory USING ivfflat (embedding vector_cosine_ops)
                WITH (lists = 100);
        """)

        await conn.execute("""
            CREATE TABLE IF NOT EXISTS slack_messages (
                id          BIGSERIAL PRIMARY KEY,
                company_id  BIGINT REFERENCES companies(id) ON DELETE CASCADE,
                channel     TEXT,
                text        TEXT,
                user_id     TEXT,
                ts          TEXT UNIQUE,
                processed   BOOLEAN DEFAULT false,
                created_at  TIMESTAMPTZ DEFAULT now()
            );
            CREATE INDEX IF NOT EXISTS idx_sm_company_processed
                ON slack_messages (company_id, processed);
        """)

        await conn.execute("""
            CREATE TABLE IF NOT EXISTS content_suggestions (
                id          BIGSERIAL PRIMARY KEY,
                company_id  BIGINT REFERENCES companies(id) ON DELETE CASCADE,
                platform    TEXT NOT NULL,   -- 'linkedin' | 'x' | 'reddit' | 'blog'
                content     TEXT NOT NULL,
                type        TEXT,            -- 'post' | 'reply' | 'thread' | 'article'
                status      TEXT DEFAULT 'pending',
                week_of     DATE,
                created_at  TIMESTAMPTZ DEFAULT now()
            );
            CREATE INDEX IF NOT EXISTS idx_cs_company_platform
                ON content_suggestions (company_id, platform, status);
        """)

        await conn.execute("""
            CREATE TABLE IF NOT EXISTS post_performance (
                id               BIGSERIAL PRIMARY KEY,
                suggestion_id    BIGINT REFERENCES content_suggestions(id),
                posted_url       TEXT,
                engagement_score INTEGER DEFAULT 0,
                tracked_at       TIMESTAMPTZ DEFAULT now()
            );
        """)

        await conn.execute("""
            CREATE TABLE IF NOT EXISTS topic_clusters (
                id              BIGSERIAL PRIMARY KEY,
                company_id      BIGINT REFERENCES companies(id) ON DELETE CASCADE,
                topic           TEXT NOT NULL,
                authority_score INTEGER DEFAULT 0,
                keywords        JSONB DEFAULT '[]',
                updated_at      TIMESTAMPTZ DEFAULT now(),
                UNIQUE (company_id, topic)
            );
        """)

        await conn.execute("""
            CREATE TABLE IF NOT EXISTS reddit_opportunities (
                id           BIGSERIAL PRIMARY KEY,
                company_id   BIGINT REFERENCES companies(id) ON DELETE CASCADE,
                subreddit    TEXT,
                thread_url   TEXT,
                thread_title TEXT,
                type         TEXT,       -- 'post' | 'comment_reply' | 'question_answer'
                suggestion   TEXT,
                status       TEXT DEFAULT 'new',
                found_at     TIMESTAMPTZ DEFAULT now(),
                UNIQUE (company_id, thread_url)
            );
            CREATE INDEX IF NOT EXISTS idx_ro_company_status
                ON reddit_opportunities (company_id, status);
        """)

        await conn.execute("""
            CREATE TABLE IF NOT EXISTS gsc_tokens (
                id            BIGSERIAL PRIMARY KEY,
                company_id    BIGINT UNIQUE REFERENCES companies(id) ON DELETE CASCADE,
                access_token  TEXT,
                refresh_token TEXT NOT NULL,
                token_expiry  TIMESTAMPTZ,
                site_url      TEXT,
                created_at    TIMESTAMPTZ DEFAULT now(),
                updated_at    TIMESTAMPTZ DEFAULT now()
            );
        """)


# ---------------------------------------------------------------------------
# CRUD helpers — Pillar 1: SEO Automation
# ---------------------------------------------------------------------------

async def save_keyword_positions(domain: str, positions: list[dict]):
    """
    Bulk-insert keyword positions.
    Each dict: {keyword, position, volume?, url?, source?}
    """
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.executemany(
            """INSERT INTO keyword_positions (domain, keyword, position, volume, url, source)
               VALUES ($1, $2, $3, $4, $5, $6)""",
            [
                (
                    domain,
                    row["keyword"],
                    row.get("position"),
                    row.get("volume", 0),
                    row.get("url"),
                    row.get("source", "dataforseo"),
                )
                for row in positions
            ],
        )


async def get_strike_zone_keywords(
    domain: str, min_pos: float = 5.0, max_pos: float = 20.0
) -> list[dict]:
    """Return the most-recent position snapshot per keyword in the strike zone."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """SELECT DISTINCT ON (keyword)
                      keyword, position, volume, url, source, recorded_at
               FROM keyword_positions
               WHERE domain = $1
                 AND position BETWEEN $2 AND $3
               ORDER BY keyword, recorded_at DESC
               LIMIT 500""",
            domain,
            min_pos,
            max_pos,
        )
        return [dict(r) for r in rows]


async def get_keyword_trend(domain: str, keyword: str, days: int = 90) -> list[dict]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """SELECT position, recorded_at
               FROM keyword_positions
               WHERE domain = $1
                 AND keyword = $2
                 AND recorded_at > now() - ($3 || ' days')::interval
               ORDER BY recorded_at ASC""",
            domain,
            keyword,
            str(days),
        )
        return [dict(r) for r in rows]


async def get_climbing_keywords(domain: str, days: int = 30) -> list[dict]:
    """
    Keywords that have improved position (lower number = better) over N days.
    Returns list with first_position, latest_position, delta.
    """
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """WITH ranked AS (
                   SELECT keyword,
                          first_value(position) OVER w AS first_pos,
                          last_value(position)  OVER w AS last_pos
                   FROM keyword_positions
                   WHERE domain = $1
                     AND recorded_at > now() - ($2 || ' days')::interval
                   WINDOW w AS (PARTITION BY keyword ORDER BY recorded_at
                                ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING)
               )
               SELECT DISTINCT keyword,
                      first_pos,
                      last_pos,
                      (first_pos - last_pos) AS delta
               FROM ranked
               WHERE last_pos < first_pos
               ORDER BY delta DESC
               LIMIT 50""",
            domain,
            str(days),
        )
        return [dict(r) for r in rows]


async def upsert_brand_profile(domain: str, **fields) -> dict:
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """INSERT INTO brand_profiles (domain, voice, audience, key_topics, interview_answers)
               VALUES ($1, $2::jsonb, $3::jsonb, $4, $5::jsonb)
               ON CONFLICT (domain) DO UPDATE
               SET voice             = EXCLUDED.voice,
                   audience          = EXCLUDED.audience,
                   key_topics        = EXCLUDED.key_topics,
                   interview_answers = EXCLUDED.interview_answers,
                   updated_at        = now()
               RETURNING *""",
            domain,
            json.dumps(fields.get("voice", {})),
            json.dumps(fields.get("audience", {})),
            fields.get("key_topics", []),
            json.dumps(fields.get("interview_answers", {})),
        )
        return dict(row)


async def get_brand_profile(domain: str) -> dict | None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT * FROM brand_profiles WHERE domain = $1", domain
        )
        return dict(row) if row else None


async def save_backlink_opportunity(
    domain: str,
    type: str,
    source_url: str,
    target_url: str = None,
    anchor_text: str = None,
    domain_authority: int = 0,
):
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """INSERT INTO backlink_opportunities
                   (domain, type, source_url, target_url, anchor_text, domain_authority)
               VALUES ($1, $2, $3, $4, $5, $6)
               ON CONFLICT (domain, type, source_url) DO NOTHING""",
            domain,
            type,
            source_url,
            target_url,
            anchor_text,
            domain_authority,
        )


async def get_backlink_opportunities(
    domain: str, status: str = "new", limit: int = 100
) -> list[dict]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """SELECT * FROM backlink_opportunities
               WHERE domain = $1 AND status = $2
               ORDER BY domain_authority DESC
               LIMIT $3""",
            domain,
            status,
            limit,
        )
        return [dict(r) for r in rows]


async def save_audit_snapshot(domain: str, overall_score: int, categories: list):
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """INSERT INTO audit_history (domain, overall_score, categories)
               VALUES ($1, $2, $3::jsonb)""",
            domain,
            overall_score,
            json.dumps(categories),
        )


async def get_audit_history(domain: str, limit: int = 12) -> list[dict]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """SELECT overall_score, categories, recorded_at
               FROM audit_history
               WHERE domain = $1
               ORDER BY recorded_at DESC
               LIMIT $2""",
            domain,
            limit,
        )
        return [dict(r) for r in rows]


async def upsert_monitor_job(
    domain: str,
    schedule: str = "weekly",
    alert_email: str = None,
    next_run=None,
) -> dict:
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """INSERT INTO monitor_jobs (domain, schedule, alert_email, next_run)
               VALUES ($1, $2, $3, $4)
               ON CONFLICT (domain) DO UPDATE
               SET schedule    = EXCLUDED.schedule,
                   alert_email = COALESCE(EXCLUDED.alert_email, monitor_jobs.alert_email),
                   next_run    = EXCLUDED.next_run,
                   active      = true
               RETURNING *""",
            domain,
            schedule,
            alert_email,
            next_run,
        )
        return dict(row)


async def get_due_monitor_jobs() -> list[dict]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """SELECT * FROM monitor_jobs
               WHERE active = true
                 AND (next_run IS NULL OR next_run <= now())
               ORDER BY next_run ASC NULLS FIRST""",
        )
        return [dict(r) for r in rows]


async def update_monitor_job_run(domain: str, next_run):
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """UPDATE monitor_jobs
               SET last_run = now(), next_run = $2
               WHERE domain = $1""",
            domain,
            next_run,
        )


# ---------------------------------------------------------------------------
# CRUD helpers — Pillar 2: Social Intelligence
# ---------------------------------------------------------------------------

async def upsert_company(
    domain: str, name: str = None, icp: dict = None
) -> dict:
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """INSERT INTO companies (domain, name, icp)
               VALUES ($1, $2, $3::jsonb)
               ON CONFLICT (domain) DO UPDATE
               SET name = COALESCE(EXCLUDED.name, companies.name),
                   icp  = COALESCE(EXCLUDED.icp,  companies.icp)
               RETURNING *""",
            domain,
            name,
            json.dumps(icp or {}),
        )
        return dict(row)


async def get_company(domain: str) -> dict | None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT * FROM companies WHERE domain = $1", domain
        )
        return dict(row) if row else None


async def get_company_by_id(company_id: int) -> dict | None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT * FROM companies WHERE id = $1", company_id
        )
        return dict(row) if row else None


async def save_memory_chunk(
    company_id: int,
    content: str,
    embedding: list[float],
    source: str,
    metadata: dict = None,
):
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """INSERT INTO company_memory
                   (company_id, content, embedding, source, metadata)
               VALUES ($1, $2, $3::vector, $4, $5::jsonb)""",
            company_id,
            content,
            embedding,
            source,
            json.dumps(metadata or {}),
        )


async def search_memory(
    company_id: int, query_embedding: list[float], limit: int = 10
) -> list[dict]:
    """Cosine similarity search over company memory chunks."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """SELECT content, source, metadata,
                      1 - (embedding <=> $2::vector) AS similarity
               FROM company_memory
               WHERE company_id = $1
               ORDER BY embedding <=> $2::vector
               LIMIT $3""",
            company_id,
            query_embedding,
            limit,
        )
        return [dict(r) for r in rows]


async def save_slack_message(
    company_id: int,
    channel: str,
    text: str,
    user_id: str,
    ts: str,
):
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """INSERT INTO slack_messages
                   (company_id, channel, text, user_id, ts)
               VALUES ($1, $2, $3, $4, $5)
               ON CONFLICT (ts) DO NOTHING""",
            company_id,
            channel,
            text,
            user_id,
            ts,
        )


async def get_unprocessed_slack_messages(
    company_id: int, limit: int = 200
) -> list[dict]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """SELECT * FROM slack_messages
               WHERE company_id = $1 AND processed = false
               ORDER BY ts ASC
               LIMIT $2""",
            company_id,
            limit,
        )
        return [dict(r) for r in rows]


async def mark_slack_processed(ids: list[int]):
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE slack_messages SET processed = true WHERE id = ANY($1::bigint[])",
            ids,
        )


async def save_content_suggestion(
    company_id: int,
    platform: str,
    content: str,
    type: str,
    week_of: str = None,
) -> dict:
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """INSERT INTO content_suggestions
                   (company_id, platform, content, type, week_of)
               VALUES ($1, $2, $3, $4, $5::date)
               RETURNING *""",
            company_id,
            platform,
            content,
            type,
            week_of,
        )
        return dict(row)


async def get_content_suggestions(
    company_id: int,
    platform: str = None,
    status: str = "pending",
) -> list[dict]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        if platform:
            rows = await conn.fetch(
                """SELECT * FROM content_suggestions
                   WHERE company_id = $1 AND status = $2 AND platform = $3
                   ORDER BY created_at DESC""",
                company_id,
                status,
                platform,
            )
        else:
            rows = await conn.fetch(
                """SELECT * FROM content_suggestions
                   WHERE company_id = $1 AND status = $2
                   ORDER BY created_at DESC""",
                company_id,
                status,
            )
        return [dict(r) for r in rows]


async def update_suggestion_status(suggestion_id: int, status: str):
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE content_suggestions SET status = $2 WHERE id = $1",
            suggestion_id,
            status,
        )


async def save_reddit_opportunity(
    company_id: int,
    subreddit: str,
    thread_url: str,
    thread_title: str,
    type: str,
    suggestion: str,
) -> None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """INSERT INTO reddit_opportunities
                   (company_id, subreddit, thread_url, thread_title, type, suggestion)
               VALUES ($1, $2, $3, $4, $5, $6)
               ON CONFLICT (company_id, thread_url) DO NOTHING""",
            company_id,
            subreddit,
            thread_url,
            thread_title,
            type,
            suggestion,
        )


async def get_reddit_opportunities(
    company_id: int, status: str = "new"
) -> list[dict]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """SELECT * FROM reddit_opportunities
               WHERE company_id = $1 AND status = $2
               ORDER BY found_at DESC""",
            company_id,
            status,
        )
        return [dict(r) for r in rows]


# GSC tokens

async def save_gsc_token(
    company_id: int,
    access_token: str,
    refresh_token: str,
    token_expiry,
    site_url: str,
):
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """INSERT INTO gsc_tokens
                   (company_id, access_token, refresh_token, token_expiry, site_url)
               VALUES ($1, $2, $3, $4, $5)
               ON CONFLICT (company_id) DO UPDATE
               SET access_token  = EXCLUDED.access_token,
                   refresh_token = EXCLUDED.refresh_token,
                   token_expiry  = EXCLUDED.token_expiry,
                   site_url      = EXCLUDED.site_url,
                   updated_at    = now()""",
            company_id,
            access_token,
            refresh_token,
            token_expiry,
            site_url,
        )


async def get_gsc_token(company_id: int) -> dict | None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT * FROM gsc_tokens WHERE company_id = $1", company_id
        )
        return dict(row) if row else None
