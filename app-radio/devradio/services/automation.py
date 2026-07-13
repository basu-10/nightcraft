from __future__ import annotations

import json
from collections import deque
import threading
from pathlib import Path
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qsl, urlencode, urlparse

import feedparser
import requests
from flask import current_app
from sqlalchemy.exc import IntegrityError
from sqlalchemy import case

from ..extensions import db
from ..models import AppSetting, Article, AutomatedSourceAllocation, Channel, Segment, SourceFeed
from .playback import register_breaking_injection
from .settings import get_setting
from ..utils import app_timezone, now_app_timezone, now_utc, parse_datetime, strip_html, to_app_timezone
from .source_fetch import SourceArticleFetcher


ALLOWED_AUTOMATED_SOURCE_KEYS = {
    "google_deepmind_blog",
    "google_for_developers",
    "hugging_face_blog",
    "nvidia_developer_blog",
    "the_linux_foundation_blog",
    "together_ai_blog",
    "github_changelog",
    "docker_blog",
    "jetbrains_blog",
    "mdn_blog",
    "vercel_blog",
    "web_dev",
    "gamesindustry_biz",
    "itch_io_blog",
    "unity_blog",
}

# Cap per-feed scans so a single run stays bounded and lightweight on small servers.
# Admins can raise this from the Automated page if the host has more capacity.
DEFAULT_AUTOMATED_FEED_FETCH_LIMIT = 8
# Hard ceiling on total article fetches per run, regardless of per-feed cap.
DEFAULT_AUTOMATED_MAX_TOTAL_FETCHES = 48
# Wall-clock budget for a single run; once exceeded the run stops accepting new
# fetches so the worker goes back to sleeping instead of hogging the server.
DEFAULT_AUTOMATED_RUN_TIME_BUDGET_SECONDS = 240.0
_ingestion_lock = threading.Lock()
AUTOMATED_FEED_FETCH_LIMIT_SETTING_KEY = "automated_feed_fetch_limit"

RETRYABLE_FAILURE_REASONS = {
    "feed_parse_failed",
    "source_fetch_disabled",
    "fetch_failed",
}

AUTOMATION_TIMESTAMP_FIELDS = {
    "run_started_utc",
    "run_finished_utc",
    "timestamp_utc",
    "retry_timestamp_utc",
}

TRACKING_QUERY_PREFIXES = ("utm_",)
TRACKING_QUERY_KEYS = {
    "gclid",
    "fbclid",
    "mc_cid",
    "mc_eid",
    "igshid",
    "ref",
    "ref_src",
    "source",
}


def _reset_db_session_state() -> None:
    try:
        db.session.rollback()
    except Exception:
        pass


def parse_automated_feed_fetch_limit(raw_value, default: int = DEFAULT_AUTOMATED_FEED_FETCH_LIMIT) -> int:
    try:
        parsed = int(str(raw_value).strip())
    except (TypeError, ValueError):
        return default
    return parsed if parsed >= 0 else default


def get_automated_feed_fetch_limit() -> int:
    return parse_automated_feed_fetch_limit(
        get_setting(AUTOMATED_FEED_FETCH_LIMIT_SETTING_KEY, str(DEFAULT_AUTOMATED_FEED_FETCH_LIMIT)),
        default=DEFAULT_AUTOMATED_FEED_FETCH_LIMIT,
    )


def list_allowed_automated_source_keys() -> list[str]:
    return sorted(ALLOWED_AUTOMATED_SOURCE_KEYS)


def source_key_from_name(name: str) -> str:
    lowered = (name or "").strip().lower()
    cleaned = []
    for ch in lowered:
        if ch.isalnum():
            cleaned.append(ch)
        else:
            cleaned.append("_")
    compact = "".join(cleaned)
    while "__" in compact:
        compact = compact.replace("__", "_")
    return compact.strip("_")


def eligible_automated_feed_ids() -> list[int]:
    feeds = SourceFeed.query.filter_by(active=True).order_by(SourceFeed.name.asc()).all()
    return [feed.id for feed in feeds if source_key_from_name(feed.name) in ALLOWED_AUTOMATED_SOURCE_KEYS]


def list_eligible_automated_feeds() -> list[SourceFeed]:
    allowed_ids = eligible_automated_feed_ids()
    if not allowed_ids:
        return []

    order_map = {feed_id: idx for idx, feed_id in enumerate(allowed_ids)}
    return (
        SourceFeed.query.filter(SourceFeed.id.in_(allowed_ids))
        .order_by(case(order_map, value=SourceFeed.id, else_=len(order_map)), SourceFeed.name.asc())
        .all()
    )


def _as_utc_aware(dt):
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _entry_published_at(entry) -> datetime | None:
    for key in ("published_parsed", "updated_parsed", "created_parsed"):
        parsed = entry.get(key)
        if parsed:
            return datetime(*parsed[:6], tzinfo=timezone.utc)
    return None


def _title_fingerprint(title: str) -> str:
    """First 60 alphanumeric chars of title, lowercased, no whitespace.
    Used to detect duplicate articles when URL-based checks are insufficient."""
    return "".join(ch.lower() for ch in (title or "") if ch.isalnum())[:60]


def _canonical_source_url(raw_url: str) -> str:
    parsed = urlparse((raw_url or "").strip())
    if not parsed.netloc and not parsed.path:
        return ""

    netloc = parsed.netloc.lower()
    if netloc.startswith("www."):
        netloc = netloc[4:]

    path = parsed.path or ""
    if path != "/":
        path = path.rstrip("/")

    filtered_qs = []
    for key, value in parse_qsl(parsed.query, keep_blank_values=True):
        lowered = key.lower()
        if lowered.startswith(TRACKING_QUERY_PREFIXES) or lowered in TRACKING_QUERY_KEYS:
            continue
        filtered_qs.append((lowered, value))
    filtered_qs.sort()

    query = urlencode(filtered_qs, doseq=True)
    canonical = f"{netloc}{path}"
    if query:
        canonical = f"{canonical}?{query}"
    return canonical


def _parse_feed_with_timeout(feed_url: str, timeout_seconds: float = 15.0):
    """Fetch a feed via requests (bounded timeout) then parse its bytes.

    feedparser.parse(url) uses urllib with NO timeout and can hang forever on a
    slow/hanging feed host. That would freeze the automation thread (and the
    server) because the leaked DB connection/pool is never released. Always
    fetch with an explicit timeout first; on failure return an empty parse so
    the caller simply skips the feed instead of blocking.
    """
    try:
        resp = requests.get(
            feed_url,
            timeout=timeout_seconds,
            headers={"User-Agent": "DevRadioBot/1.0 (+https://devradio.local)"},
        )
        resp.raise_for_status()
        return feedparser.parse(resp.content)
    except Exception:
        return feedparser.parse("")


def _build_fetcher() -> SourceArticleFetcher | None:
    source_fetch_enabled = bool(current_app.config.get("SOURCE_FETCH_ENABLED", True))
    if not source_fetch_enabled:
        return None

    return SourceArticleFetcher(
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


def _next_channel_queue_time(channel_id: int, now_dt, spacing_minutes: int):
    last_segment = (
        Segment.query.filter_by(channel_id=channel_id)
        .order_by(Segment.scheduled_at_utc.desc())
        .first()
    )
    base = _as_utc_aware(now_dt)
    if not last_segment:
        return base

    last_scheduled = _as_utc_aware(last_segment.scheduled_at_utc)
    return max(base, last_scheduled + timedelta(minutes=spacing_minutes))


def _upsert_run_meta(key: str, value: str) -> None:
    setting = AppSetting.query.filter_by(key=key).first()
    if setting:
        setting.value = value
        setting.encrypted = False
    else:
        db.session.add(AppSetting(key=key, value=value, encrypted=False))


def _automation_log_dir() -> Path:
    base_dir = Path(current_app.instance_path) / "automation_logs"
    base_dir.mkdir(parents=True, exist_ok=True)
    return base_dir


def _json_default(value):
    if isinstance(value, datetime):
        converted = to_app_timezone(value)
        if converted is not None:
            return converted.isoformat()
    return str(value)


def _convert_payload_timestamps_to_app_timezone(payload) -> bool:
    changed = False
    app_tz = app_timezone()

    if isinstance(payload, dict):
        for key, value in payload.items():
            if key in AUTOMATION_TIMESTAMP_FIELDS and isinstance(value, str):
                parsed = parse_datetime(value)
                if parsed is None:
                    continue
                converted = parsed.astimezone(app_tz).isoformat()
                if converted != value:
                    payload[key] = converted
                    changed = True
            elif isinstance(value, (dict, list)):
                if _convert_payload_timestamps_to_app_timezone(value):
                    changed = True
        return changed

    if isinstance(payload, list):
        for item in payload:
            if isinstance(item, (dict, list)) and _convert_payload_timestamps_to_app_timezone(item):
                changed = True
    return changed


def migrate_automation_log_timestamps_to_app_timezone() -> dict:
    log_dir = _automation_log_dir()
    files_updated = 0
    jsonl_rows_updated = 0
    errors = []

    file_candidates = sorted(log_dir.glob("run_*.json"))
    latest_file = log_dir / "latest.json"
    if latest_file.exists():
        file_candidates.append(latest_file)

    for path in file_candidates:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            errors.append(f"{path.name}: read failed ({exc})")
            continue

        if _convert_payload_timestamps_to_app_timezone(payload):
            try:
                serialized = json.dumps(payload, ensure_ascii=True, default=_json_default)
                path.write_text(serialized + "\n", encoding="utf-8")
                files_updated += 1
            except Exception as exc:
                errors.append(f"{path.name}: write failed ({exc})")

    jsonl_file = log_dir / "runs.jsonl"
    if jsonl_file.exists():
        try:
            lines = jsonl_file.read_text(encoding="utf-8").splitlines()
            rewritten = []
            for line in lines:
                if not line.strip():
                    continue
                try:
                    payload = json.loads(line)
                except Exception:
                    rewritten.append(line)
                    continue

                if _convert_payload_timestamps_to_app_timezone(payload):
                    jsonl_rows_updated += 1
                rewritten.append(json.dumps(payload, ensure_ascii=True, default=_json_default))

            if jsonl_rows_updated:
                jsonl_file.write_text("\n".join(rewritten) + "\n", encoding="utf-8")
        except Exception as exc:
            errors.append(f"runs.jsonl: rewrite failed ({exc})")

    setting_updated = False
    setting = AppSetting.query.filter_by(key="automated_last_run_utc").first()
    if setting and setting.value:
        parsed_setting = parse_datetime(setting.value)
        if parsed_setting is not None:
            converted_setting = parsed_setting.astimezone(app_timezone()).isoformat()
            if converted_setting != setting.value:
                setting.value = converted_setting
                setting.encrypted = False
                setting_updated = True

    if setting_updated:
        db.session.commit()

    return {
        "files_updated": files_updated,
        "jsonl_rows_updated": jsonl_rows_updated,
        "setting_updated": setting_updated,
        "errors": errors,
    }


def _persist_run_log(payload: dict) -> str:
    run_id = payload["run_id"]
    log_dir = _automation_log_dir()
    run_file = log_dir / f"{run_id}.json"
    latest_file = log_dir / "latest.json"
    jsonl_file = log_dir / "runs.jsonl"

    serialized = json.dumps(payload, ensure_ascii=True, default=_json_default)
    run_file.write_text(serialized + "\n", encoding="utf-8")
    latest_file.write_text(serialized + "\n", encoding="utf-8")
    with jsonl_file.open("a", encoding="utf-8") as handle:
        handle.write(serialized + "\n")

    _prune_automation_logs(log_dir)
    return str(run_file)


def _prune_automation_logs(log_dir: Path) -> None:
    max_run_files = int(current_app.config.get("AUTOMATED_LOG_MAX_RUN_FILES", 500))
    max_jsonl_lines = int(current_app.config.get("AUTOMATED_LOG_MAX_JSONL_LINES", 5000))

    run_files = sorted(log_dir.glob("run_*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    if max_run_files > 0 and len(run_files) > max_run_files:
        for old_file in run_files[max_run_files:]:
            try:
                old_file.unlink(missing_ok=True)
            except Exception:
                current_app.logger.exception("Failed pruning old automation log file: %s", old_file)

    if max_jsonl_lines <= 0:
        return

    jsonl_file = log_dir / "runs.jsonl"
    if not jsonl_file.exists():
        return

    try:
        tail = deque(jsonl_file.open("r", encoding="utf-8"), maxlen=max_jsonl_lines)
        if len(tail) >= max_jsonl_lines:
            jsonl_file.write_text("".join(tail), encoding="utf-8")
    except Exception:
        current_app.logger.exception("Failed pruning automation JSONL log")


def list_recent_automation_logs(limit=15):
    log_dir = _automation_log_dir()
    results = []
    for run_file in sorted(log_dir.glob("run_*.json"), key=lambda p: p.stat().st_mtime, reverse=True):
        try:
            payload = json.loads(run_file.read_text(encoding="utf-8"))
            summary = payload.get("summary", {})
            results.append(
                {
                    "run_id": payload.get("run_id", run_file.stem),
                    "run_started_utc": payload.get("run_started_utc", ""),
                    "new_articles": summary.get("new_articles", 0),
                    "duplicates_skipped": summary.get("duplicates_skipped", 0),
                    "timestamp_skipped": summary.get("timestamp_skipped", 0),
                    "fetch_failures": summary.get("fetch_failures", 0),
                    "fatal_error": summary.get("fatal_error", ""),
                    "log_path": str(run_file),
                }
            )
            if len(results) >= limit:
                break
        except Exception:
            continue
    return results


def read_automation_run_log(run_id: str):
    safe_run_id = (run_id or "").strip()
    if not safe_run_id.startswith("run_"):
        return None
    if any(ch for ch in safe_run_id if not (ch.isalnum() or ch in {"_", "-"})):
        return None

    run_file = _automation_log_dir() / f"{safe_run_id}.json"
    if not run_file.exists():
        return None
    try:
        return json.loads(run_file.read_text(encoding="utf-8"))
    except Exception:
        return None


def retry_failed_automated_entries(run_id: str, failure_indexes: list[int] | None = None):
    payload = read_automation_run_log(run_id)
    if not payload:
        return {"retried": 0, "queued": 0, "still_failed": 0, "errors": ["Run log not found."]}

    failures = payload.get("failures", [])
    if not isinstance(failures, list):
        return {"retried": 0, "queued": 0, "still_failed": 0, "errors": ["Run log has invalid failure data."]}

    if failure_indexes is None:
        selected = list(enumerate(failures))
    else:
        selected = []
        for idx in failure_indexes:
            if 0 <= idx < len(failures):
                selected.append((idx, failures[idx]))

    spacing_minutes = int(current_app.config.get("AUTOMATED_SEGMENT_SPACING_MINUTES", 8))
    fetcher = _build_fetcher()
    eligible_ids = set(eligible_automated_feed_ids())
    queue_time_by_channel = {}
    for channel in Channel.query.order_by(Channel.id.asc()).all():
        queue_time_by_channel[channel.id] = _next_channel_queue_time(channel.id, now_utc(), spacing_minutes)

    retried = 0
    queued = 0
    still_failed = 0
    errors = []
    new_segment_ids_by_channel = {}

    for idx, failure in selected:
        reason = (failure or {}).get("reason", "")
        if reason not in RETRYABLE_FAILURE_REASONS:
            continue

        feed_id = (failure or {}).get("feed_id")
        channel_id = (failure or {}).get("channel_id")
        source_url = (failure or {}).get("source_url", "")
        title = (failure or {}).get("title", "Untitled story")
        source_name = (failure or {}).get("source_name", "Unknown Source")
        raw_excerpt = (failure or {}).get("entry_summary", "")

        if not feed_id or not channel_id or not source_url:
            continue

        source_feed = db.session.get(SourceFeed, int(feed_id))
        if not source_feed:
            failures[idx]["retry_status"] = "source_feed_missing"
            failures[idx]["retry_timestamp_utc"] = now_app_timezone().isoformat()
            still_failed += 1
            continue

        if not source_feed.active or source_feed.id not in eligible_ids:
            failures[idx]["retry_status"] = "ineligible_or_inactive"
            failures[idx]["retry_timestamp_utc"] = now_app_timezone().isoformat()
            still_failed += 1
            continue

        allocation = AutomatedSourceAllocation.query.filter_by(source_feed_id=source_feed.id).first()
        if not allocation or allocation.channel_id != channel_id:
            failures[idx]["retry_status"] = "allocation_changed"
            failures[idx]["retry_timestamp_utc"] = now_app_timezone().isoformat()
            still_failed += 1
            continue

        retried += 1
        if Article.query.filter_by(source_url=source_url).first():
            failures[idx]["retry_status"] = "duplicate_now"
            failures[idx]["retry_timestamp_utc"] = now_app_timezone().isoformat()
            still_failed += 1
            continue

        if not fetcher:
            failures[idx]["retry_status"] = "source_fetch_disabled"
            failures[idx]["retry_timestamp_utc"] = now_app_timezone().isoformat()
            still_failed += 1
            continue

        fetched = fetcher.fetch(source_url)
        if fetched.status != "ok" or not fetched.text:
            failures[idx]["retry_status"] = f"fetch_failed:{fetched.status}"
            failures[idx]["retry_timestamp_utc"] = now_app_timezone().isoformat()
            still_failed += 1
            continue

        try:
            with db.session.begin_nested():
                article = Article(
                    channel_id=channel_id,
                    source_name=source_name,
                    source_url=source_url,
                    title=title,
                    summary=(strip_html(raw_excerpt)[:300]) or fetched.text[:300],
                    raw_excerpt=strip_html(raw_excerpt)[:2000],
                    source_full_article=fetched.text,
                    internal_content=fetched.text,
                    short_headline=title[:160],
                    status="approved",
                )
                db.session.add(article)
                db.session.flush()

                queue_time = queue_time_by_channel.get(channel_id, _as_utc_aware(now_utc()))
                segment = Segment(
                    article_id=article.id,
                    channel_id=channel_id,
                    scheduled_at_utc=queue_time,
                    status="queued",
                    transcript=fetched.text,
                    duration_seconds=max(20, min(300, len(fetched.text) // 12 or 90)),
                )
                db.session.add(segment)
                new_segment_ids_by_channel.setdefault(channel_id, []).append(segment.id)

            queue_time_by_channel[channel_id] = queue_time + timedelta(minutes=spacing_minutes)
            failures[idx]["retry_status"] = "queued"
            failures[idx]["retry_timestamp_utc"] = now_app_timezone().isoformat()
            queued += 1
        except IntegrityError:
            failures[idx]["retry_status"] = "duplicate_now"
            failures[idx]["retry_timestamp_utc"] = now_app_timezone().isoformat()
            still_failed += 1

    payload["failures"] = failures
    payload["retry_summary"] = {
        "retried": retried,
        "queued": queued,
        "still_failed": still_failed,
    }

    if new_segment_ids_by_channel:
        payload["retry_breaking"] = []

    try:
        _persist_run_log(payload)
    except Exception as exc:
        errors.append(f"Failed updating run log file: {exc}")

    db.session.commit()

    for channel_id, segment_ids in new_segment_ids_by_channel.items():
        try:
            breaking_result = register_breaking_injection(channel_id, segment_ids, source="automation_retry")
            payload.setdefault("retry_breaking", []).append(
                {
                    "channel_id": channel_id,
                    "segment_ids": segment_ids,
                    "breaking": breaking_result,
                }
            )
        except Exception as exc:
            errors.append(f"Breaking-state update failed for channel {channel_id}: {exc}")

    if payload.get("retry_breaking"):
        try:
            _persist_run_log(payload)
        except Exception as exc:
            errors.append(f"Failed writing retry breaking details: {exc}")

    return {
        "retried": retried,
        "queued": queued,
        "still_failed": still_failed,
        "errors": errors,
    }


def run_automated_ingestion(limit_per_feed=None, skip_timestamp_gate=False):
    if not _ingestion_lock.acquire(blocking=True, timeout=10):
        return {
            "run_id": "skipped_concurrent",
            "log_path": None,
            "feed_fetch_limit": 0,
            "new_articles": 0,
            "timestamp_skipped": 0,
            "duplicates_skipped": 0,
            "fetch_failures": 0,
            "processed_channels": 0,
            "processed_feeds": 0,
            "breaking_updates": 0,
            "fatal_error": "Another automation run is already in progress. Try again shortly.",
            "failures": [],
        }
    try:
        # Cross-process guard so the systemd timer and a manual run-now trigger
        # can never run a second ingestion while one is already in flight.
        from .process_lock import try_run_with_process_lock

        app = current_app._get_current_object()
        return try_run_with_process_lock(
            app,
            _run_automated_ingestion_locked,
            limit_per_feed=limit_per_feed,
            skip_timestamp_gate=skip_timestamp_gate,
        )
    finally:
        _ingestion_lock.release()


def _run_automated_ingestion_locked(limit_per_feed=None, skip_timestamp_gate=False):
    _reset_db_session_state()

    # Lazy import to avoid a module-level circular dependency: ingestion.py
    # imports helpers from this module, so importing it at the top would cycle.
    from .ingestion import _extract_feed_entry_image
    limit_per_feed = get_automated_feed_fetch_limit() if limit_per_feed is None else parse_automated_feed_fetch_limit(limit_per_feed)
    spacing_minutes = int(current_app.config.get("AUTOMATED_SEGMENT_SPACING_MINUTES", 8))
    run_started = now_app_timezone()
    fetcher = _build_fetcher()
    run_id = f"run_{run_started.strftime('%Y%m%d_%H%M%S_%f')}"

    max_total_fetches = int(current_app.config.get("AUTOMATED_MAX_TOTAL_FETCHES", DEFAULT_AUTOMATED_MAX_TOTAL_FETCHES))
    run_time_budget_seconds = float(current_app.config.get("AUTOMATED_RUN_TIME_BUDGET_SECONDS", DEFAULT_AUTOMATED_RUN_TIME_BUDGET_SECONDS))
    run_deadline = run_started + timedelta(seconds=run_time_budget_seconds)
    total_fetches = 0
    budget_reached = False

    eligible_ids = set(eligible_automated_feed_ids())
    if not eligible_ids:
        run_payload = {
            "run_id": run_id,
            "run_started_utc": run_started.isoformat(),
            "run_finished_utc": now_app_timezone().isoformat(),
            "events": [{"event": "no_eligible_feeds", "timestamp_utc": now_app_timezone().isoformat()}],
            "failures": [],
            "summary": {
                "feed_fetch_limit": limit_per_feed,
                "new_articles": 0,
                "duplicates_skipped": 0,
                "fetch_failures": 0,
                "processed_channels": 0,
                "processed_feeds": 0,
                "fatal_error": "",
            },
        }
        log_path = ""
        try:
            log_path = _persist_run_log(run_payload)
        except Exception:
            current_app.logger.exception("Failed persisting automation run log")

        _upsert_run_meta("automated_last_run_utc", run_started.isoformat())
        _upsert_run_meta("automated_last_run_summary", "No eligible automated feeds found.")
        db.session.commit()
        return {
            "run_id": run_id,
            "log_path": log_path,
            "feed_fetch_limit": limit_per_feed,
            "new_articles": 0,
            "timestamp_skipped": 0,
            "duplicates_skipped": 0,
            "fetch_failures": 0,
            "processed_channels": 0,
            "processed_feeds": 0,
            "breaking_updates": 0,
            "fatal_error": "",
            "failures": [],
        }

    allocations = (
        AutomatedSourceAllocation.query.join(SourceFeed, AutomatedSourceAllocation.source_feed_id == SourceFeed.id)
        .filter(SourceFeed.active.is_(True), SourceFeed.id.in_(eligible_ids))
        .order_by(AutomatedSourceAllocation.channel_id.asc(), SourceFeed.name.asc())
        .all()
    )

    queue_time_by_channel = {}
    for channel in Channel.query.order_by(Channel.id.asc()).all():
        queue_time_by_channel[channel.id] = _next_channel_queue_time(channel.id, run_started, spacing_minutes)

    new_articles = 0
    duplicates_skipped = 0
    timestamp_skipped = 0
    fetch_failures = 0
    processed_feeds = 0
    touched_channels = set()
    failures = []
    events = []
    breaking_updates = []
    new_segment_ids_by_channel = {}

    seen_source_urls = set()
    seen_canonical_urls = set()
    seen_title_fingerprints = set()
    existing_articles = db.session.query(Article.source_url, Article.title).all()
    for article_source_url, article_title in existing_articles:
        if article_source_url:
            seen_source_urls.add(article_source_url)
            canonical = _canonical_source_url(article_source_url)
            if canonical:
                seen_canonical_urls.add(canonical)
        fp = _title_fingerprint(article_title or "")
        if fp:
            seen_title_fingerprints.add(fp)

    run_payload = {
        "run_id": run_id,
        "run_started_utc": run_started.isoformat(),
        "events": events,
        "failures": failures,
    }

    if not fetcher:
        events.append({"event": "source_fetch_disabled", "timestamp_utc": now_app_timezone().isoformat()})

    fatal_error = ""
    try:
        for allocation in allocations:
            if budget_reached:
                break
            feed = allocation.source_feed
            channel_id = allocation.channel_id
            touched_channels.add(channel_id)
            processed_feeds += 1
            candidate_count = 0

            try:
                parsed = _parse_feed_with_timeout(feed.feed_url)
            except Exception as exc:
                fetch_failures += 1
                failures.append(
                    {
                        "reason": "feed_parse_failed",
                        "feed_id": feed.id,
                        "feed_url": feed.feed_url,
                        "source_name": feed.name,
                        "channel_id": channel_id,
                        "error": str(exc),
                    }
                )
                continue

            for entry in parsed.entries:
                published_at = _entry_published_at(entry)

                candidate_count += 1
                if limit_per_feed and candidate_count > limit_per_feed:
                    break

                source_url = entry.get("link", "")
                title = (entry.get("title") or "Untitled story").strip()
                entry_summary = entry.get("summary") or ""
                canonical_source_url = _canonical_source_url(source_url)
                entry_fingerprint = _title_fingerprint(title)

                if not source_url:
                    failures.append(
                        {
                            "reason": "missing_source_url",
                            "feed_id": feed.id,
                            "feed_url": feed.feed_url,
                            "source_name": feed.name,
                            "channel_id": channel_id,
                            "title": title,
                        }
                    )
                    continue

                if source_url in seen_source_urls:
                    duplicates_skipped += 1
                    continue

                if canonical_source_url and canonical_source_url in seen_canonical_urls:
                    duplicates_skipped += 1
                    continue

                if not published_at and entry_fingerprint and entry_fingerprint in seen_title_fingerprints:
                    duplicates_skipped += 1
                    continue

                if not fetcher:
                    fetch_failures += 1
                    failures.append(
                        {
                            "reason": "source_fetch_disabled",
                            "feed_id": feed.id,
                            "feed_url": feed.feed_url,
                            "source_name": feed.name,
                            "channel_id": channel_id,
                            "source_url": source_url,
                            "title": title,
                            "entry_summary": entry_summary,
                        }
                    )
                    continue

                if budget_reached or total_fetches >= max_total_fetches or now_utc() >= run_deadline:
                    budget_reached = True
                    break

                fetched = fetcher.fetch(source_url)
                total_fetches += 1
                if fetched.status != "ok" or not fetched.text:
                    fetch_failures += 1
                    failures.append(
                        {
                            "reason": "fetch_failed",
                            "fetch_status": fetched.status,
                            "feed_id": feed.id,
                            "feed_url": feed.feed_url,
                            "source_name": feed.name,
                            "channel_id": channel_id,
                            "source_url": source_url,
                            "title": title,
                            "entry_summary": entry_summary,
                        }
                    )
                    continue

                # Prefer the feed-provided image; fall back to the page scrape.
                entry_image = _extract_feed_entry_image(entry) or fetched.image_url

                try:
                    with db.session.begin_nested():
                        article = Article(
                            channel_id=channel_id,
                            source_name=feed.name,
                            source_url=source_url,
                            title=title,
                            summary=(strip_html(entry_summary)[:300]) or fetched.text[:300],
                            raw_excerpt=strip_html(entry_summary)[:2000],
                            source_full_article=fetched.text,
                            internal_content=fetched.text,
                            image_url=entry_image,
                            short_headline=title[:160],
                            published_at=published_at,
                            status="approved",
                        )
                        db.session.add(article)
                        db.session.flush()

                        queue_time = queue_time_by_channel.get(channel_id, _as_utc_aware(run_started))
                        segment = Segment(
                            article_id=article.id,
                            channel_id=channel_id,
                            scheduled_at_utc=queue_time,
                            status="queued",
                            transcript=fetched.text,
                            duration_seconds=max(20, min(300, len(fetched.text) // 12 or 90)),
                        )
                        db.session.add(segment)
                        db.session.flush()
                        _article_id = article.id
                        _segment_id = segment.id
                        new_segment_ids_by_channel.setdefault(channel_id, []).append(_segment_id)

                    # Commit immediately so subsequent fetches see the latest persisted state.
                    db.session.commit()

                    queue_time_by_channel[channel_id] = queue_time + timedelta(minutes=spacing_minutes)
                    new_articles += 1

                    seen_source_urls.add(source_url)
                    if canonical_source_url:
                        seen_canonical_urls.add(canonical_source_url)
                    if entry_fingerprint:
                        seen_title_fingerprints.add(entry_fingerprint)

                    events.append(
                        {
                            "event": "queued",
                            "timestamp_utc": now_app_timezone().isoformat(),
                            "article_id": _article_id,
                            "channel_id": channel_id,
                            "source_name": feed.name,
                            "source_url": source_url,
                        }
                    )
                except IntegrityError:
                    duplicates_skipped += 1
                    failures.append(
                        {
                            "reason": "duplicate_insert_race",
                            "feed_id": feed.id,
                            "feed_url": feed.feed_url,
                            "source_name": feed.name,
                            "channel_id": channel_id,
                            "source_url": source_url,
                            "title": title,
                        }
                    )

        if budget_reached:
            events.append(
                {
                    "event": "run_budget_reached",
                    "timestamp_utc": now_app_timezone().isoformat(),
                    "total_fetches": total_fetches,
                    "max_total_fetches": max_total_fetches,
                }
            )

    except Exception as exc:
        fatal_error = str(exc)
        current_app.logger.exception("Automated ingestion failed during run")

    # Commit feed/article updates before metadata queries to avoid query-triggered autoflush lock failures.
    try:
        db.session.commit()
    except Exception as exc:
        db.session.rollback()
        if not fatal_error:
            fatal_error = str(exc)
        current_app.logger.exception("Failed committing automated ingestion updates")

    _upsert_run_meta("automated_last_run_utc", run_started.isoformat())
    summary = (
        f"Queued {new_articles} new articles. "
        f"Skipped duplicates: {duplicates_skipped}. "
        f"Skipped due full-article fetch failures: {fetch_failures}."
    )
    if budget_reached:
        summary = (
            f"{summary} Stopped early at run budget "
            f"(processed {total_fetches} fetches) to keep the server responsive."
        )
    if fatal_error:
        summary = f"{summary} Fatal error: {fatal_error}"
    _upsert_run_meta("automated_last_run_summary", summary)

    run_payload["summary"] = {
        "feed_fetch_limit": limit_per_feed,
        "new_articles": new_articles,
        "timestamp_skipped": timestamp_skipped,
        "duplicates_skipped": duplicates_skipped,
        "fetch_failures": fetch_failures,
        "processed_channels": len(touched_channels),
        "processed_feeds": processed_feeds,
        "total_fetches": total_fetches,
        "budget_reached": budget_reached,
        "fatal_error": fatal_error,
    }
    run_payload["run_finished_utc"] = now_app_timezone().isoformat()

    log_path = ""
    try:
        log_path = _persist_run_log(run_payload)
    except Exception as exc:
        current_app.logger.exception("Failed persisting automation run log")
        summary = f"{summary} Log write failed: {exc}"
        _upsert_run_meta("automated_last_run_summary", summary)

    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        current_app.logger.exception("Failed committing automated ingestion metadata")

    for channel_id, segment_ids in new_segment_ids_by_channel.items():
        try:
            breaking_result = register_breaking_injection(channel_id, segment_ids, source="automation_run")
            breaking_updates.append(
                {
                    "channel_id": channel_id,
                    "segment_ids": segment_ids,
                    "breaking": breaking_result,
                }
            )
        except Exception as exc:
            failures.append(
                {
                    "reason": "breaking_state_update_failed",
                    "channel_id": channel_id,
                    "error": str(exc),
                }
            )

    if breaking_updates:
        run_payload.setdefault("summary", {})["breaking_updates"] = len(breaking_updates)
        run_payload["breaking_updates"] = breaking_updates
        try:
            _persist_run_log(run_payload)
        except Exception:
            current_app.logger.exception("Failed writing breaking update details to automation log")

    return {
        "run_id": run_id,
        "log_path": log_path,
        "feed_fetch_limit": limit_per_feed,
        "new_articles": new_articles,
        "timestamp_skipped": timestamp_skipped,
        "duplicates_skipped": duplicates_skipped,
        "fetch_failures": fetch_failures,
        "processed_channels": len(touched_channels),
        "processed_feeds": processed_feeds,
        "breaking_updates": len(breaking_updates),
        "fatal_error": fatal_error,
        "failures": failures,
    }
