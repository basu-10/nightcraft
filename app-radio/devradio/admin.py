from datetime import timedelta, timezone
from itertools import groupby

from flask import Blueprint, flash, redirect, render_template, request, url_for
from sqlalchemy import or_

from .auth.current_user import get_current_user
from .extensions import db
from .guards import admin_required, auth_required
from .models import Article, AutomatedSourceAllocation, Channel, SavedStory, Segment, SourceFeed, UserProfile
from .services.playback import build_channel_playback_plan, list_recent_breaking_events, register_breaking_injection
from .services.automation import (
    RETRYABLE_FAILURE_REASONS,
    AUTOMATED_FEED_FETCH_LIMIT_SETTING_KEY,
    eligible_automated_feed_ids,
    get_automated_feed_fetch_limit,
    list_eligible_automated_feeds,
    list_allowed_automated_source_keys,
    list_recent_automation_logs,
    parse_automated_feed_fetch_limit,
    read_automation_run_log,
    retry_failed_automated_entries,
    run_automated_ingestion,
    source_key_from_name,
)
from .services.ingestion import ingest_articles
from .services.settings import get_setting, get_setting_int, upsert_setting
from .services.summarizer import generate_editorial_bundle
from .utils import now_utc, strip_html

bp = Blueprint("admin", __name__, url_prefix="/admin")

TICKER_REFRESH_SECONDS_SETTING_KEY = "ticker_refresh_seconds"
DEFAULT_TICKER_REFRESH_SECONDS = 90


def _as_utc_aware(dt):
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _next_queue_time(channel_id, spacing_minutes=8):
    """Compute the next queue time with timezone-safe UTC datetimes."""
    last_segment = (
        Segment.query.filter_by(channel_id=channel_id)
        .order_by(Segment.scheduled_at_utc.desc())
        .first()
    )
    base = _as_utc_aware(now_utc())
    if not last_segment:
        return base
    last_scheduled = _as_utc_aware(last_segment.scheduled_at_utc)
    return max(base, last_scheduled + timedelta(minutes=spacing_minutes))


@bp.route("/")
@auth_required
@admin_required
def dashboard():
    return redirect(url_for("admin.stage_one"))


@bp.route("/content")
@auth_required
@admin_required
def content():
    channel_board = []
    now = _as_utc_aware(now_utc())
    channels = Channel.query.order_by(Channel.name.asc()).all()

    for channel in channels:
        plan = build_channel_playback_plan(channel.id)
        segments = Segment.query.filter_by(channel_id=channel.id).order_by(Segment.scheduled_at_utc.asc()).all()
        loop_candidates = plan.get("playlist", [])
        current = plan.get("current_segment")
        offset = plan.get("playback_offset", 0)
        total_loop_seconds = plan.get("loop_total_seconds", 0)
        queue_remaining = sum(1 for seg in segments if seg.status in ("queued", "ready"))
        current_duration = int(current.duration_seconds or 90) if current else 0
        current_remaining = max(0, current_duration - int(offset)) if current else 0

        channel_board.append(
            {
                "channel": channel,
                "total_count": len(segments),
                "queue_remaining": queue_remaining,
                "current_segment": current,
                "current_offset": offset,
                "current_remaining": current_remaining,
                "loop_total_seconds": total_loop_seconds,
                "breaking_active": bool(plan.get("breaking_active")),
                "breaking_segment_ids": plan.get("breaking_segment_ids", set()),
                "recent": sorted(
                    segments,
                    key=lambda seg: abs((_as_utc_aware(seg.scheduled_at_utc) - now).total_seconds()),
                )[:5],
            }
        )

    return render_template(
        "admin/content.html",
        channel_board=channel_board,
        breaking_events=list_recent_breaking_events(limit=40),
    )


@bp.route("/stage-1")
@auth_required
@admin_required
def stage_one():
    staged = Article.query.filter_by(status="staged").order_by(Article.created_at.desc()).all()
    rejected = Article.query.filter_by(status="rejected").order_by(Article.created_at.desc()).all()
    channel_options = Channel.query.order_by(Channel.name.asc()).all()
    source_feeds = SourceFeed.query.filter_by(active=True).order_by(SourceFeed.name.asc()).all()

    grouped_staged = []
    sorted_staged = sorted(staged, key=lambda article: ((article.source_name or "").lower(), article.created_at), reverse=False)
    for source_name, grouped_articles in groupby(sorted_staged, key=lambda article: article.source_name or "Unknown Source"):
        grouped_articles = list(grouped_articles)
        grouped_staged.append(
            {
                "source_name": source_name,
                "source_value": grouped_articles[0].source_name or "",
                "articles": grouped_articles,
            }
        )

    grouped_rejected = []
    sorted_rejected = sorted(rejected, key=lambda article: ((article.source_name or "").lower(), article.created_at), reverse=False)
    for source_name, grouped_articles in groupby(sorted_rejected, key=lambda article: article.source_name or "Unknown Source"):
        grouped_articles = list(grouped_articles)
        grouped_rejected.append(
            {
                "source_name": source_name,
                "source_value": grouped_articles[0].source_name or "",
                "articles": grouped_articles,
            }
        )

    return render_template(
        "admin/stage_one.html",
        staged=staged,
        grouped_staged=grouped_staged,
        grouped_rejected=grouped_rejected,
        channel_options=channel_options,
        source_feeds=source_feeds,
    )


@bp.route("/stage-1/find", methods=["POST"])
@auth_required
@admin_required
def stage_one_find():
    selected_feed_ids = request.form.getlist("source_feed_ids", type=int)
    restage_existing = bool(request.form.get("restage_existing"))
    if not selected_feed_ids:
        flash("Select at least one source before finding feed articles.", "error")
        return redirect(url_for("admin.stage_one"))

    created, created_by_source, restaged, restaged_by_source, duplicates_skipped = ingest_articles(
        limit_per_feed=6,
        source_feed_ids=selected_feed_ids,
        restage_existing=restage_existing,
    )
    if created_by_source or restaged_by_source:
        parts = []
        if created_by_source:
            created_breakdown = ", ".join(f"{source}: {count}" for source, count in created_by_source.items())
            parts.append(f"new {created} ({created_breakdown})")
        if restaged_by_source:
            restaged_breakdown = ", ".join(f"{source}: {count}" for source, count in restaged_by_source.items())
            parts.append(f"restaged {restaged} ({restaged_breakdown})")
        flash(f"Find complete. {'; '.join(parts)}.", "success")
    else:
        if duplicates_skipped:
            flash(
                "Find complete. No new Stage 1 items found. Matching URLs already exist in DB. "
                "Enable 'Re-stage existing matches' to bring them back to Stage 1.",
                "success",
            )
        else:
            flash("Find complete. No new Stage 1 items found from selected sources.", "success")
    return redirect(url_for("admin.stage_one"))


@bp.route("/stage-2")
@auth_required
@admin_required
def stage_two():
    drafting = Article.query.filter_by(status="drafting").order_by(Article.created_at.desc()).all()
    return render_template("admin/stage_two.html", drafting=drafting)


@bp.route("/stage-3")
@auth_required
@admin_required
def stage_three():
    channel_board = []
    now = _as_utc_aware(now_utc())
    channels = Channel.query.order_by(Channel.name.asc()).all()

    for channel in channels:
        plan = build_channel_playback_plan(channel.id)
        segments = Segment.query.filter_by(channel_id=channel.id).order_by(Segment.scheduled_at_utc.asc()).all()
        loop_candidates = plan.get("playlist", [])
        current = plan.get("current_segment")
        offset = plan.get("playback_offset", 0)
        total_loop_seconds = plan.get("loop_total_seconds", 0)
        queue_remaining = sum(1 for seg in segments if seg.status in ("queued", "ready"))
        current_duration = int(current.duration_seconds or 90) if current else 0
        current_remaining = max(0, current_duration - int(offset)) if current else 0

        channel_board.append(
            {
                "channel": channel,
                "total_count": len(segments),
                "queue_remaining": queue_remaining,
                "current_segment": current,
                "current_offset": offset,
                "current_remaining": current_remaining,
                "loop_total_seconds": total_loop_seconds,
                "breaking_active": bool(plan.get("breaking_active")),
                "breaking_segment_ids": plan.get("breaking_segment_ids", set()),
                "recent": sorted(
                    segments,
                    key=lambda seg: abs((_as_utc_aware(seg.scheduled_at_utc) - now).total_seconds()),
                )[:5],
            }
        )

    return render_template(
        "admin/stage_three.html",
        channel_board=channel_board,
        breaking_events=list_recent_breaking_events(limit=40),
    )


@bp.route("/automated")
@auth_required
@admin_required
def automated():
    channels = Channel.query.order_by(Channel.name.asc()).all()
    allowed_feed_ids = set(eligible_automated_feed_ids())
    eligible_feeds = list_eligible_automated_feeds()
    allocations = (
        AutomatedSourceAllocation.query.filter(AutomatedSourceAllocation.source_feed_id.in_(allowed_feed_ids))
        .order_by(AutomatedSourceAllocation.created_at.asc())
        .all()
    )

    channel_sources = {channel.id: [] for channel in channels}
    source_to_channel = {}

    for allocation in allocations:
        source_feed = allocation.source_feed
        if source_feed and source_feed.id in allowed_feed_ids:
            source_to_channel[source_feed.id] = allocation.channel_id
            channel_sources.setdefault(allocation.channel_id, []).append(
                {
                    "id": source_feed.id,
                    "name": source_feed.name,
                    "source_key": source_key_from_name(source_feed.name),
                }
            )

    unassigned = []
    for feed in eligible_feeds:
        if feed.id not in source_to_channel:
            unassigned.append(
                {
                    "id": feed.id,
                    "name": feed.name,
                    "source_key": source_key_from_name(feed.name),
                }
            )

    last_run_utc = get_setting("automated_last_run_utc", "")
    last_run_summary = get_setting("automated_last_run_summary", "")
    recent_logs = list_recent_automation_logs(limit=15)

    latest_log = None
    latest_failures = []
    if recent_logs:
        latest_log = read_automation_run_log(recent_logs[0]["run_id"])
        if latest_log:
            latest_failures = latest_log.get("failures", [])

    automated_feed_fetch_limit = get_automated_feed_fetch_limit()

    return render_template(
        "admin/automated.html",
        channels=channels,
        channel_sources=channel_sources,
        unassigned_sources=unassigned,
        last_run_utc=last_run_utc,
        last_run_summary=last_run_summary,
        recent_logs=recent_logs,
        latest_log=latest_log,
        latest_failures=latest_failures,
        automated_feed_fetch_limit=automated_feed_fetch_limit,
        allowed_automated_source_keys=list_allowed_automated_source_keys(),
    )


@bp.route("/automated/assign", methods=["POST"])
@auth_required
@admin_required
def automated_assign_source():
    channel_id = request.form.get("channel_id", type=int)
    source_feed_id = request.form.get("source_feed_id", type=int)

    if not channel_id or not source_feed_id:
        flash("Channel and source are required.", "error")
        return redirect(url_for("admin.automated"))

    channel = db.session.get(Channel, channel_id)
    source_feed = db.session.get(SourceFeed, source_feed_id)
    allowed_feed_ids = set(eligible_automated_feed_ids())

    if not channel or not source_feed or source_feed.id not in allowed_feed_ids:
        flash("Invalid channel/source selection.", "error")
        return redirect(url_for("admin.automated"))

    existing = AutomatedSourceAllocation.query.filter_by(source_feed_id=source_feed.id).first()
    if existing:
        existing.channel_id = channel.id
    else:
        db.session.add(AutomatedSourceAllocation(channel_id=channel.id, source_feed_id=source_feed.id))

    db.session.commit()
    flash(f"Mapped {source_feed.name} to {channel.name}.", "success")
    return redirect(url_for("admin.automated"))


@bp.route("/automated/unassign", methods=["POST"])
@auth_required
@admin_required
def automated_unassign_source():
    source_feed_id = request.form.get("source_feed_id", type=int)
    if not source_feed_id:
        flash("Source selection is required.", "error")
        return redirect(url_for("admin.automated"))

    allocation = AutomatedSourceAllocation.query.filter_by(source_feed_id=source_feed_id).first()
    if not allocation:
        flash("Source is already unassigned.", "error")
        return redirect(url_for("admin.automated"))

    source_name = allocation.source_feed.name if allocation.source_feed else "Source"
    db.session.delete(allocation)
    db.session.commit()
    flash(f"Unassigned {source_name} from automated mapping.", "success")
    return redirect(url_for("admin.automated"))


@bp.route("/automated/run-now", methods=["POST"])
@auth_required
@admin_required
def automated_run_now():
    skip_timestamp_gate = bool(request.form.get("skip_timestamp_gate"))
    result = run_automated_ingestion(skip_timestamp_gate=skip_timestamp_gate)
    fetch_limit = result.get("feed_fetch_limit", get_automated_feed_fetch_limit())
    fetch_limit_label = "full feed" if fetch_limit == 0 else f"top {fetch_limit} item(s) per feed"
    category = "error" if result.get("fatal_error") else "success"
    flash(
        "Automated run complete. "
        f"Fetch limit: {fetch_limit_label}. "
        f"Run ID: {result.get('run_id', 'n/a')}. "
        f"Queued new: {result['new_articles']}, timestamp-skipped: {result['timestamp_skipped']}, duplicates skipped: {result['duplicates_skipped']}, "
        f"full-article fetch failures: {result['fetch_failures']}, breaking updates: {result.get('breaking_updates', 0)}. "
        f"Log: {result.get('log_path', 'not written')}",
        category,
    )
    return redirect(url_for("admin.automated"))


@bp.route("/automated/settings", methods=["POST"])
@auth_required
@admin_required
def automated_update_settings():
    raw_fetch_limit = request.form.get("feed_fetch_limit", "").strip()
    if not raw_fetch_limit:
        flash("Feed fetch limit is required.", "error")
        return redirect(url_for("admin.automated"))

    try:
        parsed = int(raw_fetch_limit)
    except ValueError:
        flash("Feed fetch limit must be a whole number.", "error")
        return redirect(url_for("admin.automated"))

    if parsed < 0:
        flash("Feed fetch limit cannot be negative.", "error")
        return redirect(url_for("admin.automated"))

    setting = upsert_setting(
        AUTOMATED_FEED_FETCH_LIMIT_SETTING_KEY,
        str(parse_automated_feed_fetch_limit(parsed)),
        encrypted=False,
    )
    db.session.add(setting)
    db.session.commit()

    if parsed == 0:
        flash("Hourly automation will now scan the full feed for each mapped source.", "success")
    else:
        flash(f"Hourly automation will now scan the top {parsed} item(s) per mapped feed.", "success")
    return redirect(url_for("admin.automated"))


@bp.route("/automated/log/<run_id>")
@auth_required
@admin_required
def automated_log_detail(run_id):
    payload = read_automation_run_log(run_id)
    if not payload:
        flash("Automation log not found.", "error")
        return redirect(url_for("admin.automated"))

    failures = payload.get("failures", [])
    show_retryable_only = request.args.get("retryable") == "1"
    if show_retryable_only:
        failures = [failure for failure in failures if failure.get("reason") in RETRYABLE_FAILURE_REASONS]

    return render_template(
        "admin/automated_log.html",
        log_payload=payload,
        failures=failures,
        retryable_reasons=sorted(RETRYABLE_FAILURE_REASONS),
        show_retryable_only=show_retryable_only,
    )


@bp.route("/automated/retry-failures", methods=["POST"])
@auth_required
@admin_required
def automated_retry_failures():
    run_id = request.form.get("run_id", "").strip()
    selected_indexes = request.form.getlist("failure_indexes", type=int)
    retry_all = bool(request.form.get("retry_all"))
    next_url = request.form.get("next", "").strip()
    indexes = None if retry_all else selected_indexes

    result = retry_failed_automated_entries(run_id, indexes)
    category = "success" if not result.get("errors") else "error"
    message = (
        f"Retry complete for {run_id}. Retried: {result['retried']}, queued: {result['queued']}, "
        f"still failed: {result['still_failed']}."
    )
    if result.get("errors"):
        message = f"{message} Errors: {' | '.join(result['errors'])}"

    flash(message, category)
    if next_url:
        return redirect(next_url)
    return redirect(url_for("admin.automated"))


@bp.route("/article/manual", methods=["POST"])
@auth_required
@admin_required
def manual_article():
    title = request.form.get("title", "").strip()
    article_text = request.form.get("article_text", "").strip()
    channel_id = request.form.get("channel_id", type=int)
    source_name = request.form.get("source_name", "Manual Submission").strip() or "Manual Submission"
    source_url = request.form.get("source_url", "").strip() or "https://manual.dev/article"

    if not title or not article_text or not channel_id:
        flash("Title, channel, and article text are required.", "error")
        return redirect(url_for("admin.dashboard"))

    channel = db.session.get(Channel, channel_id)
    if not channel:
        flash("Invalid channel selected.", "error")
        return redirect(url_for("admin.dashboard"))

    article = Article(
        channel_id=channel.id,
        source_name=source_name,
        source_url=source_url,
        title=title,
        summary=article_text[:300],
        raw_excerpt=article_text[:2000],
        source_full_article=article_text,
        internal_content=article_text,
        status="staged",
    )
    db.session.add(article)
    db.session.commit()
    flash("Manual article added to staging queue.", "success")
    return redirect(url_for("admin.stage_one"))


@bp.route("/article/<int:article_id>/to-stage-2", methods=["POST"])
@auth_required
@admin_required
def move_to_stage_two(article_id):
    article = db.get_or_404(Article, article_id)
    if article.status != "staged":
        flash("Only staged articles can move to Stage 2.", "error")
        return redirect(url_for("admin.stage_one"))

    selected_channel_id = request.form.get("channel_id", type=int)
    if selected_channel_id:
        channel = db.session.get(Channel, selected_channel_id)
        if not channel:
            flash("Invalid channel selected.", "error")
            return redirect(url_for("admin.stage_one"))
        article.channel_id = channel.id

    article.status = "drafting"
    # Pre-fill source fields so the admin doesn't have to manually copy them
    if not article.short_headline:
        article.short_headline = article.title[:160]
    if not article.internal_content:
        article.internal_content = strip_html(article.source_full_article or article.raw_excerpt or "")
    db.session.commit()
    flash("Article moved to Stage 2 for generation and audio prep.", "success")
    return redirect(url_for("admin.stage_two"))


@bp.route("/article/<int:article_id>/update", methods=["POST"])
@auth_required
@admin_required
def update_article(article_id):
    article = db.get_or_404(Article, article_id)
    article.short_headline = request.form.get("short_headline", "").strip()
    article.image_url = request.form.get("image_url", "").strip() or None
    article.source_full_article = request.form.get("source_full_article", "").strip()
    article.bullet_summary = request.form.get("bullet_summary", "").strip()
    article.narration_script = request.form.get("narration_script", "").strip()
    article.tags = request.form.get("tags", "").strip()
    article.internal_content = request.form.get("internal_content", "").strip()
    db.session.commit()
    flash("Article draft updated.", "success")
    return redirect(url_for("admin.stage_two"))


@bp.route("/article/<int:article_id>/autofill", methods=["POST"])
@auth_required
@admin_required
def autofill_article(article_id):
    article = db.get_or_404(Article, article_id)
    api_key = get_setting("openrouter_api_key", default="")
    source_text = strip_html(article.source_full_article or article.raw_excerpt or "")
    bundle = generate_editorial_bundle(article.title, source_text, article.source_url, api_key)
    article.bullet_summary = bundle["bullet_summary"]
    article.narration_script = bundle["narration_script"]
    article.tags = bundle["tags"]
    # short_headline and internal_content are pre-filled from source; do not overwrite with LLM output
    db.session.commit()
    flash("Editorial bundle generated.", "success")
    return redirect(url_for("admin.stage_two"))


@bp.route("/article/<int:article_id>/preview-audio", methods=["POST"])
@auth_required
@admin_required
def preview_audio(article_id):
    article = db.get_or_404(Article, article_id)
    script = article.narration_script or article.short_headline or article.title
    article.summary = "Browser TTS preview enabled for this script in listener player."
    script_len = len(script or "")
    est_duration = max(20, min(300, script_len // 12 if script_len else 90))
    existing_segment = Segment.query.filter_by(article_id=article.id).first()
    if existing_segment and not existing_segment.duration_seconds:
        existing_segment.duration_seconds = est_duration
    db.session.commit()
    flash("Browser TTS preview prepared (no server audio file).", "success")
    return redirect(url_for("admin.stage_two"))


@bp.route("/article/<int:article_id>/approve", methods=["POST"])
@auth_required
@admin_required
def approve_article(article_id):
    article = db.get_or_404(Article, article_id)
    channel = db.session.get(Channel, article.channel_id)

    if article.status not in ("drafting", "approved"):
        flash("Article must be in Stage 2 before queueing.", "error")
        return redirect(url_for("admin.stage_two"))

    existing = Segment.query.filter_by(article_id=article.id).first()
    if existing:
        flash("Article is already queued.", "error")
        return redirect(url_for("admin.stage_three"))

    article.status = "approved"
    next_time = _next_queue_time(channel.id)

    segment = Segment(
        article_id=article.id,
        channel_id=channel.id,
        scheduled_at_utc=next_time,
        status="queued",
        transcript=article.narration_script,
        duration_seconds=max(20, min(300, len((article.narration_script or article.title or "")) // 12 or 90)),
    )
    db.session.add(segment)
    db.session.commit()
    register_breaking_injection(channel.id, [segment.id], source="manual_approve")

    flash("Article queued to Stage 3.", "success")
    return redirect(url_for("admin.stage_three"))


@bp.route("/article/<int:article_id>/approve-no-ai", methods=["POST"])
@auth_required
@admin_required
def approve_article_no_ai(article_id):
    article = db.get_or_404(Article, article_id)
    channel = db.session.get(Channel, article.channel_id)

    if article.status not in ("drafting", "approved"):
        flash("Article must be in Stage 2 before queueing.", "error")
        return redirect(url_for("admin.stage_two"))

    existing = Segment.query.filter_by(article_id=article.id).first()
    if existing:
        flash("Article is already queued.", "error")
        return redirect(url_for("admin.stage_three"))

    article.status = "approved"
    article.no_ai_mode = True

    # Use internal_content as the playback transcript; strip leading/trailing whitespace
    transcript_text = (article.internal_content or article.raw_excerpt or article.title or "").strip()

    next_time = _next_queue_time(channel.id)

    segment = Segment(
        article_id=article.id,
        channel_id=channel.id,
        scheduled_at_utc=next_time,
        status="queued",
        transcript=transcript_text,
        duration_seconds=max(20, min(300, len(transcript_text) // 12 or 90)),
    )
    db.session.add(segment)
    db.session.commit()
    register_breaking_injection(channel.id, [segment.id], source="manual_approve_no_ai")

    flash("Article queued to Stage 3 (no AI mode).", "success")
    return redirect(url_for("admin.stage_three"))


@bp.route("/article/<int:article_id>/reject", methods=["POST"])
@auth_required
@admin_required
def reject_article(article_id):
    article = db.get_or_404(Article, article_id)
    article.status = "rejected"
    db.session.commit()
    flash("Article rejected.", "success")
    return redirect(url_for("admin.stage_one"))


@bp.route("/article/<int:article_id>/delete", methods=["POST"])
@auth_required
@admin_required
def delete_article(article_id):
    article = db.get_or_404(Article, article_id)

    # Remove any queued/played segment first if it exists.
    if article.segment:
        db.session.delete(article.segment)

    db.session.delete(article)
    db.session.commit()
    flash("Article deleted permanently.", "success")
    return redirect(url_for("admin.stage_one"))


@bp.route("/articles/source/reject", methods=["POST"])
@auth_required
@admin_required
def reject_source_group():
    source_name = request.form.get("source_name", "").strip()
    query = Article.query.filter_by(status="staged")
    if source_name:
        query = query.filter(Article.source_name == source_name)
    else:
        query = query.filter(or_(Article.source_name.is_(None), Article.source_name == ""))

    affected = query.update({Article.status: "rejected"}, synchronize_session=False)
    db.session.commit()
    flash(f"Rejected {affected} staged item(s) for source group.", "success")
    return redirect(url_for("admin.stage_one"))


@bp.route("/articles/source/delete", methods=["POST"])
@auth_required
@admin_required
def delete_source_group():
    source_name = request.form.get("source_name", "").strip()
    query = Article.query.filter_by(status="staged")
    if source_name:
        query = query.filter(Article.source_name == source_name)
    else:
        query = query.filter(or_(Article.source_name.is_(None), Article.source_name == ""))

    staged_articles = query.all()
    for article in staged_articles:
        if article.segment:
            db.session.delete(article.segment)
        db.session.delete(article)

    db.session.commit()
    flash(f"Deleted {len(staged_articles)} staged item(s) for source group.", "success")
    return redirect(url_for("admin.stage_one"))


@bp.route("/schedule")
@auth_required
@admin_required
def schedule():
    return redirect(url_for("admin.stage_three"))


@bp.route("/settings", methods=["GET", "POST"])
@auth_required
@admin_required
def settings():
    if request.method == "POST":
        openrouter_api_key = request.form.get("openrouter_api_key", "").strip()
        ticker_refresh_seconds_raw = request.form.get("ticker_refresh_seconds", "").strip()

        if openrouter_api_key:
            setting = upsert_setting("openrouter_api_key", openrouter_api_key, encrypted=True)
            db.session.add(setting)
        if ticker_refresh_seconds_raw:
            try:
                ticker_refresh_seconds = int(ticker_refresh_seconds_raw)
            except ValueError:
                flash("Ticker refresh time must be a whole number of seconds.", "error")
                return redirect(url_for("admin.settings"))

            ticker_refresh_seconds = max(15, min(600, ticker_refresh_seconds))
            setting = upsert_setting(TICKER_REFRESH_SECONDS_SETTING_KEY, str(ticker_refresh_seconds), encrypted=False)
            db.session.add(setting)

        db.session.commit()

        if openrouter_api_key:
            flash("API key updated.", "success")
        if ticker_refresh_seconds_raw:
            flash("Ticker refresh time updated.", "success")
        return redirect(url_for("admin.settings"))

    masked_key = "********" if get_setting("openrouter_api_key", "") else ""
    ticker_refresh_seconds = get_setting_int(TICKER_REFRESH_SECONDS_SETTING_KEY, DEFAULT_TICKER_REFRESH_SECONDS)
    return render_template(
        "admin/settings.html",
        masked_key=masked_key,
        ticker_refresh_seconds=ticker_refresh_seconds,
        ticker_refresh_seconds_min=15,
        ticker_refresh_seconds_max=600,
    )


@bp.route("/settings/reset-editorial-data", methods=["POST"])
@auth_required
@admin_required
def reset_editorial_data():
    saved_story_count = SavedStory.query.delete(synchronize_session=False)
    segment_count = Segment.query.delete(synchronize_session=False)
    article_count = Article.query.delete(synchronize_session=False)
    db.session.commit()

    flash(
        "Cleared "
        f"{article_count} article(s), {segment_count} queued segment(s), and {saved_story_count} saved item(s). "
        "User login data was preserved.",
        "success",
    )
    return redirect(url_for("admin.settings"))


@bp.route("/me/timezone", methods=["POST"])
@auth_required
@admin_required
def admin_timezone():
    app_user = get_current_user()
    profile = UserProfile.query.filter_by(user_id=str(app_user.user_id)).first()
    if not profile:
        flash("Could not update timezone for the current profile.", "error")
        return redirect(url_for("admin.settings"))
    profile.timezone_name = request.form.get("timezone_name", "Asia/Kolkata")
    db.session.commit()
    return redirect(url_for("admin.settings"))
