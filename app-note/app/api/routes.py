"""
REST API blueprint — CRUD for notes/folders/tags + desktop sync endpoints.

Authentication:
    - Browser sessions: g.user_id set by app factory's before_request hook.
    - Desktop Basic Auth: Authorization: Basic <base64(username:password)>
"""
import base64
import io
import json
from datetime import datetime, timezone
from functools import wraps

from flask import Blueprint, g, jsonify, request, send_file
from werkzeug.security import check_password_hash

from ..database import (
    get_connection,
    _get_last_insert_id,
    _ensure_tag,
    get_all_folders,
    get_folder_tombstones_since,
    create_folder,
    update_folder,
    delete_folder,
    apply_folder_tombstone,
    upsert_folder_by_sync_id,
    get_all_tags,
    get_tag_tombstones_since,
    upsert_tag_by_sync_id,
    update_tag,
    delete_tag,
    apply_tag_tombstone,
    get_note_tombstones_since,
    apply_note_tombstone,
    get_notes,
    get_trash_notes,
    get_note,
    create_note,
    update_note,
    delete_note,
    get_notes_since,
    get_user_max_server_rev,
    allocate_server_rev,
    get_unresolved_conflicts,
    resolve_conflict,
    export_user_backup,
    import_user_backup,
    delete_all_user_data,
    get_user_id_for_api_token,
)
from ..sync_logging import get_sync_logger

api_bp = Blueprint("api", __name__)
_sync_log = get_sync_logger()


# ── Auth helpers ──────────────────────────────────────────────────────────────

def _resolve_user_from_basic_auth() -> int | None:
    """Return user_id for valid Basic Auth credentials, else None."""
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Basic "):
        return None
    try:
        decoded = base64.b64decode(auth[6:]).decode("utf-8")
        username, _, password = decoded.partition(":")
    except Exception:
        return None
    if not username or not password:
        return None
    conn = get_connection()
    user = conn.execute(
        "SELECT id, password FROM users WHERE LOWER(username)=LOWER(?)", (username,)
    ).fetchone()
    conn.close()
    if not user:
        return None
    return int(user["id"]) if check_password_hash(user["password"], password) else None


def _resolve_user_from_api_token() -> int | None:
    auth = (request.headers.get("Authorization") or "").strip()
    if auth.lower().startswith("bearer "):
        return get_user_id_for_api_token(auth[7:].strip())

    header_token = (request.headers.get("X-API-Token") or "").strip()
    if header_token:
        return get_user_id_for_api_token(header_token)

    return None


def require_auth(f):
    """Allow browser session or Basic Auth (username:password)."""
    @wraps(f)
    def wrapper(*args, **kwargs):
        user_id = g.user_id or _resolve_user_from_api_token() or _resolve_user_from_basic_auth()
        if not user_id:
            return jsonify({"error": "Authentication required"}), 401
        g.user_id = user_id
        return f(*args, **kwargs)
    return wrapper


def _ok(data=None, code=200):
    return jsonify(data if data is not None else {"ok": True}), code


def _err(msg, code):
    return jsonify({"error": msg}), code


def _parse_sync_rev(raw) -> int | None:
    if raw is None:
        return None
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return None
    return value if value >= 0 else None


def _normalize_client_timestamp(raw: str | None) -> str:
    value = (raw or "").strip()
    if not value:
        return ""
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return value
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
    return parsed.strftime("%Y-%m-%d %H:%M:%S")


def _resolve_folder_id_for_user(raw_folder_id, user_id: int) -> int | None:
    """Return a valid folder id for this user or None when invalid/missing."""
    if raw_folder_id is None or raw_folder_id == "":
        return None
    try:
        folder_id = int(raw_folder_id)
    except (TypeError, ValueError):
        return None
    conn = get_connection()
    row = conn.execute(
        "SELECT 1 FROM folders WHERE id=? AND user_id=?",
        (folder_id, user_id),
    ).fetchone()
    conn.close()
    return folder_id if row else None


def _sync_request_ids() -> tuple[str | None, str]:
    idem_key = (request.headers.get("X-Idempotency-Key") or "").strip() or None
    corr_id = (request.headers.get("X-Correlation-ID") or "").strip() or "-"
    return idem_key, corr_id


def _idempotency_replay(user_id: int, idem_key: str | None):
    if not idem_key:
        return None
    conn = get_connection()
    row = conn.execute(
        """
        SELECT response_json, status_code
        FROM sync_idempotency
        WHERE user_id=? AND method=? AND path=? AND idem_key=?
        """,
        (user_id, request.method, request.path, idem_key),
    ).fetchone()
    conn.close()
    if not row:
        return None
    try:
        payload = json.loads(row["response_json"])
    except Exception:
        payload = {"ok": True}
    return _ok(payload, int(row["status_code"] or 200))


def _idempotency_store(user_id: int, idem_key: str | None, payload: dict, status_code: int = 200) -> None:
    if not idem_key:
        return
    conn = get_connection()
    conn.execute(
        """
        INSERT OR IGNORE INTO sync_idempotency(user_id, method, path, idem_key, response_json, status_code)
        VALUES (?,?,?,?,?,?)
        """,
        (user_id, request.method, request.path, idem_key, json.dumps(payload), int(status_code)),
    )
    conn.commit()
    conn.close()


# ── Folders ───────────────────────────────────────────────────────────────────

@api_bp.route("/folders", methods=["GET"])
@require_auth
def list_folders():
    return _ok(get_all_folders(g.user_id))


@api_bp.route("/folders", methods=["POST"])
@require_auth
def post_folder():
    data = request.get_json(silent=True) or {}
    name = (data.get("name") or "").strip()
    if not name:
        return _err("name is required", 400)
    parent_id = data.get("parent_id") or None
    color = data.get("color") or None
    try:
        folder_id = create_folder(g.user_id, name, parent_id, color)
    except Exception:
        return _err("Folder name already exists", 409)
    _sync_log.info("WEB folder created  user_id=%s folder_id=%s name=%r", g.user_id, folder_id, name)
    return _ok({"id": folder_id}, 201)


@api_bp.route("/folders/<int:folder_id>", methods=["PUT"])
@require_auth
def put_folder(folder_id):
    data = request.get_json(silent=True) or {}
    update_folder(g.user_id, folder_id,
                  name=data.get("name"),
                  color=data.get("color"),
                  parent_id=data.get("parent_id"))
    _sync_log.info("WEB folder updated  user_id=%s folder_id=%s", g.user_id, folder_id)
    return _ok()


@api_bp.route("/folders/<int:folder_id>", methods=["DELETE"])
@require_auth
def del_folder(folder_id):
    delete_folder(g.user_id, folder_id)
    return _ok()


# ── Tags ──────────────────────────────────────────────────────────────────────

@api_bp.route("/tags", methods=["GET"])
@require_auth
def list_tags():
    return _ok(get_all_tags(g.user_id))
@api_bp.route("/tags", methods=["POST"])
@require_auth
def post_tag():
    from uuid import uuid4
    data = request.get_json(silent=True) or {}
    name = (data.get("name") or "").strip()
    if not name:
        return _err("name is required", 400)
    
    normalized = name.lower().lstrip("#")
    if not normalized:
        return _err("name is required", 400)
    
    existing = list(get_all_tags(g.user_id))
    if any(t["name"].lower() == normalized for t in existing):
        return _err("Tag already exists", 409)
    
    conn = get_connection()
    
    color = (data.get("color") or "").strip()
    normalized_color = None
    if color and color.startswith("#"):
        normalized_color = color[:7].upper()
    
    try:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO tags (user_id, name, color, sync_id) VALUES (?,?,?,?)",
            (g.user_id, normalized, normalized_color, str(uuid4()))
        )
        conn.commit()
        tag_id = _get_last_insert_id(conn, cursor)
        _sync_log.info("WEB tag created  user_id=%s tag_id=%s name=%r", g.user_id, tag_id, normalized)
        return _ok({"id": tag_id}, 201)
    except Exception as e:
        conn.rollback()
        return _err(str(e), 400)
    finally:
        conn.close()



@api_bp.route("/tags/<int:tag_id>", methods=["PUT"])
@require_auth
def put_tag(tag_id):
    data = request.get_json(silent=True) or {}
    update_tag(g.user_id, tag_id,
               name=data.get("name"),
               color=data.get("color"))
    _sync_log.info("WEB tag updated  user_id=%s tag_id=%s", g.user_id, tag_id)
    return _ok()


@api_bp.route("/tags/<int:tag_id>", methods=["DELETE"])
@require_auth
def del_tag(tag_id):
    delete_tag(g.user_id, tag_id)
    return _ok()


# ── Notes ─────────────────────────────────────────────────────────────────────

@api_bp.route("/notes", methods=["GET"])
@require_auth
def list_notes():
    folder_id = request.args.get("folder_id", type=int)
    tag_id = request.args.get("tag_id", type=int)
    keyword = (request.args.get("q") or "").strip() or None
    favorites = request.args.get("favorites") == "1"
    sort = request.args.get("sort", "newest")
    limit = min(request.args.get("limit", 200, type=int), 500)
    offset = request.args.get("offset", 0, type=int)
    date_filter = (request.args.get("date") or "").strip() or None
    return _ok(get_notes(g.user_id, folder_id=folder_id, tag_id=tag_id,
                         keyword=keyword, favorites_only=favorites,
                         sort=sort, limit=limit, offset=offset,
                         date_filter=date_filter))


@api_bp.route("/trash", methods=["GET"])
@require_auth
def list_trash_notes():
    keyword = (request.args.get("q") or "").strip() or None
    sort = request.args.get("sort", "newest")
    limit = min(request.args.get("limit", 200, type=int), 500)
    offset = request.args.get("offset", 0, type=int)
    return _ok(get_trash_notes(
        g.user_id,
        keyword=keyword,
        sort=sort,
        limit=limit,
        offset=offset,
    ))


@api_bp.route("/notes/<int:note_id>", methods=["GET"])
@require_auth
def get_single_note(note_id):
    note = get_note(g.user_id, note_id)
    if not note:
        return _err("Not found", 404)
    return _ok(note)


@api_bp.route("/notes", methods=["POST"])
@require_auth
def post_note():
    data = request.get_json(silent=True) or {}
    title = (data.get("title") or "").strip()
    if not title:
        return _err("title is required", 400)
    tags = [t.strip() for t in (data.get("tags") or "").split(",") if t.strip()]
    folder_id = _resolve_folder_id_for_user(data.get("folder_id"), g.user_id)
    editor_type_raw = (data.get("editor_type") or "lexical").strip().lower()
    editor_type = "lexical" if editor_type_raw in ("tui", "lexical") else "lexical"
    original_extension = (data.get("original_extension") or "").strip() or None
    note_id = create_note(
        g.user_id,
        title=title,
        content=data.get("content") or "",
        folder_id=folder_id,
        is_favorite=bool(data.get("is_favorite")),
        tag_names=tags or None,
        editor_type=editor_type,
        original_extension=original_extension,
    )
    _sync_log.info("WEB note created  user_id=%s note_id=%s title=%r", g.user_id, note_id, title)
    return _ok({"id": note_id}, 201)


@api_bp.route("/notes/<int:note_id>", methods=["PUT"])
@require_auth
def put_note(note_id):
    data = request.get_json(silent=True) or {}
    tags_raw = data.get("tags")
    tag_names = None
    if tags_raw is not None:
        tag_names = [t.strip() for t in str(tags_raw).split(",") if t.strip()]
    folder_id = data.get("folder_id")
    if "folder_id" in data:
        folder_id = _resolve_folder_id_for_user(folder_id, g.user_id)
    editor_type = None
    if "editor_type" in data:
        raw_et = (data.get("editor_type") or "").strip().lower()
        editor_type = "lexical" if raw_et in ("tui", "lexical") else None
    original_extension = None
    if "original_extension" in data:
        original_extension = (data.get("original_extension") or "").strip() or None
    ok = update_note(
        g.user_id, note_id,
        title=data.get("title"),
        content=data.get("content"),
        folder_id=folder_id,
        is_favorite=data.get("is_favorite"),
        tag_names=tag_names,
        editor_type=editor_type,
        original_extension=original_extension,
    )
    if not ok:
        return _err("Not found", 404)
    _sync_log.info("WEB note updated  user_id=%s note_id=%s", g.user_id, note_id)
    return _ok()


@api_bp.route("/notes/<int:note_id>", methods=["DELETE"])
@require_auth
def del_note(note_id):
    ok = delete_note(g.user_id, note_id)
    if not ok:
        return _err("Not found", 404)
    return _ok()


# ── Sync ──────────────────────────────────────────────────────────────────────
#
# Protocol:
#   Push:  Desktop sends a batch of changed notes with their sync_id and
#          local base server revision. Server applies updates only when
#          base revision matches current revision.
#   Pull:  Desktop sends its last seen server revision and receives notes
#          newer than that revision (excluding notes still in conflict).
# ─────────────────────────────────────────────────────────────────────────────

@api_bp.route("/sync/push-folders", methods=["POST"])
@require_auth
def sync_push_folders():
    """
    Body: { "folders": [ { sync_id, name, color } ] }
    Response: { "results": [ { sync_id, status, server_id } ] }
    """
    data = request.get_json(silent=True) or {}
    folders = data.get("folders") or []
    if not isinstance(folders, list):
        return _err("folders must be an array", 400)

    idem_key, corr_id = _sync_request_ids()
    replay = _idempotency_replay(g.user_id, idem_key)
    if replay is not None:
        _sync_log.info("SYNC push-folders replay  user_id=%s corr=%s idem=%s", g.user_id, corr_id, idem_key)
        return replay

    results = []
    for item in folders:
        sync_id = (item.get("sync_id") or "").strip()
        name = (item.get("name") or "").strip()
        if not sync_id or not name:
            continue
        color = item.get("color") or None
        parent_sync_id = item.get("parent_sync_id") or None
        try:
            server_id = upsert_folder_by_sync_id(g.user_id, sync_id, name, color, parent_sync_id)
            results.append({"sync_id": sync_id, "status": "ok", "server_id": server_id})
        except Exception as exc:
            results.append({"sync_id": sync_id, "status": "error", "error": str(exc)})

    payload = {"results": results}
    _idempotency_store(g.user_id, idem_key, payload)
    _sync_log.info("SYNC push-folders  user_id=%s count=%s corr=%s idem=%s", g.user_id, len(results), corr_id, idem_key)
    return _ok(payload)


@api_bp.route("/sync/push-folder-tombstones", methods=["POST"])
@require_auth
def sync_push_folder_tombstones():
    idem_key, corr_id = _sync_request_ids()
    replay = _idempotency_replay(g.user_id, idem_key)
    if replay is not None:
        _sync_log.info("SYNC push-folder-tombstones replay  user_id=%s corr=%s idem=%s", g.user_id, corr_id, idem_key)
        return replay

    data = request.get_json(silent=True) or {}
    tombstones = data.get("tombstones") or []
    if not isinstance(tombstones, list):
        return _err("tombstones must be an array", 400)

    results = []
    for item in tombstones:
        sync_id = (item.get("sync_id") or "").strip()
        if not sync_id:
            continue
        try:
            applied = apply_folder_tombstone(g.user_id, sync_id)
            results.append({"sync_id": sync_id, "status": "deleted" if applied else "already_deleted"})
        except Exception as exc:
            results.append({"sync_id": sync_id, "status": "error", "error": str(exc)})

    payload = {"results": results}
    _idempotency_store(g.user_id, idem_key, payload)
    _sync_log.info("SYNC push-folder-tombstones  user_id=%s count=%s corr=%s idem=%s", g.user_id, len(results), corr_id, idem_key)
    return _ok(payload)


@api_bp.route("/sync/push-tags", methods=["POST"])
@require_auth
def sync_push_tags():
    """
    Body: { "tags": [ { sync_id, name, color } ] }
    Response: { "results": [ { sync_id, status, server_id } ] }
    """
    idem_key, corr_id = _sync_request_ids()
    replay = _idempotency_replay(g.user_id, idem_key)
    if replay is not None:
        _sync_log.info("SYNC push-tags replay  user_id=%s corr=%s idem=%s", g.user_id, corr_id, idem_key)
        return replay

    data = request.get_json(silent=True) or {}
    tags = data.get("tags") or []
    if not isinstance(tags, list):
        return _err("tags must be an array", 400)

    results = []
    for item in tags:
        sync_id = (item.get("sync_id") or "").strip()
        name = (item.get("name") or "").strip().lower().lstrip("#")
        if not sync_id or not name:
            continue
        color = item.get("color") or None
        try:
            tag_id = upsert_tag_by_sync_id(g.user_id, sync_id, name, color)
            results.append({"sync_id": sync_id, "status": "ok", "server_id": tag_id})
        except Exception as exc:
            results.append({"sync_id": sync_id, "status": "error", "error": str(exc)})

    payload = {"results": results}
    _idempotency_store(g.user_id, idem_key, payload)
    _sync_log.info("SYNC push-tags  user_id=%s count=%s corr=%s idem=%s", g.user_id, len(results), corr_id, idem_key)
    return _ok(payload)


@api_bp.route("/sync/push-tag-tombstones", methods=["POST"])
@require_auth
def sync_push_tag_tombstones():
    idem_key, corr_id = _sync_request_ids()
    replay = _idempotency_replay(g.user_id, idem_key)
    if replay is not None:
        _sync_log.info("SYNC push-tag-tombstones replay  user_id=%s corr=%s idem=%s", g.user_id, corr_id, idem_key)
        return replay

    data = request.get_json(silent=True) or {}
    tombstones = data.get("tombstones") or []
    if not isinstance(tombstones, list):
        return _err("tombstones must be an array", 400)

    results = []
    for item in tombstones:
        sync_id = (item.get("sync_id") or "").strip()
        if not sync_id:
            continue
        try:
            applied = apply_tag_tombstone(g.user_id, sync_id)
            results.append({"sync_id": sync_id, "status": "deleted" if applied else "already_deleted"})
        except Exception as exc:
            results.append({"sync_id": sync_id, "status": "error", "error": str(exc)})

    payload = {"results": results}
    _idempotency_store(g.user_id, idem_key, payload)
    _sync_log.info("SYNC push-tag-tombstones  user_id=%s count=%s corr=%s idem=%s", g.user_id, len(results), corr_id, idem_key)
    return _ok(payload)


@api_bp.route("/sync/push-note-tombstones", methods=["POST"])
@require_auth
def sync_push_note_tombstones():
    idem_key, corr_id = _sync_request_ids()
    replay = _idempotency_replay(g.user_id, idem_key)
    if replay is not None:
        _sync_log.info("SYNC push-note-tombstones replay  user_id=%s corr=%s idem=%s", g.user_id, corr_id, idem_key)
        return replay

    data = request.get_json(silent=True) or {}
    tombstones = data.get("tombstones") or []
    if not isinstance(tombstones, list):
        return _err("tombstones must be an array", 400)

    results = []
    for item in tombstones:
        sync_id = (item.get("sync_id") or "").strip()
        if not sync_id:
            continue
        try:
            applied = apply_note_tombstone(g.user_id, sync_id)
            results.append({"sync_id": sync_id, "status": "deleted" if applied else "already_deleted"})
        except Exception as exc:
            results.append({"sync_id": sync_id, "status": "error", "error": str(exc)})

    payload = {"results": results}
    _idempotency_store(g.user_id, idem_key, payload)
    _sync_log.info("SYNC push-note-tombstones  user_id=%s count=%s corr=%s idem=%s", g.user_id, len(results), corr_id, idem_key)
    return _ok(payload)


@api_bp.route("/sync/push", methods=["POST"])
@require_auth
def sync_push():
    """
    Body: { "notes": [ { sync_id, title, content, updated_at,
                          folder_id?, is_favorite?, tags? } ] }
    Response: { "results": [ { sync_id, status, server_id?, conflict_id? } ] }
    """
    idem_key, corr_id = _sync_request_ids()
    replay = _idempotency_replay(g.user_id, idem_key)
    if replay is not None:
        _sync_log.info("SYNC push-notes replay  user_id=%s corr=%s idem=%s", g.user_id, corr_id, idem_key)
        return replay

    data = request.get_json(silent=True) or {}
    incoming = data.get("notes") or []
    if not isinstance(incoming, list):
        return _err("notes must be an array", 400)

    conn = get_connection()
    results = []

    for item in incoming:
        sync_id = (item.get("sync_id") or "").strip()
        if not sync_id:
            continue
        try:
            _process_sync_note(conn, g.user_id, sync_id, item, results, corr_id)
        except Exception as exc:
            # Roll back any partial work for this note and continue with the next
            try:
                conn.rollback()
            except Exception:
                pass
            _sync_log.exception(
                "SYNC push-note error user_id=%s sync_id=%s corr=%s idem=%s",
                g.user_id,
                sync_id,
                corr_id,
                idem_key,
            )
            results.append({"sync_id": sync_id, "status": "error", "error": str(exc)})

    conn.close()
    payload = {"results": results}
    _idempotency_store(g.user_id, idem_key, payload)
    _sync_log.info("SYNC push-notes  user_id=%s count=%s corr=%s idem=%s", g.user_id, len(results), corr_id, idem_key)
    return _ok(payload)


def _process_sync_note(conn, user_id: int, sync_id: str, item: dict, results: list, corr_id: str) -> None:
    """Insert or update a single note from a sync push. Mutates *results*."""
    title = (item.get("title") or "Untitled").strip()
    content = item.get("content") or ""
    client_updated_at = _normalize_client_timestamp(item.get("updated_at"))
    base_server_rev = _parse_sync_rev(item.get("server_rev"))
    is_favorite = int(bool(item.get("is_favorite")))
    tags_raw = item.get("tags") or ""
    tag_names = [t.strip() for t in tags_raw.split(",") if t.strip()]
    tag_sync_ids_raw = item.get("tag_sync_ids") or ""
    tag_sync_ids = [s.strip() for s in str(tag_sync_ids_raw).split(",") if s.strip()]

    # Resolve folder: prefer folder_sync_id (UUID-based), fall back to folder_id
    # with server-side validation (local integer IDs won't match server IDs).
    folder_id = None
    folder_sync_id = (item.get("folder_sync_id") or "").strip()
    if folder_sync_id:
        folder_row = conn.execute(
            "SELECT id FROM folders WHERE sync_id=? AND user_id=?",
            (folder_sync_id, user_id),
        ).fetchone()
        if folder_row:
            folder_id = int(folder_row["id"])
    else:
        raw_fid = item.get("folder_id") or None
        if raw_fid is not None:
            exists = conn.execute(
                "SELECT 1 FROM folders WHERE id=? AND user_id=?", (raw_fid, user_id)
            ).fetchone()
            if exists:
                folder_id = raw_fid

    existing = conn.execute(
        "SELECT * FROM notes WHERE sync_id=? AND user_id=?",
        (sync_id, user_id),
    ).fetchone()

    if existing is None:
        # New note from desktop — insert
        server_rev = allocate_server_rev(conn)
        conn.execute(
            """INSERT INTO notes
               (user_id, folder_id, title, content, is_favorite, sync_id, client_updated_at, server_rev)
               VALUES (?,?,?,?,?,?,?,?)""",
            (user_id, folder_id, title, content, is_favorite,
             sync_id, client_updated_at, server_rev),
        )
        conn.execute(
            "DELETE FROM note_tombstones WHERE user_id=? AND sync_id=?",
            (user_id, sync_id),
        )
        note_id = _get_last_insert_id(conn)
        if tag_sync_ids:
            for tag_sync_id in tag_sync_ids:
                row = conn.execute(
                    "SELECT id FROM tags WHERE user_id=? AND sync_id=?",
                    (user_id, tag_sync_id),
                ).fetchone()
                if row:
                    conn.execute(
                        "INSERT OR IGNORE INTO note_tags (note_id, tag_id) VALUES (?,?)",
                        (note_id, int(row["id"])),
                    )
        else:
            for tag_name in tag_names:
                tag_name = tag_name.strip().lower().lstrip("#")
                if not tag_name:
                    continue
                tag_id = _ensure_tag(conn, user_id, tag_name)
                conn.execute(
                    "INSERT OR IGNORE INTO note_tags (note_id, tag_id) VALUES (?,?)",
                    (note_id, tag_id),
                )
        conn.commit()
        results.append({
            "sync_id": sync_id,
            "status": "created",
            "server_id": note_id,
            "server_rev": server_rev,
        })
        _sync_log.info(
            "SYNC push-note created user_id=%s sync_id=%s server_id=%s server_rev=%s corr=%s",
            user_id,
            sync_id,
            note_id,
            server_rev,
            corr_id,
        )

    else:
        note_id = int(existing["id"])
        current_server_rev = int(existing["server_rev"] or 0)

        # Compare-and-swap guard: only accept push if desktop edits are based
        # on the current server revision.
        if base_server_rev is None or base_server_rev != current_server_rev:
            results.append({
                "sync_id": sync_id,
                "status": "remote_newer",
                "server_id": note_id,
                "server_rev": current_server_rev,
            })
            _sync_log.info(
                "SYNC push-note remote_newer user_id=%s sync_id=%s server_id=%s server_rev=%s corr=%s",
                user_id,
                sync_id,
                note_id,
                current_server_rev,
                corr_id,
            )
            return

        next_server_rev = allocate_server_rev(conn)
        conn.execute(
            """UPDATE notes
               SET title=?, content=?, is_favorite=?,
                   updated_at=datetime('now'), client_updated_at=?,
                   folder_id=?, server_rev=?
               WHERE id=? AND user_id=?""",
            (
                title,
                content,
                is_favorite,
                client_updated_at,
                folder_id,
                next_server_rev,
                note_id,
                user_id,
            ),
        )
        conn.execute(
            "DELETE FROM note_tombstones WHERE user_id=? AND sync_id=?",
            (user_id, sync_id),
        )
        conn.execute("DELETE FROM note_tags WHERE note_id=?", (note_id,))
        if tag_sync_ids:
            for tag_sync_id in tag_sync_ids:
                row = conn.execute(
                    "SELECT id FROM tags WHERE user_id=? AND sync_id=?",
                    (user_id, tag_sync_id),
                ).fetchone()
                if row:
                    conn.execute(
                        "INSERT OR IGNORE INTO note_tags (note_id, tag_id) VALUES (?,?)",
                        (note_id, int(row["id"])),
                    )
        else:
            for tag_name in tag_names:
                tag_name = tag_name.strip().lower().lstrip("#")
                if not tag_name:
                    continue
                tag_id = _ensure_tag(conn, user_id, tag_name)
                conn.execute(
                    "INSERT OR IGNORE INTO note_tags (note_id, tag_id) VALUES (?,?)",
                    (note_id, tag_id),
                )
        conn.commit()
        results.append({
            "sync_id": sync_id,
            "status": "updated",
            "server_id": note_id,
            "server_rev": next_server_rev,
        })
        _sync_log.info(
            "SYNC push-note updated user_id=%s sync_id=%s server_id=%s server_rev=%s corr=%s",
            user_id,
            sync_id,
            note_id,
            next_server_rev,
            corr_id,
        )



@api_bp.route("/sync/pull", methods=["GET"])
@require_auth
def sync_pull():
    """
    ?since_rev=<int>
    Returns notes newer than since_rev, excluding any with open conflicts.
    """
    idem_key, corr_id = _sync_request_ids()
    replay = _idempotency_replay(g.user_id, idem_key)
    if replay is not None:
        _sync_log.info("SYNC pull replay  user_id=%s corr=%s idem=%s", g.user_id, corr_id, idem_key)
        return replay

    since_rev = request.args.get("since_rev", default=0, type=int)
    since_rev = max(int(since_rev or 0), 0)
    notes = get_notes_since(g.user_id, since_rev)

    # Exclude notes that have open conflicts
    conn = get_connection()
    conflict_note_ids = {
        int(r["note_id"])
        for r in conn.execute(
            "SELECT note_id FROM conflicts WHERE user_id=? AND resolved=0 AND note_id IS NOT NULL",
            (g.user_id,),
        ).fetchall()
    }
    conn.close()

    clean = [n for n in notes if n["id"] not in conflict_note_ids]
    max_server_rev = get_user_max_server_rev(g.user_id)
    next_since_rev = max(since_rev, max_server_rev)
    folder_tombstones = get_folder_tombstones_since(g.user_id, since_rev)
    tag_tombstones = get_tag_tombstones_since(g.user_id, since_rev)
    note_tombstones = get_note_tombstones_since(g.user_id, since_rev)
    raw_folders = get_all_folders(g.user_id)
    folder_sync_by_id = {int(folder["id"]): folder.get("sync_id") for folder in raw_folders}
    folders = [
        {
            **folder,
            "parent_sync_id": folder_sync_by_id.get(folder.get("parent_id")) if folder.get("parent_id") else None,
        }
        for folder in raw_folders
    ]
    tags = get_all_tags(g.user_id)
    _sync_log.info(
        "SYNC pull  user_id=%s since_rev=%s folders=%s tags=%s notes=%s folder_tombstones=%s tag_tombstones=%s note_tombstones=%s next_since_rev=%s corr=%s idem=%s",
        g.user_id,
        since_rev,
        len(folders),
        len(tags),
        len(clean),
        len(folder_tombstones),
        len(tag_tombstones),
        len(note_tombstones),
        next_since_rev,
        corr_id,
        idem_key,
    )
    payload = {
        "notes": clean,
        "folders": folders,
        "tags": tags,
        "folder_tombstones": folder_tombstones,
        "tag_tombstones": tag_tombstones,
        "note_tombstones": note_tombstones,
        "since_rev": next_since_rev,
    }
    _idempotency_store(g.user_id, idem_key, payload)
    _sync_log.info("SYNC pull trace user_id=%s corr=%s idem=%s", g.user_id, corr_id, idem_key)
    return _ok(payload)


@api_bp.route("/sync/conflicts", methods=["GET"])
@require_auth
def list_conflicts():
    return _ok(get_unresolved_conflicts(g.user_id))


@api_bp.route("/sync/conflicts/<int:conflict_id>/resolve", methods=["POST"])
@require_auth
def resolve_conflict_route(conflict_id):
    """
    Body: { "title": "...", "content": "...", "choice": "server"|"client"|"custom" }
    """
    data = request.get_json(silent=True) or {}
    choice = data.get("choice", "custom")

    if choice == "server":
        conn = get_connection()
        conflict = conn.execute(
            "SELECT * FROM conflicts WHERE id=? AND user_id=? AND resolved=0",
            (conflict_id, g.user_id),
        ).fetchone()
        conn.close()
        if not conflict:
            return _err("Not found", 404)
        title = conflict["server_title"]
        content = conflict["server_content"]
    elif choice == "client":
        conn = get_connection()
        conflict = conn.execute(
            "SELECT * FROM conflicts WHERE id=? AND user_id=? AND resolved=0",
            (conflict_id, g.user_id),
        ).fetchone()
        conn.close()
        if not conflict:
            return _err("Not found", 404)
        title = conflict["client_title"]
        content = conflict["client_content"]
    else:
        title = (data.get("title") or "").strip()
        content = data.get("content") or ""
        if not title:
            return _err("title is required for custom resolution", 400)

    ok = resolve_conflict(g.user_id, conflict_id, title, content)
    if not ok:
        return _err("Not found or already resolved", 404)
    return _ok({"resolved": True})


# ─── Backup export / import ──────────────────────────────────────────────────

@api_bp.route("/backup/export", methods=["GET"])
@require_auth
def export_backup():
    """Export user's notes, folders, tags as JSONL download."""
    lines = export_user_backup(g.user_id)
    content = "\n".join(lines)
    
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    filename = f"NoteStack_backup_{timestamp}.jsonl"
    
    return send_file(
        io.BytesIO(content.encode("utf-8")),
        mimetype="application/x-jsonlines",
        as_attachment=True,
        download_name=filename,
    )


@api_bp.route("/backup/import", methods=["POST"])
@require_auth
def import_backup():
    """Import a JSONL backup file into user's library.
    
    Expects multipart/form-data with 'file' field containing the .jsonl file.
    Returns import stats: {folders_created, tags_created, notes_added, notes_updated}.
    """
    if "file" not in request.files:
        return _err("No file provided", 400)
    
    file = request.files["file"]
    if not file or file.filename == "":
        return _err("No file selected", 400)
    
    try:
        content = file.read().decode("utf-8")
        lines = content.splitlines()
        stats = import_user_backup(g.user_id, lines)
        return _ok(stats)
    except Exception as e:
        _sync_log.error("Import error: %s", str(e))
        return _err(f"Import failed: {str(e)}", 400)


@api_bp.route("/data/delete-all", methods=["POST"])
@require_auth
def delete_all_data():
    """Permanently delete all of the authenticated user's NoteStack content."""
    stats = delete_all_user_data(g.user_id)
    return _ok({"deleted": True, "stats": stats})
