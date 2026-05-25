from pathlib import Path
from uuid import uuid4

from flask import Blueprint, abort, current_app, flash, redirect, render_template, request, send_from_directory, url_for
from sqlalchemy import and_

from .auth.current_user import get_current_user
from .guards import auth_required
from .extensions import db
from .models import CurioItem, CurioList, CurioListItem, CurioNote, FeedEvent, Review, UserProfile
from .works import CATEGORY_METADATA_FIELDS, create_work, normalize_work_category, search_existing_works, uploaded_image_path

bp = Blueprint("main", __name__)


def _is_allowed_profile_url(raw_value):
    value = (raw_value or "").strip().lower()
    if not value:
        return True
    return value.startswith("http://") or value.startswith("https://")


def _tone_from_category(category):
    category_key = (category or "").strip().lower()
    mapping = {
        "book": "books",
        "books": "books",
        "song": "songs",
        "songs": "songs",
        "music": "songs",
        "film": "films",
        "films": "films",
        "movie": "films",
        "movies": "films",
        "art": "art",
        "playlist": "playlist",
        "mixed": "mixed",
    }
    return mapping.get(category_key, "mixed")


def _category_label(category):
    labels = {
        "book": "Books",
        "song": "Songs",
        "film": "Films",
        "art": "Arts",
    }
    return labels.get(normalize_work_category(category), (category or "").title())


def _item_metadata_rows(item):
    metadata_values = item.metadata_values
    category = item.normalized_category

    ordered_fields = {
        "book": [
            ("Author", "author"),
            ("Year", "year"),
            ("Pages", "pages"),
            ("Publisher", "publisher"),
            ("ISBN", "isbn"),
            ("Language", "language"),
        ],
        "film": [
            ("Director", "director"),
            ("Year", "year"),
            ("Runtime", "runtime_minutes"),
            ("Country", "country"),
            ("Language", "language"),
        ],
        "song": [
            ("Artist", "artist"),
            ("Album", "album"),
            ("Year", "year"),
            ("Duration", "duration_seconds"),
        ],
        "art": [
            ("Artist", "artist"),
            ("Year", "year"),
            ("Medium", "medium"),
            ("Movement", "movement"),
            ("Museum", "museum"),
        ],
    }

    rows = []
    for label, key in ordered_fields.get(category, []):
        value = metadata_values.get(key)
        if value in (None, ""):
            continue
        if key == "runtime_minutes":
            value = f"{value} min"
        elif key == "duration_seconds":
            minutes, seconds = divmod(value, 60)
            value = f"{minutes}m {seconds:02d}s"
        rows.append({"label": label, "value": value})
    return rows


def _review_categories_for_item(item):
    category = item.normalized_category
    compatible = {
        "book": ["book", "books"],
        "song": ["song", "songs", "music"],
        "film": ["film", "films", "movie", "movies"],
        "art": ["art", "arts", "artwork", "artworks"],
    }
    return compatible.get(category, [category])


def _supported_work_categories():
    return ["book", "film", "song", "art"]


def _blank_work_form_data():
    return {
        "category": "book",
        "title": "",
        "creator_display_name": "",
        "image_url": "",
        "description": "",
        "book_author": "",
        "book_year": "",
        "book_pages": "",
        "book_publisher": "",
        "book_isbn": "",
        "book_language": "",
        "film_director": "",
        "film_year": "",
        "film_runtime_minutes": "",
        "film_country": "",
        "film_language": "",
        "song_artist": "",
        "song_album": "",
        "song_year": "",
        "song_duration_seconds": "",
        "art_artist": "",
        "art_year": "",
        "art_medium": "",
        "art_movement": "",
        "art_museum": "",
    }


def _work_form_metadata(category, form_data):
    normalized = normalize_work_category(category)
    prefixes = {
        "book": "book",
        "film": "film",
        "song": "song",
        "art": "art",
    }
    prefix = prefixes[normalized]
    metadata = {}
    for field_name in CATEGORY_METADATA_FIELDS[normalized]:
        metadata[field_name] = form_data.get(f"{prefix}_{field_name}", "")
    return metadata


def _work_form_data_from_request():
    form_data = _blank_work_form_data()
    for key in form_data:
        form_data[key] = request.form.get(key, "").strip()
    form_data["category"] = normalize_work_category(form_data["category"] or "book")
    return form_data


def _work_submission_payload(form_data):
    category = normalize_work_category(form_data.get("category"))
    common = {
        "category": category,
        "title": form_data.get("title", "").strip(),
        "creator_display_name": form_data.get("creator_display_name", "").strip(),
        "image_url": form_data.get("image_url", "").strip(),
        "description": form_data.get("description", "").strip(),
        "source_type": "user",
        "source_id": f"user-{uuid4().hex}",
        "is_user_submitted": True,
        "metadata_confidence": None,
    }
    return common, _work_form_metadata(category, form_data)


def _find_duplicate_work(common):
    return CurioItem.query.filter_by(
        category=normalize_work_category(common.get("category")),
        title=common.get("title", ""),
        creator_display_name=common.get("creator_display_name", ""),
    ).first()


def _uploaded_works_root():
    return Path(current_app.instance_path) / current_app.config.get("UPLOADS_DIR", "uploads")


def _confidence_label(confidence):
    if confidence is None:
        return "Unknown"
    if confidence < 0.4:
        return "Low"
    if confidence < 0.75:
        return "Medium"
    return "High"


def _normalize_review_visibility(value):
    normalized = (value or "public").strip().lower()
    if normalized not in {"private", "followers", "public"}:
        return "public"
    return normalized


def _normalize_review_status(value):
    normalized = (value or "published").strip().lower()
    if normalized not in {"draft", "published"}:
        return "published"
    return normalized


def _normalize_list_visibility(value):
    normalized = (value or "public").strip().lower()
    if normalized not in {"private", "public"}:
        return "public"
    return normalized


def _normalize_note_visibility(value):
    normalized = (value or "public").strip().lower()
    if normalized not in {"private", "public"}:
        return "public"
    return normalized


def _normalize_note_status(value):
    normalized = (value or "published").strip().lower()
    if normalized not in {"draft", "published"}:
        return "published"
    return normalized


def _review_is_public(row):
    return row.status == "published" and row.visibility == "public"


def _review_is_owner_visible(row, app_user):
    return app_user.is_authenticated and row.profile.user_id == app_user.user_id


def _note_is_public(row):
    return row.status == "published" and row.visibility == "public"


def _review_payload(row, app_user=None, highlighted_review_id=None):
    app_user = app_user or get_current_user()
    work = row.work
    subject = row.subject
    category = row.category
    if work is not None:
        subject = work.title
        category = work.normalized_category

    return {
        "id": row.id,
        "subject": subject,
        "review_title": row.review_title,
        "category": category.upper(),
        "category_key": category,
        "body": row.body,
        "rating": row.rating,
        "created_at": row.created_at,
        "status": row.status,
        "visibility": row.visibility,
        "spoiler": row.spoiler,
        "tags": row.tags,
        "is_owner": _review_is_owner_visible(row, app_user),
        "is_highlighted": highlighted_review_id == row.id,
    }


def _review_rows_for_profile(profile_id, viewer_can_edit=False, include_drafts=False):
    query = Review.query.filter_by(profile_id=profile_id)
    if include_drafts:
        query = query.filter((Review.status == "draft") | (Review.visibility == "private"))
    elif viewer_can_edit:
        query = query.filter(Review.status == "published", Review.visibility != "private")
    else:
        query = query.filter_by(status="published", visibility="public")
    return query.order_by(Review.created_at.desc()).limit(12).all()


def _note_rows_for_profile(profile_id, viewer_can_edit=False, include_drafts=False):
    query = CurioNote.query.filter_by(profile_id=profile_id)
    if include_drafts:
        query = query.filter((CurioNote.status == "draft") | (CurioNote.visibility == "private"))
    elif viewer_can_edit:
        query = query.filter(CurioNote.status == "published", CurioNote.visibility != "private")
    else:
        query = query.filter_by(status="published", visibility="public")
    return query.order_by(CurioNote.created_at.desc()).limit(12).all()


def _list_rows_for_profile(profile_id, viewer_can_edit=False, include_drafts=False):
    query = CurioList.query.filter_by(profile_id=profile_id)
    if include_drafts:
        query = query.filter_by(visibility="private")
    elif not viewer_can_edit:
        query = query.filter_by(visibility="public")
    return query.order_by(CurioList.created_at.desc()).all()


def _collect_item_review_rows(item, app_user, highlighted_review_id=None):
    category_keys = _review_categories_for_item(item)
    rows = (
        Review.query.filter(
            (Review.work_id == item.id)
            | and_(Review.work_id.is_(None), Review.subject.ilike(item.title), Review.category.in_(category_keys))
        )
        .order_by(Review.created_at.desc())
        .all()
    )

    visible_rows = []
    seen_ids = set()
    for row in rows:
        if _review_is_public(row) or _review_is_owner_visible(row, app_user) or row.id == highlighted_review_id:
            if row.id not in seen_ids:
                visible_rows.append(row)
                seen_ids.add(row.id)
    return visible_rows


def _feed_event_for_review(review_id):
    return FeedEvent.query.filter_by(target_type="review", target_id=review_id).first()


def _sync_review_feed_event(review):
    existing = _feed_event_for_review(review.id)
    should_exist = review.status == "published" and review.visibility != "private"
    if should_exist and existing is None:
        db.session.add(FeedEvent(profile_id=review.profile_id, target_type="review", target_id=review.id))
    elif not should_exist and existing is not None:
        db.session.delete(existing)


def _blank_review_form_data(work):
    category = work.normalized_category if work is not None else "book"
    subject = work.title if work is not None else ""
    return {
        "work_id": work.id if work is not None else "",
        "subject": subject,
        "category": category,
        "rating": "",
        "review_title": "",
        "body": "",
        "spoiler": False,
        "tags": "",
        "visibility": "public",
        "status": "published",
    }


def _review_form_from_request(default_work=None):
    return {
        "work_id": request.form.get("work_id", str(default_work.id) if default_work is not None else "").strip(),
        "subject": request.form.get("subject", default_work.title if default_work is not None else "").strip(),
        "category": normalize_work_category(request.form.get("category", default_work.normalized_category if default_work is not None else "book")),
        "rating": request.form.get("rating", "").strip(),
        "review_title": request.form.get("review_title", "").strip(),
        "body": request.form.get("body", "").strip(),
        "spoiler": request.form.get("spoiler", "") == "on",
        "tags": request.form.get("tags", "").strip(),
        "visibility": request.form.get("visibility", "public").strip().lower() or "public",
        "status": request.form.get("status", "published").strip().lower() or "published",
    }


def _blank_book_entry_form(initial_title=""):
    return {
        "title": initial_title,
        "author": "",
        "year": "",
        "image_url": "",
        "isbn": "",
        "publisher": "",
        "pages": "",
        "language": "",
        "description": "",
        "genres": "",
    }


def _book_entry_form_from_request():
    form_data = _blank_book_entry_form()
    for key in form_data:
        form_data[key] = request.form.get(key, "").strip()
    return form_data


def _list_payloads(rows):
    payloads = []
    for row in rows:
        entries = []
        for index, entry in enumerate(row.items[:5]):
            entries.append(
                {
                    "id": entry.id,
                    "title": entry.title,
                    "creator_name": entry.creator_name,
                    "notes": entry.notes,
                    "can_move_up": index > 0,
                    "can_move_down": index < len(row.items[:5]) - 1,
                }
            )
        payloads.append(
            {
                "id": row.id,
                "title": row.title,
                "category": row.category.upper(),
                "description": row.description,
                "visibility": row.visibility,
                "items": row.item_count,
                "tone": _tone_from_category(row.category),
                "entries": entries,
            }
        )
    return payloads


def _review_payloads(rows):
    return [_review_payload(row) for row in rows]


def _note_payload(row):
    return {
        "id": row.id,
        "title": row.title,
        "body": row.body,
        "status": row.status,
        "visibility": row.visibility,
        "created_at": row.created_at,
    }


def _note_payloads(rows):
    return [_note_payload(row) for row in rows]


def _feed_payloads(profile_id, viewer_can_edit=False):
    rows = (
        FeedEvent.query.filter_by(profile_id=profile_id, target_type="review")
        .order_by(FeedEvent.created_at.desc())
        .limit(20)
        .all()
    )
    review_ids = [row.target_id for row in rows]
    if not review_ids:
        return []

    review_lookup = {row.id: row for row in Review.query.filter(Review.id.in_(review_ids)).all()}

    payloads = []
    for event in rows:
        review = review_lookup.get(event.target_id)
        if review is None:
            continue
        if not viewer_can_edit and not _review_is_public(review):
            continue

        subject = review.subject
        item_id = None
        if review.work is not None:
            subject = review.work.title
            item_id = review.work.id

        payloads.append(
            {
                "id": event.id,
                "target_type": event.target_type,
                "target_id": event.target_id,
                "created_at": event.created_at,
                "review_id": review.id,
                "review_title": review.review_title,
                "review_subject": subject,
                "review_rating": review.rating,
                "review_category": review.category.upper(),
                "review_visibility": review.visibility,
                "item_id": item_id,
            }
        )

    return payloads


def _profile_payload(profile, viewer_can_edit=False, include_bookmarks=False):
    joined_label = "Recently joined"
    if getattr(profile, "created_at", None):
        joined_label = profile.created_at.strftime("%b %Y")

    review_rows = _review_rows_for_profile(profile.id, viewer_can_edit=viewer_can_edit)
    list_rows = _list_rows_for_profile(profile.id, viewer_can_edit=viewer_can_edit)
    note_rows = _note_rows_for_profile(profile.id, viewer_can_edit=viewer_can_edit)
    draft_review_rows = _review_rows_for_profile(profile.id, viewer_can_edit=viewer_can_edit, include_drafts=True) if viewer_can_edit else []
    draft_list_rows = _list_rows_for_profile(profile.id, viewer_can_edit=viewer_can_edit, include_drafts=True) if viewer_can_edit else []
    draft_note_rows = _note_rows_for_profile(profile.id, viewer_can_edit=viewer_can_edit, include_drafts=True) if viewer_can_edit else []

    review_payloads = _review_payloads(review_rows)
    list_payloads = _list_payloads(list_rows)
    note_payloads = _note_payloads(note_rows)
    draft_review_payloads = _review_payloads(draft_review_rows)
    draft_list_payloads = _list_payloads(draft_list_rows)
    draft_note_payloads = _note_payloads(draft_note_rows)
    feed_payloads = _feed_payloads(profile.id, viewer_can_edit=viewer_can_edit)

    nav_tabs = ["Lists", "Reviews", "Notes", "Feed"]
    if viewer_can_edit:
        nav_tabs.append("Drafts")
    if include_bookmarks:
        nav_tabs.append("Bookmarks")

    return {
        "id": profile.id,
        "username": profile.username,
        "name": profile.display_name,
        "handle": f"@{profile.username}",
        "bio": profile.bio,
        "avatar_url": profile.avatar_url,
        "background_url": profile.background_url,
        "accent_color": profile.accent_color,
        "location": profile.location,
        "profile_link": profile.profile_link,
        "joined_label": joined_label,
        "followers": "0",
        "following": "0",
        "nav_tabs": nav_tabs,
        "list_count": len(list_payloads),
        "review_count": len(review_payloads),
        "note_count": len(note_payloads),
        "post_count": 0,
        "lists": list_payloads,
        "reviews": review_payloads,
        "notes": note_payloads,
        "feed_events": feed_payloads,
        "draft_lists": draft_list_payloads,
        "draft_reviews": draft_review_payloads,
        "draft_notes": draft_note_payloads,
    }


def _resolve_tab_href(tab_name, profile, viewer_can_edit=False):
    if tab_name == "Lists":
        return url_for("main.public_lists", username=profile.username)
    if tab_name == "Reviews":
        return url_for("main.profile", username=profile.username)
    if tab_name == "Notes":
        if viewer_can_edit:
            return url_for("main.my_notes")
        return url_for("main.public_notes", username=profile.username)
    if tab_name == "Feed":
        if viewer_can_edit:
            return url_for("main.my_feed")
        return url_for("main.public_feed", username=profile.username)
    if tab_name == "Drafts" and viewer_can_edit:
        return url_for("main.my_drafts")
    if tab_name == "Bookmarks" and viewer_can_edit:
        return url_for("main.my_bookmarks")
    return "#"


def _render_tab_empty_state(profile, current_tab, title, body):
    app_user = get_current_user()
    viewer_can_edit = app_user.is_authenticated and app_user.user_id == profile.user_id
    profile_payload = _profile_payload(profile, viewer_can_edit=viewer_can_edit, include_bookmarks=viewer_can_edit)
    tab_links = {
        tab_name: _resolve_tab_href(tab_name, profile, viewer_can_edit)
        for tab_name in profile_payload["nav_tabs"]
    }
    return render_template(
        "profile_tab_empty.html",
        profile=profile_payload,
        app_user=app_user,
        viewer_can_edit=viewer_can_edit,
        current_tab=current_tab,
        tab_links=tab_links,
        empty_title=title,
        empty_body=body,
    )


def _item_payload(item):
    return {
        "id": item.id,
        "category": item.normalized_category,
        "category_label": _category_label(item.category),
        "title": item.title,
        "creator_display_name": item.creator_display_name,
        "creator_name": item.creator_name,
        "year_value": item.year_value,
        "length_label": item.length_label,
        "description": item.description,
        "image_url": item.image_url,
        "source_type": item.source_type,
        "source_id": item.source_id,
        "is_user_submitted": item.is_user_submitted,
        "metadata_confidence": item.metadata_confidence,
        "confidence_label": _confidence_label(item.metadata_confidence),
        "metadata": item.metadata_values,
        "metadata_rows": _item_metadata_rows(item),
    }


def _render_profile(profile):
    app_user = get_current_user()
    viewer_can_edit = app_user.is_authenticated and app_user.user_id == profile.user_id
    profile_payload = _profile_payload(profile, viewer_can_edit=viewer_can_edit, include_bookmarks=viewer_can_edit)
    tab_links = {
        tab_name: _resolve_tab_href(tab_name, profile, viewer_can_edit)
        for tab_name in profile_payload["nav_tabs"]
    }
    return render_template(
        "profile.html",
        profile=profile_payload,
        app_user=app_user,
        viewer_can_edit=viewer_can_edit,
        current_tab="Reviews",
        tab_links=tab_links,
    )


def _render_lists(profile):
    app_user = get_current_user()
    viewer_can_edit = app_user.is_authenticated and app_user.user_id == profile.user_id
    profile_payload = _profile_payload(profile, viewer_can_edit=viewer_can_edit, include_bookmarks=viewer_can_edit)
    tab_links = {
        tab_name: _resolve_tab_href(tab_name, profile, viewer_can_edit)
        for tab_name in profile_payload["nav_tabs"]
    }
    return render_template(
        "profile.html",
        profile=profile_payload,
        app_user=app_user,
        viewer_can_edit=viewer_can_edit,
        current_tab="Lists",
        tab_links=tab_links,
    )


def _render_drafts(profile):
    app_user = get_current_user()
    viewer_can_edit = app_user.is_authenticated and app_user.user_id == profile.user_id
    if not viewer_can_edit:
        abort(404)
    profile_payload = _profile_payload(profile, viewer_can_edit=True, include_bookmarks=True)
    tab_links = {
        tab_name: _resolve_tab_href(tab_name, profile, True)
        for tab_name in profile_payload["nav_tabs"]
    }
    return render_template(
        "profile.html",
        profile=profile_payload,
        app_user=app_user,
        viewer_can_edit=True,
        current_tab="Drafts",
        tab_links=tab_links,
    )


def _render_notes(profile):
    app_user = get_current_user()
    viewer_can_edit = app_user.is_authenticated and app_user.user_id == profile.user_id
    profile_payload = _profile_payload(profile, viewer_can_edit=viewer_can_edit, include_bookmarks=viewer_can_edit)
    tab_links = {
        tab_name: _resolve_tab_href(tab_name, profile, viewer_can_edit)
        for tab_name in profile_payload["nav_tabs"]
    }
    return render_template(
        "profile.html",
        profile=profile_payload,
        app_user=app_user,
        viewer_can_edit=viewer_can_edit,
        current_tab="Notes",
        tab_links=tab_links,
    )


def _render_feed(profile):
    app_user = get_current_user()
    viewer_can_edit = app_user.is_authenticated and app_user.user_id == profile.user_id
    profile_payload = _profile_payload(profile, viewer_can_edit=viewer_can_edit, include_bookmarks=viewer_can_edit)
    tab_links = {
        tab_name: _resolve_tab_href(tab_name, profile, viewer_can_edit)
        for tab_name in profile_payload["nav_tabs"]
    }
    return render_template(
        "profile.html",
        profile=profile_payload,
        app_user=app_user,
        viewer_can_edit=viewer_can_edit,
        current_tab="Feed",
        tab_links=tab_links,
    )


def _profile_tab_redirect(tab_name):
    if tab_name == "Lists":
        return redirect(url_for("main.my_lists"))
    if tab_name == "Notes":
        return redirect(url_for("main.my_notes"))
    if tab_name == "Feed":
        return redirect(url_for("main.my_feed"))
    if tab_name == "Drafts":
        return redirect(url_for("main.my_drafts"))
    return redirect(url_for("main.me"))


def _current_profile_or_404():
    app_user = get_current_user()
    profile = UserProfile.query.filter_by(user_id=app_user.user_id).first()
    if profile is None:
        abort(404)
    return profile


def _owned_list_or_404(profile, list_id):
    curio_list = CurioList.query.filter_by(id=list_id, profile_id=profile.id).first()
    if curio_list is None:
        abort(404)
    return curio_list


def _owned_review_or_404(profile, review_id):
    review = Review.query.filter_by(id=review_id, profile_id=profile.id).first()
    if review is None:
        abort(404)
    return review


def _owned_note_or_404(profile, note_id):
    note = CurioNote.query.filter_by(id=note_id, profile_id=profile.id).first()
    if note is None:
        abort(404)
    return note


def _owned_list_item_or_404(curio_list, item_id):
    item = CurioListItem.query.filter_by(id=item_id, list_id=curio_list.id).first()
    if item is None:
        abort(404)
    return item


def _reindex_list_items(curio_list):
    for index, item in enumerate(curio_list.items, start=1):
        item.position = index
    curio_list.item_count = len(curio_list.items)


@bp.route("/")
def home():
    app_user = get_current_user()
    if app_user.is_authenticated:
        profile = UserProfile.query.filter_by(user_id=app_user.user_id).first()
    else:
        profile = UserProfile.query.order_by(UserProfile.created_at.asc()).first()

    if profile is None:
        profile = UserProfile(
            user_id="demo",
            username="curio",
            display_name="Curio",
            bio="Curating pieces of art that feel like home.",
            is_public=True,
        )

    profile_payload = _profile_payload(profile, include_bookmarks=False)
    featured_lists = profile_payload["lists"][:3]
    featured_reviews = profile_payload["reviews"][:3]

    return render_template(
        "home.html",
        app_user=app_user,
        featured_profile=profile_payload,
        featured_lists=featured_lists,
        featured_reviews=featured_reviews,
        central_admin_url=current_app.config.get("LANDING_ADMIN_URL", "/admin"),
    )


@bp.get("/admin")
@auth_required
def admin_home():
    app_user = get_current_user()
    if not app_user.is_admin:
        abort(403)

    return render_template(
        "admin.html",
        app_user=app_user,
        stats={
            "profiles": UserProfile.query.count(),
            "works": CurioItem.query.count(),
            "reviews": Review.query.count(),
            "lists": CurioList.query.count(),
            "notes": CurioNote.query.count(),
        },
    )


@bp.route("/u/<username>")
def profile(username):
    profile_row = UserProfile.query.filter_by(username=username).first()
    if profile_row is None or not profile_row.is_public:
        abort(404)

    return _render_profile(profile_row)


@bp.route("/u/<username>/lists")
def public_lists(username):
    profile_row = UserProfile.query.filter_by(username=username).first()
    if profile_row is None or not profile_row.is_public:
        abort(404)

    return _render_lists(profile_row)


@bp.route("/u/<username>/notes")
def public_notes(username):
    profile_row = UserProfile.query.filter_by(username=username).first()
    if profile_row is None or not profile_row.is_public:
        abort(404)
    return _render_notes(profile_row)


@bp.route("/u/<username>/feed")
def public_feed(username):
    profile_row = UserProfile.query.filter_by(username=username).first()
    if profile_row is None or not profile_row.is_public:
        abort(404)
    return _render_feed(profile_row)


@bp.route("/u/<username>/bookmarks")
@auth_required
def public_bookmarks(username):
    profile_row = UserProfile.query.filter_by(username=username).first()
    if profile_row is None:
        abort(404)
    app_user = get_current_user()
    if app_user.user_id != profile_row.user_id:
        abort(404)
    return _render_tab_empty_state(
        profile_row,
        current_tab="Bookmarks",
        title="No bookmarks yet",
        body="Saved items, lists, and posts will appear in your private bookmarks tab.",
    )


@bp.route("/u/<username>/drafts")
@auth_required
def public_drafts(username):
    profile_row = UserProfile.query.filter_by(username=username).first()
    if profile_row is None:
        abort(404)
    app_user = get_current_user()
    if app_user.user_id != profile_row.user_id:
        abort(404)
    return _render_drafts(profile_row)


@bp.route("/me")
@auth_required
def me():
    return _render_profile(_current_profile_or_404())


@bp.get("/me/notes")
@auth_required
def my_notes():
    profile = _current_profile_or_404()
    return redirect(url_for("main.public_notes", username=profile.username))


@bp.get("/me/feed")
@auth_required
def my_feed():
    profile = _current_profile_or_404()
    return redirect(url_for("main.public_feed", username=profile.username))


@bp.get("/me/bookmarks")
@auth_required
def my_bookmarks():
    profile = _current_profile_or_404()
    return redirect(url_for("main.public_bookmarks", username=profile.username))


@bp.get("/me/drafts")
@auth_required
def my_drafts():
    profile = _current_profile_or_404()
    return redirect(url_for("main.public_drafts", username=profile.username))


@bp.post("/me/profile")
@auth_required
def update_profile_header():
    profile = _current_profile_or_404()
    location = request.form.get("location", "").strip()
    profile_link = request.form.get("profile_link", "").strip()
    avatar_url = request.form.get("avatar_url", "").strip()
    background_url = request.form.get("background_url", "").strip()

    if not all(_is_allowed_profile_url(value) for value in [profile_link, avatar_url, background_url]):
        flash("Profile link and image URLs must start with http:// or https://", "error")
        return redirect(url_for("main.me"))

    profile.location = location
    profile.profile_link = profile_link
    profile.avatar_url = avatar_url
    profile.background_url = background_url
    db.session.commit()
    flash("Profile header updated.", "success")
    return redirect(url_for("main.me"))


@bp.get("/me/lists")
@auth_required
def my_lists():
    return _render_lists(_current_profile_or_404())


@bp.get("/items")
def items_catalog():
    app_user = get_current_user()
    category_order = ["book", "song", "art", "film"]
    category_labels = {"book": "Books", "song": "Songs", "art": "Arts", "film": "Films"}

    all_items = CurioItem.query.order_by(CurioItem.category.asc(), CurioItem.title.asc()).all()
    grouped = {key: [] for key in category_order}
    for row in all_items:
        category_key = normalize_work_category(row.category)
        grouped.setdefault(category_key, [])
        grouped[category_key].append(_item_payload(row))

    sections = []
    for category in category_order:
        sections.append(
            {
                "key": category,
                "label": category_labels[category],
                "items": grouped.get(category, []),
            }
        )

    return render_template(
        "items_catalog.html",
        app_user=app_user,
        sections=sections,
        work_categories=[{"value": value, "label": _category_label(value)} for value in category_order],
        work_form=_blank_work_form_data(),
    )


@bp.get("/uploads/<path:filename>")
def uploaded_work_file(filename):
    return send_from_directory(_uploaded_works_root(), filename)


@bp.get("/items/<int:item_id>")
def item_detail(item_id):
    app_user = get_current_user()
    item = CurioItem.query.filter_by(id=item_id).first_or_404()
    highlighted_review_id = request.args.get("highlight_review", type=int)
    related_reviews = _collect_item_review_rows(item, app_user, highlighted_review_id=highlighted_review_id)[:10]

    review_cards = [_review_payload(row, app_user=app_user, highlighted_review_id=highlighted_review_id) for row in related_reviews]

    return render_template(
        "item_detail.html",
        app_user=app_user,
        item=_item_payload(item),
        related_reviews=review_cards,
        average_rating=round(sum(card["rating"] for card in review_cards) / len(review_cards), 1)
        if review_cards
        else None,
    )


@bp.get("/reviews/new")
@auth_required
def new_review_search():
    category = normalize_work_category(request.args.get("category", "book")) or "book"
    query = request.args.get("q", "").strip()
    work_id = request.args.get("work_id", type=int)
    if work_id is not None:
        return redirect(url_for("main.compose_review", work_id=work_id))

    exact_matches, similar_matches = search_existing_works(category, query)
    search_state = "initial"
    if query:
        if exact_matches:
            search_state = "exact"
        elif similar_matches:
            search_state = "similar"
        else:
            search_state = "none"

    return render_template(
        "review_search.html",
        app_user=get_current_user(),
        category=category,
        category_label=_category_label(category),
        query=query,
        search_state=search_state,
        exact_matches=[_item_payload(row) for row in exact_matches],
        similar_matches=[_item_payload(row) for row in similar_matches],
    )


@bp.get("/reviews/new/book")
@auth_required
def new_book_entry():
    title = request.args.get("title", "").strip()
    return render_template(
        "review_create_book.html",
        app_user=get_current_user(),
        form_data=_blank_book_entry_form(initial_title=title),
        duplicate_matches=[],
        duplicate_warning=False,
    )


@bp.post("/reviews/new/book")
@auth_required
def create_book_for_review():
    _current_profile_or_404()
    form_data = _book_entry_form_from_request()
    title = form_data["title"]
    if not title:
        flash("Book title is required.", "error")
        return render_template(
            "review_create_book.html",
            app_user=get_current_user(),
            form_data=form_data,
            duplicate_matches=[],
            duplicate_warning=False,
        )

    common = {
        "category": "book",
        "title": title,
        "creator_display_name": form_data["author"],
        "image_url": form_data["image_url"],
        "description": form_data["description"],
        "source_type": "user",
        "source_id": f"user-{uuid4().hex}",
        "is_user_submitted": True,
        "metadata_confidence": None,
    }
    metadata = {
        "author": form_data["author"],
        "year": form_data["year"],
        "pages": form_data["pages"],
        "publisher": form_data["publisher"],
        "isbn": form_data["isbn"],
        "language": form_data["language"],
    }

    if common["image_url"] and not _is_allowed_profile_url(common["image_url"]):
        flash("Cover image URL must start with http:// or https://.", "error")
        return render_template(
            "review_create_book.html",
            app_user=get_current_user(),
            form_data=form_data,
            duplicate_matches=[],
            duplicate_warning=False,
        )

    exact_matches, similar_matches = search_existing_works("book", title)
    duplicate_matches = exact_matches + [row for row in similar_matches if row.id not in {match.id for match in exact_matches}]
    if duplicate_matches and request.form.get("confirm_create_new", "") != "1":
        return render_template(
            "review_create_book.html",
            app_user=get_current_user(),
            form_data=form_data,
            duplicate_matches=[_item_payload(row) for row in duplicate_matches[:5]],
            duplicate_warning=True,
        )

    work, metadata_record = create_work(common, metadata)
    db.session.add(work)
    db.session.flush()
    metadata_record.work_id = work.id
    db.session.add(metadata_record)
    db.session.commit()
    flash("Book created. Now write your review.", "success")
    return redirect(url_for("main.compose_review", work_id=work.id))


@bp.get("/reviews/new/compose")
@auth_required
def compose_review():
    work_id = request.args.get("work_id", type=int)
    work = CurioItem.query.filter_by(id=work_id).first_or_404() if work_id is not None else None
    return render_template(
        "review_compose.html",
        app_user=get_current_user(),
        work=_item_payload(work) if work is not None else None,
        review_form=_blank_review_form_data(work),
    )


@bp.post("/reviews/new/compose")
@auth_required
def submit_review():
    profile = _current_profile_or_404()
    work_id = request.form.get("work_id", type=int)
    work = CurioItem.query.filter_by(id=work_id).first_or_404() if work_id is not None else None
    review_form = _review_form_from_request(default_work=work)

    try:
        rating = max(1, min(5, int(review_form["rating"])))
    except (TypeError, ValueError):
        flash("Rating is required.", "error")
        return render_template(
            "review_compose.html",
            app_user=get_current_user(),
            work=_item_payload(work) if work is not None else None,
            review_form=review_form,
        )

    review = Review(
        profile_id=profile.id,
        work_id=work.id if work is not None else None,
        subject=work.title if work is not None else review_form["subject"],
        category=work.normalized_category if work is not None else review_form["category"],
        review_title=review_form["review_title"],
        body=review_form["body"],
        rating=rating,
        spoiler=review_form["spoiler"],
        tags=review_form["tags"],
        visibility=review_form["visibility"],
        status=review_form["status"],
    )
    db.session.add(review)
    db.session.flush()
    _sync_review_feed_event(review)
    db.session.commit()

    if review.status == "draft":
        flash("Draft saved.", "success")
    else:
        flash("Review published.", "success")
    return redirect(url_for("main.item_detail", item_id=work.id, highlight_review=review.id))


@bp.post("/items")
@auth_required
def create_item():
    _current_profile_or_404()
    form_data = _work_form_data_from_request()
    common, metadata = _work_submission_payload(form_data)

    if not common["title"] or not common["creator_display_name"]:
        flash("Work title and creator name are required.", "error")
        return redirect(url_for("main.items_catalog"))

    image_url = common["image_url"]
    uploaded_file = request.files.get("image_file")
    if uploaded_file and uploaded_file.filename:
        try:
            common["image_url"] = uploaded_image_path(uploaded_file, common["title"])
        except ValueError as exc:
            flash(str(exc), "error")
            return redirect(url_for("main.items_catalog"))
    elif image_url and not _is_allowed_profile_url(image_url):
        flash("Image URL must start with http:// or https:// unless you upload a file.", "error")
        return redirect(url_for("main.items_catalog"))

    duplicate = _find_duplicate_work(common)
    if duplicate is not None:
        flash("That work already exists in the catalog.", "error")
        return redirect(url_for("main.item_detail", item_id=duplicate.id))

    work, metadata_record = create_work(common, metadata)
    db.session.add(work)
    db.session.flush()
    metadata_record.work_id = work.id
    db.session.add(metadata_record)
    db.session.commit()
    flash("Work submitted.", "success")
    return redirect(url_for("main.item_detail", item_id=work.id))


@bp.post("/me/lists")
@auth_required
def create_list():
    profile = _current_profile_or_404()
    title = request.form.get("title", "").strip()
    category = request.form.get("category", "mixed").strip().lower() or "mixed"
    description = request.form.get("description", "").strip()
    visibility = _normalize_list_visibility(request.form.get("visibility", "public"))

    if not title:
        flash("List title is required.", "error")
        return redirect(url_for("main.my_lists"))

    curio_list = CurioList(
        profile_id=profile.id,
        title=title,
        category=category,
        description=description,
        visibility=visibility,
        item_count=0,
    )
    db.session.add(curio_list)
    db.session.commit()
    flash("List created.", "success")
    return redirect(url_for("main.my_lists"))


@bp.post("/me/lists/<int:list_id>/items")
@auth_required
def create_list_item(list_id):
    profile = _current_profile_or_404()
    curio_list = _owned_list_or_404(profile, list_id)

    title = request.form.get("title", "").strip()
    creator_name = request.form.get("creator_name", "").strip()
    notes = request.form.get("notes", "").strip()
    if not title:
        flash("List item title is required.", "error")
        return redirect(url_for("main.my_lists"))

    next_position = (curio_list.items[-1].position + 1) if curio_list.items else 1
    db.session.add(
        CurioListItem(
            list_id=curio_list.id,
            position=next_position,
            title=title,
            creator_name=creator_name,
            notes=notes,
        )
    )
    curio_list.item_count = next_position
    db.session.commit()
    flash("List item added.", "success")
    return redirect(url_for("main.my_lists"))


@bp.post("/me/lists/<int:list_id>/edit")
@auth_required
def edit_list(list_id):
    profile = _current_profile_or_404()
    curio_list = _owned_list_or_404(profile, list_id)
    title = request.form.get("title", "").strip()
    category = request.form.get("category", curio_list.category).strip().lower() or curio_list.category
    description = request.form.get("description", "").strip()
    visibility = _normalize_list_visibility(request.form.get("visibility", curio_list.visibility))
    return_tab = request.form.get("return_tab", "Lists").strip()

    if not title:
        flash("List title is required.", "error")
        return redirect(url_for("main.my_lists"))

    curio_list.title = title
    curio_list.category = category
    curio_list.description = description
    curio_list.visibility = visibility
    db.session.commit()
    flash("List updated.", "success")
    return _profile_tab_redirect(return_tab)


@bp.post("/me/lists/<int:list_id>/delete")
@auth_required
def delete_list(list_id):
    profile = _current_profile_or_404()
    curio_list = _owned_list_or_404(profile, list_id)
    return_tab = request.form.get("return_tab", "Lists").strip()
    db.session.delete(curio_list)
    db.session.commit()
    flash("List deleted.", "success")
    return _profile_tab_redirect(return_tab)


@bp.post("/me/lists/<int:list_id>/items/<int:item_id>/move")
@auth_required
def move_list_item(list_id, item_id):
    profile = _current_profile_or_404()
    curio_list = _owned_list_or_404(profile, list_id)
    item = _owned_list_item_or_404(curio_list, item_id)
    direction = request.form.get("direction", "").strip().lower()
    items = list(curio_list.items)
    current_index = next((index for index, row in enumerate(items) if row.id == item.id), None)
    if current_index is None:
        abort(404)

    target_index = current_index
    if direction == "up" and current_index > 0:
        target_index = current_index - 1
    elif direction == "down" and current_index < len(items) - 1:
        target_index = current_index + 1

    if target_index != current_index:
        items[current_index], items[target_index] = items[target_index], items[current_index]
        for index, row in enumerate(items, start=1):
            row.position = index
        db.session.commit()
        flash("List item reordered.", "success")
    else:
        flash("List item already at edge.", "error")
    return redirect(url_for("main.my_lists"))


@bp.post("/me/lists/<int:list_id>/items/<int:item_id>/delete")
@auth_required
def delete_list_item(list_id, item_id):
    profile = _current_profile_or_404()
    curio_list = _owned_list_or_404(profile, list_id)
    item = _owned_list_item_or_404(curio_list, item_id)
    db.session.delete(item)
    db.session.flush()
    _reindex_list_items(curio_list)
    db.session.commit()
    flash("List item deleted.", "success")
    return redirect(url_for("main.my_lists"))


@bp.post("/me/reviews")
@auth_required
def create_review():
    profile = _current_profile_or_404()
    subject = request.form.get("subject", "").strip()
    category = request.form.get("category", "mixed").strip().lower() or "mixed"
    body = request.form.get("body", "").strip()
    rating_raw = request.form.get("rating", "4").strip()
    review_title = request.form.get("review_title", "").strip()
    spoiler = request.form.get("spoiler", "") == "on"
    tags = request.form.get("tags", "").strip()
    visibility = _normalize_review_visibility(request.form.get("visibility", "public"))
    status = _normalize_review_status(request.form.get("status", "published"))
    work_id = request.form.get("work_id", type=int)
    work = CurioItem.query.filter_by(id=work_id).first() if work_id is not None else None

    if work is not None:
        subject = work.title
        category = work.normalized_category

    if not subject:
        flash("Review subject is required.", "error")
        return redirect(url_for("main.me"))

    try:
        rating = max(1, min(5, int(rating_raw)))
    except ValueError:
        rating = 4

    review = Review(
        profile_id=profile.id,
        work_id=work.id if work is not None else None,
        subject=subject,
        category=category,
        review_title=review_title,
        body=body,
        rating=rating,
        spoiler=spoiler,
        tags=tags,
        visibility=visibility,
        status=status,
    )
    db.session.add(review)
    db.session.flush()
    _sync_review_feed_event(review)
    db.session.commit()
    flash("Review published.", "success")
    return redirect(url_for("main.me"))


@bp.post("/me/notes")
@auth_required
def create_note():
    profile = _current_profile_or_404()
    title = request.form.get("title", "").strip()
    body = request.form.get("body", "").strip()
    visibility = _normalize_note_visibility(request.form.get("visibility", "public"))
    status = _normalize_note_status(request.form.get("status", "published"))

    if not title:
        flash("Note title is required.", "error")
        return redirect(url_for("main.my_notes"))

    note = CurioNote(
        profile_id=profile.id,
        title=title,
        body=body,
        visibility=visibility,
        status=status,
    )
    db.session.add(note)
    db.session.commit()

    if note.status == "draft":
        flash("Note draft saved.", "success")
    else:
        flash("Note published.", "success")
    return redirect(url_for("main.my_notes"))


@bp.post("/me/notes/<int:note_id>/edit")
@auth_required
def edit_note(note_id):
    profile = _current_profile_or_404()
    note = _owned_note_or_404(profile, note_id)
    title = request.form.get("title", "").strip()
    body = request.form.get("body", "").strip()
    visibility = _normalize_note_visibility(request.form.get("visibility", note.visibility))
    status = _normalize_note_status(request.form.get("status", note.status))
    return_tab = request.form.get("return_tab", "Notes").strip()

    if not title:
        flash("Note title is required.", "error")
        return _profile_tab_redirect(return_tab)

    note.title = title
    note.body = body
    note.visibility = visibility
    note.status = status
    db.session.commit()
    flash("Note updated.", "success")
    return _profile_tab_redirect(return_tab)


@bp.post("/me/notes/<int:note_id>/delete")
@auth_required
def delete_note(note_id):
    profile = _current_profile_or_404()
    note = _owned_note_or_404(profile, note_id)
    return_tab = request.form.get("return_tab", "Notes").strip()
    db.session.delete(note)
    db.session.commit()
    flash("Note deleted.", "success")
    return _profile_tab_redirect(return_tab)


@bp.post("/me/reviews/<int:review_id>/edit")
@auth_required
def edit_review(review_id):
    profile = _current_profile_or_404()
    review = _owned_review_or_404(profile, review_id)
    subject = request.form.get("subject", "").strip()
    category = request.form.get("category", review.category).strip().lower() or review.category
    body = request.form.get("body", "").strip()
    rating_raw = request.form.get("rating", str(review.rating)).strip()
    review_title = request.form.get("review_title", review.review_title).strip()
    spoiler = request.form.get("spoiler", "") == "on"
    tags = request.form.get("tags", review.tags).strip()
    visibility = _normalize_review_visibility(request.form.get("visibility", review.visibility))
    status = _normalize_review_status(request.form.get("status", review.status))
    return_tab = request.form.get("return_tab", "Reviews").strip()

    if not subject:
        flash("Review subject is required.", "error")
        return redirect(url_for("main.me"))

    try:
        rating = max(1, min(5, int(rating_raw)))
    except ValueError:
        rating = review.rating

    review.subject = subject
    review.category = category
    review.review_title = review_title
    review.body = body
    review.rating = rating
    review.spoiler = spoiler
    review.tags = tags
    review.visibility = visibility
    review.status = status
    _sync_review_feed_event(review)
    db.session.commit()
    flash("Review updated.", "success")
    return _profile_tab_redirect(return_tab)


@bp.post("/me/reviews/<int:review_id>/delete")
@auth_required
def delete_review(review_id):
    profile = _current_profile_or_404()
    review = _owned_review_or_404(profile, review_id)
    return_tab = request.form.get("return_tab", "Reviews").strip()
    feed_event = _feed_event_for_review(review.id)
    if feed_event is not None:
        db.session.delete(feed_event)
    db.session.delete(review)
    db.session.commit()
    flash("Review deleted.", "success")
    return _profile_tab_redirect(return_tab)
