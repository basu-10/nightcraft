import click
from flask import current_app

from .extensions import db
from .models import Article, Channel, LocalCredential, Segment, SourceFeed, UserProfile
from .services.automation import migrate_automation_log_timestamps_to_app_timezone, run_automated_ingestion
from .services.ingestion import ingest_articles
from .services.settings import get_setting
from .services.tts import synthesize_speech
from .utils import now_utc

DEFAULT_CHANNELS = [
    {
        "slug": "all-in-ai",
        "name": "All In AI",
        "description": "AI breakthroughs, launches, policy shifts, and practical workflows.",
    },
    {
        "slug": "united-states-of-web-dev",
        "name": "United States of Web Dev",
        "description": "Web platforms, frontend tooling, backend releases, and standards updates.",
    },
    {
        "slug": "a-game-a-day",
        "name": "A game a day...",
        "description": "Game development engines, launches, studio insights, and creator economy trends.",
    },
]

DEFAULT_FEEDS = {
    "all-in-ai": [
        ("OpenAI Blog", "https://openai.com/news/rss.xml"),
        ("Google DeepMind Blog", "https://deepmind.google/blog/rss.xml"),
        ("Hugging Face Blog", "https://huggingface.co/blog/feed.xml"),
        ("Google for Developers", "https://developers.googleblog.com/feeds/posts/default?alt=rss"),
        ("NVIDIA Developer Blog", "https://developer.nvidia.com/blog/feed/"),
        ("PyTorch Blog", "https://pytorch.org/feed.xml"),
        ("The Linux Foundation Blog", "https://www.linuxfoundation.org/blog/rss.xml"),
        ("Together AI Blog", "https://www.together.ai/blog/rss.xml"),
    ],
    "united-states-of-web-dev": [
        ("GitHub Changelog", "https://github.blog/changelog/feed/"),
        ("Web.dev", "https://web.dev/feed.xml"),
        ("MDN Blog", "https://developer.mozilla.org/en-US/blog/rss.xml"),
        ("CSS-Tricks", "https://css-tricks.com/feed/"),
        ("Docker Blog", "https://www.docker.com/blog/feed/"),
        ("JetBrains Blog", "https://blog.jetbrains.com/feed/"),
        ("Node.js Blog", "https://nodejs.org/en/feed/blog.xml"),
        ("Vercel Blog", "https://vercel.com/atom"),
    ],
    "a-game-a-day": [
        ("GamesIndustry.biz", "https://www.gamesindustry.biz/feed"),
        ("itch.io Blog", "https://itch.io/blog.rss"),
        ("Unity Blog", "https://blog.unity.com/feed"),
        ("Unreal Engine", "https://www.unrealengine.com/en-US/feed"),
        ("Godot Engine News", "https://godotengine.org/rss.xml"),
        ("Blender News", "https://www.blender.org/feed/"),
        ("GameDev.net", "https://gamedev.net/articles/news/?rss=1"),
    ],
}


def register_cli(app):
    @app.cli.command("setup")
    def setup():
        db.create_all()
        _seed_channels_and_feeds()
        _seed_accounts()
        click.echo("Setup complete.")

    @app.cli.command("ingest-feeds")
    def ingest_feeds():
        created, created_by_source, restaged, restaged_by_source, duplicates_skipped = ingest_articles(limit_per_feed=6)
        if created_by_source:
            source_breakdown = ", ".join(f"{source}: {count}" for source, count in created_by_source.items())
            click.echo(f"Ingestion complete. New staged articles: {created}. {source_breakdown}")
        else:
            click.echo(f"Ingestion complete. New staged articles: {created}")

        if restaged_by_source:
            restaged_breakdown = ", ".join(f"{source}: {count}" for source, count in restaged_by_source.items())
            click.echo(f"Restaged existing articles: {restaged}. {restaged_breakdown}")
        elif duplicates_skipped:
            click.echo(f"Skipped existing duplicate URLs: {duplicates_skipped}")

    @app.cli.command("build-audio")
    def build_audio():
        api_key = get_setting("openrouter_api_key", default="")
        count = 0
        segments = (
            Segment.query.join(Article)
            .filter(Segment.status == "queued")
            .filter(Article.status == "approved")
            .order_by(Segment.scheduled_at_utc.asc())
            .all()
        )
        for segment in segments:
            script = segment.article.narration_script or segment.article.short_headline or segment.article.title
            audio_url, model = synthesize_speech(script, api_key, segment.id)
            segment.audio_url = audio_url
            segment.tts_model = model
            segment.duration_seconds = max(20, min(120, len(script) // 12))
            segment.status = "ready"
            count += 1

        db.session.commit()
        click.echo(f"Audio build complete. Segments updated: {count}")

    @app.cli.command("advance-radio")
    def advance_radio():
        now = now_utc()
        moved = 0
        segments = Segment.query.filter(Segment.status.in_(["queued", "ready", "playing"]))
        for segment in segments:
            if segment.scheduled_at_utc <= now and segment.status != "played":
                segment.status = "playing" if segment.audio_url else "queued"
            if segment.duration_seconds and segment.scheduled_at_utc <= now:
                end = segment.scheduled_at_utc.timestamp() + segment.duration_seconds
                if now.timestamp() > end:
                    segment.status = "played"
                    moved += 1

        db.session.commit()
        click.echo(f"Radio advanced. Segments marked played: {moved}")

    @app.cli.command("automated-run")
    def automated_run():
        result = run_automated_ingestion()
        fetch_limit_label = (
            "full feed"
            if result.get("feed_fetch_limit") == 0
            else f"top {result.get('feed_fetch_limit', 0)} item(s) per feed"
        )
        click.echo(
            "Automated run complete. "
            f"Fetch limit: {fetch_limit_label}. "
            f"Run ID: {result.get('run_id', 'n/a')}. "
            f"Queued new: {result['new_articles']}, duplicates skipped: {result['duplicates_skipped']}, "
            f"full-article fetch failures: {result['fetch_failures']}, "
            f"channels touched: {result['processed_channels']}, feeds processed: {result['processed_feeds']}, "
            f"fatal error: {result.get('fatal_error') or 'none'}, "
            f"log: {result.get('log_path', 'not written')}"
        )

    @app.cli.command("migrate-automation-log-timezone")
    def migrate_automation_log_timezone():
        result = migrate_automation_log_timestamps_to_app_timezone()
        click.echo(
            "Automation log timezone migration complete. "
            f"Files updated: {result['files_updated']}, "
            f"JSONL rows updated: {result['jsonl_rows_updated']}, "
            f"App setting updated: {result['setting_updated']}."
        )
        if result["errors"]:
            click.echo("Warnings:")
            for err in result["errors"]:
                click.echo(f"- {err}")


def _seed_channels_and_feeds():
    for entry in DEFAULT_CHANNELS:
        channel = Channel.query.filter_by(slug=entry["slug"]).first()
        if not channel:
            channel = Channel(**entry)
            db.session.add(channel)
            db.session.flush()

        for name, url in DEFAULT_FEEDS[entry["slug"]]:
            feed = SourceFeed.query.filter_by(channel_id=channel.id, feed_url=url).first()
            if not feed:
                db.session.add(SourceFeed(channel_id=channel.id, name=name, feed_url=url, kind="rss"))

    db.session.commit()


def _seed_accounts():
    defaults = [
        ("admin", "admin123", "admin"),
        ("testuser", "test123", "listener"),
    ]
    for username, password, role in defaults:
        user = LocalCredential.query.filter_by(username=username).first()
        if not user:
            user = LocalCredential(username=username, role=role)
            user.set_password(password)
            db.session.add(user)
            db.session.flush()
        else:
            user.role = role
            user.set_password(password)

        profile = UserProfile.query.filter_by(user_id=str(user.id)).first()
        if not profile:
            db.session.add(
                UserProfile(
                    user_id=str(user.id),
                    username=user.username,
                    is_admin=user.is_admin,
                    timezone_name="Asia/Kolkata",
                )
            )
        else:
            profile.username = user.username
            profile.is_admin = user.is_admin

    db.session.commit()
