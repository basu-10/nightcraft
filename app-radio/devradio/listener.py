from datetime import timezone
from flask import Blueprint, abort, current_app, flash, jsonify, make_response, redirect, render_template, request, url_for

from .auth.current_user import get_current_user
from .extensions import db
from .guards import auth_required
from .models import Article, Channel, SavedStory, Segment, UserProfile
from .services.playback import build_channel_playback_plan, get_breaking_segment_ids
from .services.settings import get_setting_int
from .utils import app_timezone, format_article_body_html, now_app_timezone, strip_html

bp = Blueprint("listener", __name__)

TICKER_REFRESH_SECONDS_SETTING_KEY = "ticker_refresh_seconds"
DEFAULT_TICKER_REFRESH_SECONDS = 90


def _current_user_profile_id():
    app_user = get_current_user()
    if not app_user.is_authenticated:
        return None
    profile = UserProfile.query.filter_by(user_id=str(app_user.user_id)).first()
    if not profile and current_app.config.get("AUTH_MODE", "local").lower() == "local":
        local_profile = UserProfile(
            user_id=str(app_user.user_id),
            username=app_user.username,
            is_admin=app_user.is_admin,
            timezone_name=app_user.timezone_name,
        )
        db.session.add(local_profile)
        try:
            db.session.commit()
            profile = local_profile
        except Exception:
            db.session.rollback()
            profile = UserProfile.query.filter_by(user_id=str(app_user.user_id)).first()
    if not profile:
        return None
    return profile.id


def _as_utc_aware(dt_value):
    if dt_value is None:
        return None
    if dt_value.tzinfo is None:
        return dt_value.replace(tzinfo=timezone.utc)
    return dt_value.astimezone(timezone.utc)


def _resolve_post_redirect(default_url):
    next_target = request.form.get("next", "").strip()
    if next_target.startswith("/"):
        return next_target

    referrer = request.referrer or ""
    if referrer.startswith(request.host_url):
        return referrer

    return default_url


def _visible_channel_segments(channel_id):
    ist_tz = app_timezone()
    now_utc = _as_utc_aware(now_app_timezone())
    segments = Segment.query.filter_by(channel_id=channel_id).order_by(Segment.scheduled_at_utc.desc()).all()

    visible = []
    for seg in segments:
        scheduled_utc = _as_utc_aware(seg.scheduled_at_utc)
        local_time = scheduled_utc.astimezone(ist_tz)
        if seg.status == "played" or scheduled_utc <= now_utc:
            visible.append((seg, local_time))

    return visible


def _group_segments_by_date(segments):
    """Group (seg, local_time) tuples into non-overlapping recency buckets.

    Buckets are evaluated in order so each segment lands in exactly one group:
    Today, Yesterday, This Week, This Month, This Year, Older.
    """
    today = _as_utc_aware(now_app_timezone()).astimezone(app_timezone()).date()

    buckets = [
        (0, "Today", []),
        (1, "Yesterday", []),
        (7, "This Week", []),
        (30, "This Month", []),
        (365, "This Year", []),
        (10 ** 9, "Older", []),
    ]

    for seg, local_time in segments:
        day_offset = (today - local_time.date()).days
        for threshold, label, bucket in buckets:
            if day_offset <= threshold:
                bucket.append((seg, local_time))
                break

    return [(label, bucket) for _, label, bucket in buckets if bucket]


def _ticker_headlines_payload(channel_id, limit=25):
    visible_segments = _visible_channel_segments(channel_id)
    rows = []
    max_updated = None

    for seg, _local_time in visible_segments[:limit]:
        headline = seg.article.short_headline or seg.article.title
        if not headline:
            continue
        rows.append(
            {
                "segment_id": seg.id,
                "article_id": seg.article.id,
                "headline": headline,
            }
        )

        for ts_candidate in (seg.updated_at, seg.article.updated_at):
            candidate = _as_utc_aware(ts_candidate)
            if candidate and (max_updated is None or candidate > max_updated):
                max_updated = candidate

    latest_epoch = int(max_updated.timestamp()) if max_updated else 0
    latest_segment = rows[0]["segment_id"] if rows else 0
    revision = f"{channel_id}-{len(rows)}-{latest_segment}-{latest_epoch}"

    return rows, revision


@bp.route("/")
def home():
    channels = Channel.query.order_by(Channel.name.asc()).all()
    live_segments = {}
    for channel in channels:
        plan = build_channel_playback_plan(channel.id)
        live_segments[channel.slug] = plan.get("current_segment")
    return render_template("listener/home.html", channels=channels, live_segments=live_segments)


@bp.route("/player/<channel_slug>")
def player(channel_slug):
    channel = Channel.query.filter_by(slug=channel_slug).first_or_404()
    plan = build_channel_playback_plan(channel.id)
    playlist = plan.get("playlist", [])
    current_segment = plan.get("current_segment")
    playback_offset = plan.get("playback_offset", 0)
    breaking_active = bool(plan.get("breaking_active"))
    breaking_segment_ids = plan.get("breaking_segment_ids", set())
    tts_text = ""
    if current_segment:
        tts_text = (
            current_segment.transcript
            or current_segment.article.narration_script
            or current_segment.article.short_headline
            or current_segment.article.title
        )

    if breaking_active and current_segment and playlist:
        ordered_ids = [seg.id for seg in playlist]
        injected_indices = [idx for idx, seg_id in enumerate(ordered_ids) if seg_id in breaking_segment_ids]
        first_injected_id = ordered_ids[injected_indices[0]] if injected_indices else None
        resume_segment_id = None
        if injected_indices:
            last_injected_index = injected_indices[-1]
            for seg_id in ordered_ids[last_injected_index + 1 :]:
                if seg_id not in breaking_segment_ids:
                    resume_segment_id = seg_id
                    break

        if first_injected_id and current_segment.id == first_injected_id and plan.get("breaking_announcement_intro"):
            tts_text = f"{plan.get('breaking_announcement_intro')} {tts_text}".strip()
        elif resume_segment_id and current_segment.id == resume_segment_id and plan.get("breaking_announcement_resume"):
            tts_text = f"{plan.get('breaking_announcement_resume')} {tts_text}".strip()

    visible_segments = _visible_channel_segments(channel.id)

    previous_stories = []
    next_stories = []
    if playlist and current_segment:
        current_index = next((idx for idx, seg in enumerate(playlist) if seg.id == current_segment.id), 0)
        total = len(playlist)
        for i in range(1, min(6, total)):
            previous_stories.append(playlist[(current_index - i) % total])
            next_stories.append(playlist[(current_index + i) % total])

    # Fallback for sparse playlists: fetch recently played segments from DB.
    if not previous_stories:
        recent_played = (
            Segment.query.filter_by(channel_id=channel.id, status="played")
            .filter(Segment.id != (current_segment.id if current_segment else -1))
            .order_by(Segment.scheduled_at_utc.desc())
            .limit(5)
            .all()
        )
        previous_stories = recent_played

    # Keep sidebar populated even when there are no published rows yet.
    sidebar_segments = visible_segments
    if not sidebar_segments:
        sidebar_segments = [(seg, None) for seg in previous_stories]

    bookmark_rows = []
    bookmarked_article_ids = set()
    app_user = get_current_user()
    if app_user.is_authenticated and not app_user.is_admin:
        profile_id = _current_user_profile_id()
        if profile_id is not None:
            bookmark_rows = (
                SavedStory.query.filter_by(user_id=profile_id)
                .join(Article)
                .filter(Article.channel_id == channel.id)
                .order_by(SavedStory.created_at.desc())
                .all()
            )
            bookmarked_article_ids = {row.article_id for row in bookmark_rows}

    current_is_bookmarked = (
        bool(current_segment)
        and bool(current_segment.article)
        and current_segment.article.id in bookmarked_article_ids
    )

    ticker_refresh_seconds = get_setting_int(TICKER_REFRESH_SECONDS_SETTING_KEY, DEFAULT_TICKER_REFRESH_SECONDS)
    focus_article_html = ""
    if current_segment and current_segment.article:
        focus_article_html = format_article_body_html(
            current_segment.article.source_full_article,
            current_segment.article.raw_excerpt,
            current_segment.article.summary,
            fallback=channel.description,
        )

    return render_template(
        "listener/player.html",
        channel=channel,
        playlist=playlist,
        current_segment=current_segment,
        sidebar_segments=sidebar_segments,
        previous_stories=previous_stories,
        next_stories=next_stories,
        bookmark_rows=bookmark_rows,
        current_is_bookmarked=current_is_bookmarked,
        breaking_active=breaking_active,
        breaking_segment_ids=breaking_segment_ids,
        breaking_announcement_intro=plan.get("breaking_announcement_intro", ""),
        breaking_announcement_resume=plan.get("breaking_announcement_resume", ""),
        playback_offset=playback_offset,
        tts_text=tts_text,
        ticker_refresh_seconds=ticker_refresh_seconds,
        focus_article_html=focus_article_html,
    )


@bp.route("/channels/<channel_slug>")
def channel_page(channel_slug):
    channel = Channel.query.filter_by(slug=channel_slug).first_or_404()
    other_channels = Channel.query.filter(Channel.id != channel.id).order_by(Channel.name.asc()).all()
    breaking_segment_ids = get_breaking_segment_ids(channel.id)

    return render_template(
        "listener/channel_page.html",
        channel=channel,
        groups=_group_segments_by_date(_visible_channel_segments(channel.id)),
        other_channels=other_channels,
        breaking_segment_ids=breaking_segment_ids,
    )


@bp.route("/channels/<channel_slug>/ticker-headlines")
def channel_ticker_headlines(channel_slug):
    channel = Channel.query.filter_by(slug=channel_slug).first_or_404()
    rows, revision = _ticker_headlines_payload(channel.id)

    if request.if_none_match and request.if_none_match.contains(revision):
        response = make_response("", 304)
        response.set_etag(revision)
        response.headers["Cache-Control"] = "private, max-age=0, must-revalidate"
        return response

    response = jsonify(
        {
            "headlines": [row["headline"] for row in rows],
            "items": rows,
            "revision": revision,
        }
    )
    response.set_etag(revision)
    response.headers["Cache-Control"] = "private, max-age=0, must-revalidate"
    return response


@bp.route("/article/<int:article_id>")
def article_detail(article_id):
    article = db.get_or_404(Article, article_id)
    channel = article.channel
    other_channels = Channel.query.filter(Channel.id != channel.id).order_by(Channel.name.asc()).all()

    # Get all articles in the same channel, sorted by created_at DESC
    all_articles = Article.query.filter_by(channel_id=article.channel_id).order_by(Article.created_at.desc()).all()

    # Find current index
    current_idx = next((idx for idx, a in enumerate(all_articles) if a.id == article_id), None)

    # Get previous and next articles
    prev_article = all_articles[current_idx + 1] if current_idx is not None and current_idx + 1 < len(all_articles) else None
    next_article = all_articles[current_idx - 1] if current_idx is not None and current_idx > 0 else None

    is_bookmarked = False
    app_user = get_current_user()
    if app_user.is_authenticated and not app_user.is_admin:
        profile_id = _current_user_profile_id()
        if profile_id is not None:
            is_bookmarked = SavedStory.query.filter_by(user_id=profile_id, article_id=article.id).first() is not None

    article_body_html = format_article_body_html(
        article.source_full_article,
        article.raw_excerpt,
        article.summary,
    )

    return render_template(
        "listener/article_detail.html",
        article=article,
        channel=channel,
        other_channels=other_channels,
        prev_article=prev_article,
        next_article=next_article,
        is_bookmarked=is_bookmarked,
        article_body_html=article_body_html,
    )


@bp.route("/bookmark/<int:article_id>", methods=["POST"])
@auth_required
def toggle_bookmark(article_id):
    app_user = get_current_user()
    if app_user.is_admin:
        abort(403)

    profile_id = _current_user_profile_id()
    if profile_id is None:
        abort(403)

    article = db.get_or_404(Article, article_id)
    existing = SavedStory.query.filter_by(user_id=profile_id, article_id=article.id).first()
    if existing:
        db.session.delete(existing)
        flash("Bookmark removed.", "success")
    else:
        db.session.add(SavedStory(user_id=profile_id, article_id=article.id))
        flash("Bookmarked.", "success")

    db.session.commit()
    default_url = url_for("listener.article_detail", article_id=article.id)
    return redirect(_resolve_post_redirect(default_url))


@bp.route("/api/player/<channel_slug>/state")
def get_player_state(channel_slug):
    """
    Lightweight API endpoint for continuous player animation.
    Returns minimal state to detect segment changes without hammering the DB.
    Polls every 30-60s; between polls, client interpolates with elapsed time.
    """
    channel = Channel.query.filter_by(slug=channel_slug).first_or_404()
    plan = build_channel_playback_plan(channel.id)
    current_segment = plan.get("current_segment")
    playback_offset = plan.get("playback_offset", 0)

    if not current_segment:
        return jsonify({
            "segment_id": None,
            "segment_duration_seconds": 90,  # Default duration
            "segment_headline": "Waiting for content...",
            "segment_synopsis": "",
            "playback_offset": 0,
        }), 200

    # Use segment duration if available, otherwise use a default of 90 seconds
    # (this matches compute_loop_segment behavior)
    segment_duration = current_segment.duration_seconds or 90

    synopsis_html = format_article_body_html(
        current_segment.article.source_full_article,
        current_segment.article.raw_excerpt,
        current_segment.article.summary,
        fallback=channel.description,
    )
    synopsis = strip_html(synopsis_html)

    return jsonify({
        "segment_id": current_segment.id,
        "segment_duration_seconds": segment_duration,
        "segment_headline": current_segment.article.short_headline or current_segment.article.title,
        "segment_synopsis": synopsis,
        "segment_synopsis_html": synopsis_html,
        "playback_offset": playback_offset,
    }), 200


@bp.route("/save/<int:article_id>", methods=["POST"])
@auth_required
def save_story(article_id):
    app_user = get_current_user()
    if app_user.is_admin:
        abort(403)

    profile_id = _current_user_profile_id()
    if profile_id is None:
        abort(403)

    article = db.get_or_404(Article, article_id)
    exists = SavedStory.query.filter_by(user_id=profile_id, article_id=article.id).first()
    if not exists:
        db.session.add(SavedStory(user_id=profile_id, article_id=article.id))
        db.session.commit()
        flash("Story saved.", "success")

    default_url = url_for("listener.channel_page", channel_slug=article.channel.slug)
    return redirect(_resolve_post_redirect(default_url))


@bp.route("/share/<int:article_id>")
def share_story(article_id):
    article = db.get_or_404(Article, article_id)
    share_url = url_for("listener.article_detail", article_id=article.id, _external=True)
    return render_template("listener/share.html", article=article, share_url=share_url)


@bp.route("/bookmarks")
@auth_required
def bookmarks():
    app_user = get_current_user()
    if app_user.is_admin:
        abort(403)

    profile_id = _current_user_profile_id()
    if profile_id is None:
        abort(403)

    sort_by = request.args.get("sort", "newest")

    query = SavedStory.query.filter_by(user_id=profile_id).join(Article)

    if sort_by == "oldest":
        query = query.order_by(SavedStory.created_at.asc())
    elif sort_by == "title":
        query = query.order_by(Article.short_headline.asc(), Article.title.asc())
    else:
        query = query.order_by(SavedStory.created_at.desc())

    bookmark_rows = query.all()

    return render_template(
        "listener/bookmarks.html",
        bookmark_rows=bookmark_rows,
        sort_by=sort_by,
    )


@bp.route("/bookmarks/remove/<int:saved_id>", methods=["POST"])
@auth_required
def remove_bookmark(saved_id):
    app_user = get_current_user()
    if app_user.is_admin:
        abort(403)

    profile_id = _current_user_profile_id()
    if profile_id is None:
        abort(403)

    saved = db.get_or_404(SavedStory, saved_id)
    if saved.user_id != profile_id:
        abort(403)

    db.session.delete(saved)
    db.session.commit()
    flash("Bookmark removed.", "success")

    return_to = request.form.get("next", "").strip()
    if return_to.startswith("/"):
        return redirect(return_to)
    return redirect(url_for("listener.bookmarks"))


@bp.route("/settings", methods=["GET", "POST"])
@auth_required
def listener_settings():
    app_user = get_current_user()
    if app_user.is_admin:
        return redirect(url_for("admin.settings"))

    if request.method == "POST":
        timezone_name = request.form.get("timezone_name", "Asia/Kolkata")
        profile_id = _current_user_profile_id()
        if profile_id is None:
            abort(403)
        profile = db.session.get(UserProfile, profile_id)
        if not profile:
            abort(403)
        profile.timezone_name = timezone_name
        db.session.commit()
        flash("Timezone updated.", "success")
        return redirect(url_for("listener.listener_settings"))

    return render_template("listener/settings.html")
