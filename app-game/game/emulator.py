import os
import sqlite3
import uuid
from typing import Optional

from flask import (
    Blueprint,
    abort,
    current_app,
    jsonify,
    redirect,
    render_template,
    request,
    send_file,
    url_for,
)

from .auth import _get_user_id, login_required

emulator_bp = Blueprint("emulator", __name__, url_prefix="/game/emulator")

_ALLOWED_EXTENSIONS = {
    ".gba": "gba",
    ".gb": "gb",
    ".gbc": "gb",
    ".nes": "nes",
    ".smc": "snes",
    ".sfc": "snes",
    ".md": "segaMD",
    ".genesis": "segaMD",
    ".sms": "segaMS",
    ".gg": "segaGG",
    ".32x": "sega32x",
}

_CONTENT_TYPES = {
    ".gba": "application/octet-stream",
    ".gb": "application/octet-stream",
    ".gbc": "application/octet-stream",
    ".nes": "application/octet-stream",
    ".smc": "application/octet-stream",
    ".sfc": "application/octet-stream",
    ".md": "application/octet-stream",
    ".genesis": "application/octet-stream",
    ".sms": "application/octet-stream",
    ".gg": "application/octet-stream",
    ".32x": "application/octet-stream",
}


def _db_path() -> str:
    return current_app.config["EMULATOR_DB_PATH"]


def _get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(_db_path(), timeout=30, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    conn = _get_conn()
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS roms (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                system TEXT NOT NULL,
                stored_name TEXT NOT NULL,
                original_name TEXT NOT NULL,
                size INTEGER NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_roms_user ON roms(user_id)")
        conn.commit()
    finally:
        conn.close()


def _core_for_ext(ext: str) -> str:
    return _ALLOWED_EXTENSIONS.get(ext, "gba")


def _is_admin(user_id: str) -> bool:
    return user_id in current_app.config.get("GAME_ADMIN_USER_IDS", [])


def _get_rom(rom_id) -> Optional[dict]:
    try:
        rom_id = int(rom_id)
    except (TypeError, ValueError):
        return None
    conn = _get_conn()
    try:
        row = conn.execute("SELECT * FROM roms WHERE id = ?", (rom_id,)).fetchone()
    finally:
        conn.close()
    if row is None:
        return None
    return dict(row)


def _owned_or_admin(rom: dict, user_id: str) -> bool:
    return rom["user_id"] == user_id or _is_admin(user_id)


def _usage_for_user(user_id: str) -> tuple[int, int]:
    conn = _get_conn()
    try:
        row = conn.execute(
            "SELECT COUNT(*) AS cnt, COALESCE(SUM(size), 0) AS total FROM roms WHERE user_id = ?",
            (user_id,),
        ).fetchone()
    finally:
        conn.close()
    return int(row["cnt"]), int(row["total"])


def _rom_file_path(rom: dict) -> str:
    upload_dir = current_app.config["EMULATOR_UPLOAD_DIR"]
    return os.path.join(upload_dir, rom["user_id"], rom["stored_name"])


@emulator_bp.route("/")
@login_required
def index():
    user_id = _get_user_id()
    conn = _get_conn()
    try:
        rows = conn.execute(
            "SELECT id, system, original_name, size, created_at FROM roms WHERE user_id = ? ORDER BY created_at DESC",
            (user_id,),
        ).fetchall()
    finally:
        conn.close()
    roms = [dict(r) for r in rows]
    return render_template("emulator_list.html", roms=roms)


@emulator_bp.route("/upload", methods=["POST"])
@login_required
def upload():
    user_id = _get_user_id()

    if not request.files:
        return jsonify({"error": "No file provided."}), 400
    file = request.files.get("rom")
    if file is None or not file.filename:
        return jsonify({"error": "No file provided."}), 400

    if not request.form.get("rights_confirm"):
        return jsonify({"error": "You must confirm you have the rights to upload this ROM."}), 400

    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in _ALLOWED_EXTENSIONS:
        return jsonify({"error": f"Unsupported file type: {ext}"}), 400

    count, total = _usage_for_user(user_id)
    max_roms = current_app.config["EMULATOR_MAX_ROMS"]
    max_storage = current_app.config["EMULATOR_MAX_STORAGE_BYTES"]
    file.seek(0, os.SEEK_END)
    size = file.tell()
    file.seek(0)

    if count >= max_roms:
        return jsonify({"error": f"You have reached the limit of {max_roms} ROMs."}), 400
    if total + size > max_storage:
        return jsonify({"error": "Upload would exceed your storage quota."}), 400

    stored_name = f"{uuid.uuid4().hex}{ext}"
    user_dir = os.path.join(current_app.config["EMULATOR_UPLOAD_DIR"], user_id)
    os.makedirs(user_dir, exist_ok=True)
    dest = os.path.join(user_dir, stored_name)
    file.save(dest)

    from datetime import datetime, timezone

    created_at = datetime.now(timezone.utc).isoformat()
    conn = _get_conn()
    try:
        conn.execute(
            "INSERT INTO roms (user_id, system, stored_name, original_name, size, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (user_id, _core_for_ext(ext), stored_name, file.filename, size, created_at),
        )
        conn.commit()
    finally:
        conn.close()

    return redirect(url_for("emulator.index"))


@emulator_bp.route("/play/<rom_id>")
@login_required
def play(rom_id):
    user_id = _get_user_id()
    rom = _get_rom(rom_id)
    if rom is None or not _owned_or_admin(rom, user_id):
        abort(404)
    return render_template(
        "emulator_play.html",
        rom_id=rom["id"],
        rom_name=rom["original_name"],
        core=rom["system"],
        game_url=url_for("emulator.rom_file", rom_id=rom["id"]),
    )


@emulator_bp.route("/rom/<rom_id>")
@login_required
def rom_file(rom_id):
    user_id = _get_user_id()
    rom = _get_rom(rom_id)
    if rom is None or not _owned_or_admin(rom, user_id):
        abort(404)
    path = _rom_file_path(rom)
    if not os.path.isfile(path):
        abort(404)
    ext = os.path.splitext(rom["stored_name"])[1].lower()
    content_type = _CONTENT_TYPES.get(ext, "application/octet-stream")
    return send_file(path, mimetype=content_type, conditional=True)


@emulator_bp.route("/delete/<rom_id>", methods=["POST"])
@login_required
def delete(rom_id):
    user_id = _get_user_id()
    rom = _get_rom(rom_id)
    if rom is None or not _owned_or_admin(rom, user_id):
        abort(404)
    path = _rom_file_path(rom)
    if os.path.isfile(path):
        try:
            os.remove(path)
        except OSError:
            pass
    conn = _get_conn()
    try:
        conn.execute("DELETE FROM roms WHERE id = ?", (rom["id"],))
        conn.commit()
    finally:
        conn.close()
    return redirect(url_for("emulator.index"))
