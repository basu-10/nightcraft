from difflib import SequenceMatcher
from pathlib import Path
from urllib.parse import quote_plus
from uuid import uuid4

from flask import current_app
from werkzeug.utils import secure_filename

from .catalog_seed import CATALOG_SEED_DATA
from .models import (
    NeeraArtMetadata,
    NeeraBookMetadata,
    NeeraFilmMetadata,
    NeeraItem,
    NeeraSongMetadata,
)

ALLOWED_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp"}

CATEGORY_METADATA_MODELS = {
    "book": NeeraBookMetadata,
    "film": NeeraFilmMetadata,
    "song": NeeraSongMetadata,
    "art": NeeraArtMetadata,
}

CATEGORY_METADATA_FIELDS = {
    "book": ["author", "year", "pages", "publisher", "isbn", "language"],
    "film": ["director", "year", "runtime_minutes", "country", "language"],
    "song": ["artist", "album", "year", "duration_seconds"],
    "art": ["artist", "year", "medium", "movement", "museum"],
}


def normalize_work_category(category):
    category_key = (category or "").strip().lower()
    mapping = {
        "book": "book",
        "books": "book",
        "film": "film",
        "films": "film",
        "movie": "film",
        "movies": "film",
        "song": "song",
        "songs": "song",
        "music": "song",
        "art": "art",
        "arts": "art",
        "artwork": "art",
        "artworks": "art",
    }
    return mapping.get(category_key, category_key)


def catalog_image_url(raw_value, fallback_label):
    value = (raw_value or "").strip()
    if value.startswith("http://") or value.startswith("https://"):
        return value
    return f"https://placehold.co/600x900?text={quote_plus(fallback_label)}"


def build_seed_payload(entry):
    common = dict(entry.get("common", {}))
    common["category"] = normalize_work_category(common.get("category"))
    common["image_url"] = catalog_image_url(common.get("image_url"), common.get("title", "Neera"))
    return common, dict(entry.get("metadata", {}))


def metadata_confidence_for(category, metadata, is_user_submitted):
    if not is_user_submitted:
        return 1.0

    fields = CATEGORY_METADATA_FIELDS.get(normalize_work_category(category), [])
    if not fields:
        return 0.2

    normalized = normalize_work_category(category)
    creator_fields = {
        "book": "author",
        "film": "director",
        "song": "artist",
        "art": "artist",
    }
    confidence = 0.2
    creator_field = creator_fields.get(normalized)
    if creator_field and metadata.get(creator_field) not in (None, ""):
        confidence += 0.15

    remaining_fields = [field_name for field_name in fields if field_name != creator_field]
    if remaining_fields:
        increment = 0.65 / len(remaining_fields)
        for field_name in remaining_fields:
            value = metadata.get(field_name)
            if value not in (None, ""):
                confidence += increment
    return round(min(confidence, 1.0), 2)


def coerce_optional_int(raw_value):
    if raw_value is None:
        return None
    if isinstance(raw_value, int):
        return raw_value
    value = str(raw_value).strip()
    if not value:
        return None
    return int(value)


def prepare_metadata(category, raw_metadata, creator_display_name=""):
    normalized = normalize_work_category(category)
    metadata = dict(raw_metadata or {})

    if normalized == "book" and not metadata.get("author"):
        metadata["author"] = creator_display_name
    if normalized == "film" and not metadata.get("director"):
        metadata["director"] = creator_display_name
    if normalized == "song" and not metadata.get("artist"):
        metadata["artist"] = creator_display_name
    if normalized == "art" and not metadata.get("artist"):
        metadata["artist"] = creator_display_name

    int_fields = {
        "book": ["year", "pages"],
        "film": ["year", "runtime_minutes"],
        "song": ["year", "duration_seconds"],
        "art": ["year"],
    }
    for field_name in int_fields.get(normalized, []):
        metadata[field_name] = coerce_optional_int(metadata.get(field_name, ""))

    string_fields = set(CATEGORY_METADATA_FIELDS.get(normalized, [])) - set(int_fields.get(normalized, []))
    for field_name in string_fields:
        metadata[field_name] = (metadata.get(field_name) or "").strip()

    return metadata


def create_metadata_record(work, category, metadata):
    model = CATEGORY_METADATA_MODELS[normalize_work_category(category)]
    return model(work_id=work.id, **metadata)


def find_existing_seed_work(common):
    source_type = (common.get("source_type") or "").strip()
    source_id = (common.get("source_id") or "").strip()
    if source_type and source_id:
        return NeeraItem.query.filter_by(source_type=source_type, source_id=source_id).first()

    return NeeraItem.query.filter_by(
        category=normalize_work_category(common.get("category")),
        title=common.get("title", ""),
        creator_display_name=common.get("creator_display_name", ""),
    ).first()


def create_work(common, metadata):
    common_payload = dict(common)
    common_payload["category"] = normalize_work_category(common_payload.get("category"))
    work = NeeraItem(**common_payload)
    metadata_payload = prepare_metadata(
        common_payload["category"],
        metadata,
        creator_display_name=common_payload.get("creator_display_name", ""),
    )
    work.metadata_confidence = metadata_confidence_for(
        common_payload["category"],
        metadata_payload,
        work.is_user_submitted,
    )
    return work, create_metadata_record(work, common_payload["category"], metadata_payload)


def seed_catalog_items(session):
    created_count = 0
    for entry in CATALOG_SEED_DATA:
        common, metadata = build_seed_payload(entry)
        existing = find_existing_seed_work(common)
        if existing is not None:
            continue
        work, metadata_record = create_work(common, metadata)
        session.add(work)
        session.flush()
        metadata_record.work_id = work.id
        session.add(metadata_record)
        created_count += 1
    return created_count


def uploaded_image_path(file_storage, title):
    filename = secure_filename(file_storage.filename or "")
    extension = Path(filename).suffix.lower()
    if extension not in ALLOWED_IMAGE_EXTENSIONS:
        raise ValueError("Image uploads must be jpg, jpeg, png, gif, or webp.")

    uploads_root = Path(current_app.instance_path) / current_app.config.get("UPLOADS_DIR", "uploads") / "works"
    uploads_root.mkdir(parents=True, exist_ok=True)
    stored_name = f"{uuid4().hex}{extension}"
    file_storage.save(uploads_root / stored_name)
    return f"/uploads/works/{stored_name}"


def search_existing_works(category, query, limit=5):
    normalized_category = normalize_work_category(category)
    search_text = (query or "").strip().lower()
    if not search_text:
        return [], []

    rows = NeeraItem.query.filter_by(category=normalized_category).all()
    exact_matches = []
    scored_rows = []
    for row in rows:
        title = (row.title or "").strip().lower()
        creator = (row.creator_display_name or "").strip().lower()
        haystack = f"{title} {creator}".strip()
        if title == search_text:
            exact_matches.append(row)
            continue

        similarity = SequenceMatcher(None, search_text, title).ratio()
        term_overlap = 0.0
        search_terms = [part for part in search_text.split() if part]
        if search_terms:
            matched_terms = sum(1 for term in search_terms if term in haystack)
            term_overlap = matched_terms / len(search_terms)
        score = max(similarity, term_overlap)
        if score >= 0.38:
            scored_rows.append((score, row))

    scored_rows.sort(key=lambda pair: (-pair[0], pair[1].title.lower()))
    similar_matches = [row for _, row in scored_rows[:limit]]
    return exact_matches[:1], similar_matches
