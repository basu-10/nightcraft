from datetime import datetime, timezone

import feedparser
from flask import current_app
from sqlalchemy import case

from ..models import Article, SourceFeed
from ..utils import strip_html
from .source_fetch import SourceArticleFetcher


def ingest_articles(limit_per_feed=5, source_feed_ids=None, restage_existing=False):
    created = 0
    created_by_source = {}
    restaged = 0
    restaged_by_source = {}
    duplicates_skipped = 0
    feeds_query = SourceFeed.query.filter_by(active=True)
    if source_feed_ids:
        feeds_query = feeds_query.filter(SourceFeed.id.in_(source_feed_ids))

    # Keep the user-selected source order stable, then fallback to source name.
    if source_feed_ids:
        order_map = {feed_id: idx for idx, feed_id in enumerate(source_feed_ids)}
        feeds_query = feeds_query.order_by(case(order_map, value=SourceFeed.id, else_=len(order_map)), SourceFeed.name.asc())
    else:
        feeds_query = feeds_query.order_by(SourceFeed.name.asc())

    feeds = feeds_query.all()
    source_fetch_enabled = bool(current_app.config.get("SOURCE_FETCH_ENABLED", True))
    fetcher = None
    if source_fetch_enabled:
        fetcher = SourceArticleFetcher(
            user_agent=current_app.config.get("SOURCE_FETCH_USER_AGENT", "DevRadioBot/1.0 (+https://devradio.local)"),
            timeout_seconds=float(current_app.config.get("SOURCE_FETCH_TIMEOUT_SECONDS", 12.0)),
            min_chars=int(current_app.config.get("SOURCE_FETCH_MIN_CHARS", 800)),
            max_chars=int(current_app.config.get("SOURCE_FETCH_MAX_CHARS", 30000)),
            min_delay_seconds=float(current_app.config.get("SOURCE_FETCH_MIN_DELAY_SECONDS", 2.0)),
            jitter_seconds=float(current_app.config.get("SOURCE_FETCH_JITTER_SECONDS", 1.0)),
            max_retries=int(current_app.config.get("SOURCE_FETCH_MAX_RETRIES", 2)),
            retry_backoff_seconds=float(current_app.config.get("SOURCE_FETCH_RETRY_BACKOFF_SECONDS", 2.0)),
            respect_robots=bool(current_app.config.get("SOURCE_FETCH_RESPECT_ROBOTS", True)),
        )

    for feed in feeds:
        parsed = feedparser.parse(feed.feed_url)
        for entry in parsed.entries[:limit_per_feed]:
            source_url = entry.get("link", "")
            title = (entry.get("title") or "Untitled story").strip()
            if not source_url:
                continue

            duplicate = Article.query.filter_by(source_url=source_url).first()
            if duplicate:
                duplicates_skipped += 1
                if restage_existing:
                    changed = False
                    duplicate.source_name = feed.name
                    duplicate.channel_id = feed.channel_id
                    duplicate.title = title

                    fresh_excerpt = strip_html((entry.get("summary") or ""))[:2000]
                    if fresh_excerpt:
                        duplicate.raw_excerpt = fresh_excerpt

                    if duplicate.status != "staged":
                        duplicate.status = "staged"
                        changed = True

                    if fetcher:
                        fetched = fetcher.fetch(source_url)
                        if fetched.status == "ok" and fetched.text:
                            duplicate.source_full_article = fetched.text
                            changed = True

                    if changed:
                        restaged += 1
                        restaged_by_source[feed.name] = restaged_by_source.get(feed.name, 0) + 1
                continue

            published_at = None
            if entry.get("published_parsed"):
                published_at = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)

            source_full_article = None
            if fetcher and source_url:
                fetched = fetcher.fetch(source_url)
                if fetched.status == "ok":
                    source_full_article = fetched.text

            article = Article(
                channel_id=feed.channel_id,
                source_name=feed.name,
                source_url=source_url,
                title=title,
                raw_excerpt=strip_html((entry.get("summary") or ""))[:2000],
                source_full_article=source_full_article,
                published_at=published_at,
                status="staged",
            )
            created += 1
            created_by_source[feed.name] = created_by_source.get(feed.name, 0) + 1
            from ..extensions import db

            db.session.add(article)

    from ..extensions import db

    db.session.commit()
    return created, created_by_source, restaged, restaged_by_source, duplicates_skipped
