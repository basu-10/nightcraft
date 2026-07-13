from __future__ import annotations

import json
import os
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import pandas as pd
from flask import Flask, jsonify, redirect, render_template, request, url_for
from werkzeug.middleware.proxy_fix import ProxyFix
from werkzeug.utils import secure_filename

# Engine mapping for initial conversion
ENGINE_FOR_SUFFIX = {
    ".xlsx": "openpyxl",
    ".xlsm": "openpyxl",
    ".xls": "xlrd",
    ".xlsb": "pyxlsb",
    ".csv": None,
}

# Configuration
# Runtime data (uploads + SQLite) lives outside the source checkout by default,
# mirroring the rest of the Nightcraft stack. Override via env if needed.
# TINYXL_UPLOAD_DIR and TINYXL_DB_DIR are DIRECTORIES; the SQLite filename is
# appended to the DB directory.
UPLOAD_FOLDER = Path(os.environ.get("TINYXL_UPLOAD_DIR", str(Path(__file__).parent / "uploads")))
DB_DIR = Path(os.environ.get("TINYXL_DB_DIR", str(Path(__file__).parent / "db")))
DB_PATH = DB_DIR / "excel_reader_state.sqlite3"
ALLOWED_EXTENSIONS = {".xlsx", ".xls", ".xlsb", ".xlsm", ".csv", ".txl"}

app = Flask(__name__)
app.config["UPLOAD_FOLDER"] = str(UPLOAD_FOLDER)

# Respect X-Forwarded-Prefix so the app can be served under a subpath
# (e.g. /tinyxl) behind Nginx, matching the rest of the Nightcraft stack.
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)


class PrefixStripper:
    """Strip a forwarded mount prefix from PATH_INFO.

    ProxyFix sets SCRIPT_NAME from X-Forwarded-Prefix but does NOT rewrite
    PATH_INFO. If a proxy forwards the full subpath (e.g. /tinyxl/api/upload)
    without stripping it, Flask would route against the prefixed path and 404.
    This wrapper removes the prefix from PATH_INFO so routing matches whether
    or not the upstream proxy strips the prefix.
    """

    def __init__(self, app):
        self.app = app

    def __call__(self, environ, start_response):
        prefix = (environ.get("HTTP_X_FORWARDED_PREFIX") or "").split(",")[0].strip()
        if prefix and environ.get("PATH_INFO", "").startswith(prefix):
            environ["PATH_INFO"] = environ["PATH_INFO"][len(prefix):] or "/"
            environ["SCRIPT_NAME"] = prefix
        return self.app(environ, start_response)


app.wsgi_app = PrefixStripper(app.wsgi_app)

# Ensure directories exist
UPLOAD_FOLDER.mkdir(parents=True, exist_ok=True)
DB_PATH.parent.mkdir(parents=True, exist_ok=True)


# ─────────────────────────────────────────────
# TXL Helpers — all state lives in .txl files
# ─────────────────────────────────────────────

TXL_VERSION = "1.0"


def _ensure_txl_path(file_path: Path) -> Path:
    """If the path ends in .xlsx/.csv/etc., swap to .txl extension.
    Used for back-compat in case old .xlsx files remain in uploads/."""
    if file_path.suffix.lower() == ".txl":
        return file_path
    return file_path.with_suffix(".txl")


def load_txl(file_path: Path) -> dict:
    """Load a .txl file and return the full parsed JSON."""
    txl_path = _ensure_txl_path(file_path)
    with open(txl_path, "r", encoding="utf-8") as f:
        return json.load(f)


_txl_write_lock = {}  # per-file lock to prevent concurrent write corruption


def save_txl(file_path: Path, txl_data: dict):
    """Write the full txl_data dict back to the .txl file (atomic write)."""
    txl_path = _ensure_txl_path(file_path)
    txl_data["exported_at"] = datetime.now(timezone.utc).isoformat()

    # Per-file locking to prevent concurrent read-modify-write races
    lock_key = str(txl_path.resolve())
    lock = _txl_write_lock.setdefault(lock_key, __import__("threading").Lock())
    lock.acquire()
    try:
        # Atomic write: write to temp file, then rename over target
        tmp_path = txl_path.with_suffix(".txl.tmp")
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(txl_data, f, indent=2)
            f.flush()
            os.fsync(f.fileno())
        tmp_path.replace(txl_path)
    finally:
        lock.release()
    # Clean up stale lock if map grows too large
    if len(_txl_write_lock) > 100:
        _txl_write_lock.clear()


def get_txl_sheets(txl_data: dict) -> list:
    """Return list of sheet dicts from a txl file."""
    return txl_data.get("file", {}).get("sheets", [])


def get_txl_sheet(txl_data: dict, sheet_name: str) -> Optional[dict]:
    """Return the sheet dict for a given sheet name, or None."""
    for s in get_txl_sheets(txl_data):
        if s["name"] == sheet_name:
            return s
    return None


def get_txl_sheet_names(txl_data: dict) -> list:
    """Return list of sheet names."""
    return [s["name"] for s in get_txl_sheets(txl_data)]


def get_txl_linked_sheets(txl_data: dict) -> list:
    """Return the linked_sheets list from a txl file (file-level, for backward compatibility)."""
    return txl_data.get("file", {}).get("linked_sheets", [])


def get_txl_sheet_linked_sheets(txl_data: dict, sheet_name: str) -> list:
    """Return linked_sheets for a specific sheet."""
    sheet = get_txl_sheet(txl_data, sheet_name)
    if sheet:
        linked = sheet.get("linked_sheets")
        return linked if isinstance(linked, list) else []
    return []


def get_txl_file_id(txl_data: dict) -> str:
    """Return the file_id stored in the txl file."""
    return txl_data.get("file", {}).get("file_id")


def set_txl_file_id(txl_data: dict, file_id: str):
    txl_data.setdefault("file", {})["file_id"] = file_id


def get_txl_original_name(txl_data: dict) -> str:
    return txl_data.get("file", {}).get("original_name", "Untitled.txl")


def _convert_to_txl_from_path(file_path: Path, original_name: str = None) -> Path:
    """Convert an xlsx/csv/xls/xlsb file to .txl format in place.
    Returns the path to the new .txl file (old file is removed)."""
    if file_path.suffix.lower() == ".txl":
        return file_path  # already native

    suffix = file_path.suffix.lower()
    engine = ENGINE_FOR_SUFFIX.get(suffix)
    if suffix == ".csv":
        frame = pd.read_csv(file_path, dtype=str, header=None)
        sheets_data = [{file_path.stem: frame}]
    else:
        excel_file = pd.ExcelFile(file_path, engine=engine)
        sheets_data = []
        for name in excel_file.sheet_names:
            df = pd.read_excel(file_path, sheet_name=name, engine=engine, dtype=str, header=None)
            sheets_data.append({name: df})

    # Build TXL structure
    sheets = []
    for sd in sheets_data:
        for sname, df in sd.items():
            df = df.fillna("")
            data = df.values.tolist()
            rows = df.shape[0]
            cols = df.shape[1]
            if rows < 1:
                rows = 1
                data = [[""] * max(1, cols)]
            if cols < 1:
                cols = 1
                for row in data:
                    while len(row) < cols:
                        row.append("")

            sheets.append({
                "name": sname,
                "data": data,
                "rows": rows,
                "cols": cols,
                "layout": {
                    "column_widths": {},
                    "row_heights": {},
                    "sticky_row": None,
                    "alternate_row_colors": False,
                    "cell_colors": {},
                    "header_rows": [],
                    "columnTypes": {},
                    "data_rows": rows,
                    "data_cols": cols
                },
                "linked_sheets": []
            })

    # Generate file_id (deterministic from original absolute path so re-imports match)
    # Use the original file path for UUID v5 to keep stability
    orig_path_for_id = file_path.resolve()
    file_id = str(uuid.uuid5(uuid.NAMESPACE_URL, str(orig_path_for_id)))

    payload = {
        "version": TXL_VERSION,
        "app": "TinyXL",
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "file": {
            "original_name": original_name or file_path.name,
            "file_id": file_id,
            "sheets": sheets,
            "linked_sheets": []
        }
    }

    # Save as .txl, remove the original
    txl_path = file_path.with_suffix(".txl")
    with open(txl_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
    # Remove the old format file
    try:
        file_path.unlink()
    except Exception:
        pass

    return txl_path

# ─────────────────────────────────────────────
# SQLite helpers — only for recent_files + settings
# ─────────────────────────────────────────────

def get_db():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False, timeout=30.0)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with get_db() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS recent_files (
                file_path TEXT PRIMARY KEY,
                last_opened_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS app_settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
            """
        )


init_db()


def allowed_file(filename):
    return Path(filename).suffix.lower() in ALLOWED_EXTENSIONS


# ─────────────────────────────────────────────
# Recent files (SQLite — app-level only)
# ─────────────────────────────────────────────

def touch_recent_file(file_path: str):
    with get_db() as conn:
        conn.execute(
            """
            INSERT INTO recent_files (file_path, last_opened_at)
            VALUES (?, ?)
            ON CONFLICT(file_path) DO UPDATE SET last_opened_at = excluded.last_opened_at
            """,
            (file_path, datetime.now(timezone.utc).isoformat()),
        )


def get_recent_files(limit: int = 12):
    with get_db() as conn:
        rows = conn.execute(
            "SELECT file_path FROM recent_files ORDER BY last_opened_at DESC LIMIT ?", (limit,)
        ).fetchall()
    return [row["file_path"] for row in rows]


def remove_recent_file(file_path: str):
    with get_db() as conn:
        conn.execute("DELETE FROM recent_files WHERE file_path = ?", (file_path,))


# ─────────────────────────────────────────────
# Shared helpers for reading/writing sheets
# ─────────────────────────────────────────────

def load_workbook_info(file_path: Path):
    """Get sheet names from a workbook (works for .txl and legacy formats)."""
    suffix = file_path.suffix.lower()
    if suffix == ".txl":
        txl = load_txl(file_path)
        return get_txl_sheet_names(txl)
    if suffix not in ENGINE_FOR_SUFFIX:
        raise ValueError(f"Unsupported file type: {suffix}")
    if suffix == ".csv":
        return [file_path.stem or "Sheet1"]
    engine = ENGINE_FOR_SUFFIX[suffix]
    excel_file = pd.ExcelFile(file_path, engine=engine)
    return list(excel_file.sheet_names)


def load_sheet_data(file_path: Path, sheet_name: str, expected_rows: int = 0, expected_cols: int = 0):
    """Load a sheet and return dict with data, rows, cols. Works for .txl and legacy formats."""
    suffix = file_path.suffix.lower()
    if suffix == ".txl":
        txl = load_txl(file_path)
        sheet = get_txl_sheet(txl, sheet_name)
        if sheet is None:
            raise ValueError(f"Sheet '{sheet_name}' not found in TXL file")
        data = sheet["data"]
        rows = len(data)
        cols = len(data[0]) if data else 0
        # Pad if expected size is larger
        if expected_rows > rows or expected_cols > cols:
            for r in range(len(data), max(expected_rows, rows)):
                data.append([""] * max(expected_cols, cols))
            for r in range(len(data)):
                while len(data[r]) < max(expected_cols, cols):
                    data[r].append("")
            rows = len(data)
            cols = len(data[0]) if data else 0
        # Minimum size
        if rows < 1:
            rows, cols = 1, max(1, cols)
            data = [[""] * cols]
        if cols < 1:
            cols = 1
            for row in data:
                while len(row) < cols:
                    row.append("")
        return {"name": sheet_name, "data": data, "rows": rows, "cols": cols}

    # Fallback: legacy format support (read via pandas)
    engine = ENGINE_FOR_SUFFIX.get(suffix)
    if suffix == ".csv":
        frame = pd.read_csv(file_path, dtype=str, header=None)
    else:
        frame = pd.read_excel(file_path, sheet_name=sheet_name, engine=engine, dtype=str, header=None)
    frame = frame.fillna("")
    if expected_rows > 0 and expected_cols > 0 and (frame.shape[0] < expected_rows or frame.shape[1] < expected_cols):
        new_frame = pd.DataFrame("", index=range(expected_rows), columns=range(expected_cols))
        if frame.shape[0] > 0 and frame.shape[1] > 0:
            new_frame.iloc[:frame.shape[0], :frame.shape[1]] = frame.values
        frame = new_frame
    # Ensure minimum size
    min_rows, min_cols = 1, 1
    if frame.shape[0] < min_rows or frame.shape[1] < min_cols:
        rows, cols = max(min_rows, frame.shape[0]), max(min_cols, frame.shape[1])
        new_frame = pd.DataFrame("", index=range(rows), columns=range(cols))
        if frame.shape[0] > 0 and frame.shape[1] > 0:
            new_frame.iloc[:frame.shape[0], :frame.shape[1]] = frame.values
        frame = new_frame
    return {
        "name": sheet_name,
        "data": frame.values.tolist(),
        "rows": frame.shape[0],
        "cols": frame.shape[1],
    }


def save_sheet_data(file_path: Path, sheet_name: str, data: list):
    """Save modified sheet data back to a .txl file."""
    _save_txl_sheet_data(file_path, sheet_name, data)


def _save_txl_sheet_data(file_path: Path, sheet_name: str, sheet_data: list):
    """Replace sheet data in a .txl file."""
    txl = load_txl(file_path)
    sheets = get_txl_sheets(txl)
    for s in sheets:
        if s["name"] == sheet_name:
            s["data"] = sheet_data
            s["rows"] = len(sheet_data)
            s["cols"] = len(sheet_data[0]) if sheet_data else 0
            # Update layout dimensions too
            layout = s.setdefault("layout", {})
            layout["data_rows"] = s["rows"]
            layout["data_cols"] = s["cols"]
            break
    else:
        # Create new sheet
        cols = len(sheet_data[0]) if sheet_data else 1
        new_sheet = {
            "name": sheet_name,
            "data": sheet_data,
            "rows": len(sheet_data),
            "cols": cols,
            "layout": {
                "column_widths": {},
                "row_heights": {},
                "sticky_row": None,
                "alternate_row_colors": False,
                "cell_colors": {},
                "header_rows": [],
                "columnTypes": {},
                "data_rows": len(sheet_data),
                "data_cols": cols
            },
            "linked_sheets": []
        }
        sheets.append(new_sheet)
    save_txl(file_path, txl)


def load_layout(file_path: Path, sheet_name: str) -> Optional[dict]:
    """Load layout state for a sheet from the .txl file."""
    suffix = file_path.suffix.lower()
    if suffix != ".txl":
        # Legacy format — return default
        return None
    try:
        txl = load_txl(file_path)
        sheet = get_txl_sheet(txl, sheet_name)
        if sheet is None:
            return None
        layout = sheet.get("layout")
        if layout is None:
            return None
        # Ensure all keys exist
        defaults = {
            "column_widths": {},
            "row_heights": {},
            "sticky_row": None,
            "alternate_row_colors": False,
            "cell_colors": {},
            "header_rows": [],
            "columnTypes": {},
            "data_rows": sheet.get("rows", 0),
            "data_cols": sheet.get("cols", 0),
        }
        for k, v in defaults.items():
            layout.setdefault(k, v)
        return layout
    except Exception:
        return None


def save_layout(file_path: Path, sheet_name: str, state: dict):
    """Save layout state to the .txl file."""
    suffix = file_path.suffix.lower()
    if suffix != ".txl":
        return  # Can't save layout to legacy formats
    try:
        txl = load_txl(file_path)
        sheets = get_txl_sheets(txl)
        for s in sheets:
            if s["name"] == sheet_name:
                # Merge with existing layout — keep cell colors and non-overwritten fields
                existing_layout = s.get("layout", {})
                for k, v in state.items():
                    existing_layout[k] = v
                s["layout"] = existing_layout
                break
        save_txl(file_path, txl)
    except Exception:
        pass  # Silently fail layout save


def get_txl_file_id_for_path(file_path: Path) -> str:
    """Return a stable file_id from the TXL file itself."""
    suffix = file_path.suffix.lower()
    if suffix == ".txl":
        try:
            txl = load_txl(file_path)
            fid = get_txl_file_id(txl)
            if fid:
                return fid
            # Generate one if missing
            fid = str(uuid.uuid5(uuid.NAMESPACE_URL, str(file_path.resolve())))
            set_txl_file_id(txl, fid)
            save_txl(file_path, txl)
            return fid
        except Exception:
            pass
    return str(uuid.uuid5(uuid.NAMESPACE_URL, str(file_path.resolve())))


# Routes
@app.route("/")
def landing():
    return render_template("landing.html")


@app.route("/app")
def app_redirect():
    return redirect(url_for("index_app"))


@app.route("/app/")
def index_app():
    return render_template("home.html")


@app.route("/file")
def file_view():
    return render_template("file.html")


@app.route("/api/upload", methods=["POST"])
def upload_file():
    if "file" not in request.files:
        return jsonify({"error": "No file provided"}), 400

    file = request.files["file"]
    if file.filename == "":
        return jsonify({"error": "No file selected"}), 400

    if not allowed_file(file.filename):
        return jsonify({"error": "Unsupported file type"}), 400

    # Route .txl files through import
    if file.filename.lower().endswith(".txl"):
        try:
            result = _import_txl_from_upload(file)
            return jsonify(result)
        except json.JSONDecodeError:
            return jsonify({"error": "Invalid JSON in TXL file"}), 400
        except ValueError as e:
            return jsonify({"error": str(e)}), 400
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    filename = secure_filename(file.filename)
    upload_path = UPLOAD_FOLDER / filename

    # Handle duplicates
    counter = 1
    while upload_path.exists():
        stem = Path(filename).stem
        suffix = Path(filename).suffix
        upload_path = UPLOAD_FOLDER / f"{stem}_{counter}{suffix}"
        counter += 1

    file.save(upload_path)

    # Immediately convert to .txl format
    try:
        txl_path = _convert_to_txl_from_path(upload_path, original_name=filename)
    except Exception as e:
        return jsonify({"error": f"Failed to convert file to TXL: {str(e)}"}), 400

    touch_recent_file(str(txl_path))

    try:
        file_id = get_txl_file_id_for_path(txl_path)
        sheets = load_workbook_info(txl_path)
        return jsonify({"file_path": str(txl_path), "file_id": file_id, "sheets": sheets})
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@app.route("/api/sheet", methods=["GET"])
def get_sheet():
    file_path = request.args.get("file")
    sheet_name = request.args.get("sheet")
    file_id = request.args.get("file_id")

    if not file_path or not sheet_name:
        return jsonify({"error": "Missing file or sheet parameter"}), 400

    try:
        p = Path(file_path)
        layout = load_layout(p, sheet_name) if file_id else None
        expected_rows = layout.get("data_rows", 0) if layout else 0
        expected_cols = layout.get("data_cols", 0) if layout else 0
        sheet_data = load_sheet_data(p, sheet_name, expected_rows, expected_cols)
        return jsonify({"sheet": sheet_data, "layout": layout})
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@app.route("/api/sheet", methods=["POST"])
def update_sheet():
    data = request.json
    file_path = data.get("file_path")
    sheet_name = data.get("sheet_name")
    sheet_data = data.get("data")

    if not file_path or not sheet_name or sheet_data is None:
        return jsonify({"error": "Missing required fields"}), 400

    try:
        save_sheet_data(Path(file_path), sheet_name, sheet_data)
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@app.route("/api/layout", methods=["POST"])
def save_layout_route():
    data = request.json
    file_path = data.get("file_path")
    sheet_name = data.get("sheet_name")
    state = data.get("state")

    if not file_path or not sheet_name or not state:
        return jsonify({"error": "Missing required fields"}), 400

    try:
        save_layout(Path(file_path), sheet_name, state)
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@app.route("/api/recent", methods=["GET"])
def recent_files():
    files = get_recent_files()
    result = []
    for f in files:
        p = Path(f)
        result.append({"path": f, "name": p.name, "exists": p.exists()})
    return jsonify({"files": result})


@app.route("/api/recent", methods=["DELETE"])
def remove_recent():
    data = request.json
    file_path = data.get("file_path")
    if file_path:
        remove_recent_file(file_path)
    return jsonify({"success": True})


@app.route("/api/open-path", methods=["POST"])
def open_path():
    data = request.json
    file_path = data.get("path")
    if not file_path or not Path(file_path).exists():
        return jsonify({"error": "File not found"}), 404

    p = Path(file_path)
    touch_recent_file(str(p))
    try:
        file_id = get_txl_file_id_for_path(p)
        sheets = load_workbook_info(p)
        return jsonify({"file_path": str(p), "file_id": file_id, "sheets": sheets})
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@app.route("/api/new", methods=["POST"])
def create_new_file():
    data = request.json
    file_name = data.get("file_name", "Untitled.xlsx")
    if not file_name.endswith(".txl"):
        file_name = Path(file_name).stem + ".txl"

    file_path = UPLOAD_FOLDER / file_name
    counter = 1
    while file_path.exists():
        stem = Path(file_name).stem
        suffix = Path(file_name).suffix
        file_path = UPLOAD_FOLDER / f"{stem}_{counter}{suffix}"
        counter += 1

    file_id = str(uuid.uuid4())
    payload = {
        "version": TXL_VERSION,
        "app": "TinyXL",
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "file": {
            "original_name": file_name,
            "file_id": file_id,
            "sheets": [
                {
                    "name": "Sheet1",
                    "data": [[""]],
                    "rows": 1,
                    "cols": 1,
                    "layout": {
                        "column_widths": {},
                        "row_heights": {},
                        "sticky_row": None,
                        "alternate_row_colors": False,
                        "cell_colors": {},
                        "header_rows": [],
                        "columnTypes": {},
                        "data_rows": 1,
                        "data_cols": 1
                    },
                    "linked_sheets": []
                }
            ],
            "linked_sheets": []
        }
    }
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)

    touch_recent_file(str(file_path))
    sheets = ["Sheet1"]
    return jsonify({"file_path": str(file_path), "file_id": file_id, "sheets": sheets})


# ─────────────────────────────────────────────
# EXPORT / IMPORT (TXL)
# ─────────────────────────────────────────────

@app.route("/api/export/txl", methods=["GET"])
def export_txl():
    file_path = request.args.get("file")
    if not file_path:
        return jsonify({"error": "Missing file parameter"}), 400

    try:
        p = Path(file_path)
        if not p.exists():
            return jsonify({"error": "Source file not found"}), 404

        # The file is already .txl — just serve it
        txl = load_txl(p)
        original_name = get_txl_original_name(txl) or p.name

        resp = jsonify(txl)
        resp.headers["Content-Disposition"] = f'attachment; filename="{Path(original_name).stem}.txl"'
        resp.headers["Content-Type"] = "application/json"
        return resp

    except Exception as e:
        return jsonify({"error": str(e)}), 500


def _import_txl_from_upload(txl_file):
    """Import a .txl file — save it directly to uploads/."""
    content = txl_file.read().decode("utf-8")
    payload = json.loads(content)

    if payload.get("app") != "TinyXL" or "file" not in payload:
        raise ValueError("Invalid TXL format")

    file_data = payload["file"]
    original_name = file_data.get("original_name", "imported.txl")
    sheets = file_data.get("sheets", [])

    if not sheets:
        raise ValueError("No sheets in TXL file")

    txl_filename = Path(original_name).with_suffix(".txl").name
    file_path = UPLOAD_FOLDER / txl_filename
    counter = 1
    while file_path.exists():
        stem = Path(txl_filename).stem
        file_path = UPLOAD_FOLDER / f"{stem}_{counter}.txl"
        counter += 1

    # Reuse or generate file_id
    imported_file_id = file_data.get("file_id")
    if imported_file_id:
        try:
            uuid.UUID(imported_file_id)
            file_id = imported_file_id
        except Exception:
            file_id = str(uuid.uuid5(uuid.NAMESPACE_URL, str(file_path.resolve())))
    else:
        file_id = str(uuid.uuid5(uuid.NAMESPACE_URL, str(file_path.resolve())))

    payload["file"]["file_id"] = file_id
    payload["exported_at"] = datetime.now(timezone.utc).isoformat()

    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)

    touch_recent_file(str(file_path))

    return {
        "success": True,
        "file_path": str(file_path),
        "file_id": file_id,
        "original_name": original_name,
        "sheets": [s["name"] for s in sheets]
    }


@app.route("/api/import/txl", methods=["POST"])
def import_txl():
    if "file" not in request.files:
        return jsonify({"error": "No file provided"}), 400

    txl_file = request.files["file"]
    if not txl_file.filename or not txl_file.filename.endswith(".txl"):
        return jsonify({"error": "File must have .txl extension"}), 400

    try:
        result = _import_txl_from_upload(txl_file)
        return jsonify(result)
    except json.JSONDecodeError:
        return jsonify({"error": "Invalid JSON in TXL file"}), 400
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ─────────────────────────────────────────────
# Filter / Linked Sheet helpers — stored in .txl
# ─────────────────────────────────────────────

def _apply_filter(data: list, col: int, op: str, val: str, with_indices: bool = False):
    result = []
    for src_idx, row in enumerate(data):
        cell_val = str(row[col]) if col < len(row) else ""
        match = False
        if op == "equals":
            match = cell_val == val
        elif op == "not_equals":
            match = cell_val != val
        elif op == "contains":
            match = val.lower() in cell_val.lower()
        elif op == "starts_with":
            match = cell_val.lower().startswith(val.lower())
        elif op == "ends_with":
            match = cell_val.lower().endswith(val.lower())
        elif op == "greater_than":
            try:
                match = float(cell_val) > float(val) if cell_val and val else False
            except ValueError:
                match = False
        elif op == "less_than":
            try:
                match = float(cell_val) < float(val) if cell_val and val else False
            except ValueError:
                match = False
        elif op == "greater_equal":
            try:
                match = float(cell_val) >= float(val) if cell_val and val else False
            except ValueError:
                match = False
        elif op == "less_equal":
            try:
                match = float(cell_val) <= float(val) if cell_val and val else False
            except ValueError:
                match = False
        if match:
            if with_indices:
                result.append((src_idx, row))
            else:
                result.append(row)
    return result


@app.route("/api/filter-preview", methods=["POST"])
def filter_preview():
    data = request.json
    file_path = data.get("file_path")
    sheet_name = data.get("sheet_name")
    filter_col = data.get("filter_col")
    filter_op = data.get("filter_op")
    filter_val = data.get("filter_val")
    preserve_headers = data.get("preserve_headers", False)
    header_rows = data.get("header_rows", [])

    if not all([file_path, sheet_name, filter_col is not None, filter_op, filter_val is not None]):
        return jsonify({"error": "Missing required fields"}), 400

    try:
        sheet = load_sheet_data(Path(file_path), sheet_name)
        raw_data = sheet["data"]

        header_data = [raw_data[i] for i in header_rows if i < len(raw_data)]
        data_rows = [raw_data[i] for i in range(len(raw_data)) if i not in header_rows]

        filtered_data = _apply_filter(data_rows, filter_col, filter_op, filter_val)

        if preserve_headers and header_data:
            result = header_data + filtered_data
        else:
            result = filtered_data

        preview = result[:20]
        return jsonify({
            "total_matches": len(filtered_data),
            "total_rows": len(result),
            "preview": preview,
            "preview_rows": len(preview),
            "preview_cols": len(preview[0]) if preview else 0
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@app.route("/api/linked-sheet", methods=["POST"])
def create_linked_sheet():
    try:
        body = request.json
        if body is None:
            return jsonify({"error": "Invalid JSON body"}), 400
        file_path = body.get("file_path")
        source_sheet = body.get("source_sheet")
        display_name = body.get("display_name")
        filter_col = body.get("filter_col")
        filter_op = body.get("filter_op")
        filter_val = body.get("filter_val")
        preserve_headers = body.get("preserve_headers", False)

        if not all([file_path, source_sheet, display_name, filter_col is not None, filter_op, filter_val is not None]):
            return jsonify({"error": "Missing required fields"}), 400

        linked_id = str(uuid.uuid4())
        new_linked = {
            "id": linked_id,
            "source_sheet": source_sheet,
            "display_name": display_name,
            "filter_col": filter_col,
            "filter_op": filter_op,
            "filter_val": filter_val,
            "preserve_headers": bool(preserve_headers),
            "created_at": datetime.now(timezone.utc).isoformat()
        }

        p = Path(file_path)
        txl = load_txl(p)
        sheets = get_txl_sheets(txl)
        src_sheet = None
        for s in sheets:
            if s["name"] == source_sheet:
                src_sheet = s
                break
        if src_sheet is None:
            return jsonify({"error": f"Source sheet '{source_sheet}' not found"}), 404
        src_sheet.setdefault("linked_sheets", []).append(new_linked)
        save_txl(p, txl)

        return jsonify({"id": linked_id, "display_name": display_name})
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@app.route("/api/linked-sheets", methods=["GET"])
def get_linked_sheets():
    file_path = request.args.get("file")
    sheet_name = request.args.get("sheet")
    if not file_path:
        return jsonify({"error": "Missing file parameter"}), 400

    try:
        p = Path(file_path)
        txl = load_txl(p)
        if sheet_name:
            linked = get_txl_sheet_linked_sheets(txl, sheet_name)
        else:
            linked = get_txl_linked_sheets(txl)
        return jsonify({"linked_sheets": linked})
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@app.route("/api/linked-sheet-data", methods=["GET"])
def get_linked_sheet_data():
    linked_id = request.args.get("linked_id")
    file_path = request.args.get("file")
    if not linked_id or not file_path:
        return jsonify({"error": "Missing linked_id or file"}), 400

    try:
        p = Path(file_path)
        txl = load_txl(p)
        linked = None

        for ls in get_txl_linked_sheets(txl):
            if ls["id"] == linked_id:
                linked = ls
                break

        if linked is None:
            for s in get_txl_sheets(txl):
                for ls in s.get("linked_sheets", []):
                    if ls["id"] == linked_id:
                        linked = ls
                        break
                if linked:
                    break

        if not linked:
            return jsonify({"error": "Linked filter not found"}), 404

        filter_col = linked["filter_col"]
        filter_op = linked["filter_op"]
        filter_val = linked["filter_val"]
        source_sheet = linked["source_sheet"]
        preserve_headers = bool(linked.get("preserve_headers", False))

        sheet = load_sheet_data(p, source_sheet)
        raw_data = sheet["data"]

        source_layout = load_layout(p, source_sheet) or {}

        header_rows = []
        if preserve_headers:
            header_rows = source_layout.get("header_rows", [])

        filtered_with_src = _apply_filter(raw_data, filter_col, filter_op, filter_val, with_indices=True)
        filtered = [row for _, row in filtered_with_src]

        if preserve_headers and header_rows:
            header_data = [raw_data[r] for r in header_rows if r < len(raw_data)]
            filtered = header_data + filtered

        if len(filtered) < 1:
            min_rows = 1
            min_cols = max(1, sheet["cols"])
            while len(filtered) < min_rows:
                filtered.append([""] * min_cols)
            for r in range(len(filtered)):
                while len(filtered[r]) < min_cols:
                    filtered[r].append("")

        linked_to_src = list(header_rows) if preserve_headers and header_rows else []
        linked_to_src.extend(idx for idx, _ in filtered_with_src)

        remapped_row_heights = {}
        for linked_row, source_idx in enumerate(linked_to_src):
            src_h = source_layout.get("row_heights", {}).get(str(source_idx))
            if src_h is None:
                src_h = source_layout.get("row_heights", {}).get(source_idx)
            if src_h is not None:
                remapped_row_heights[str(linked_row)] = src_h

        src_cell_colors = source_layout.get("cell_colors", {}) or {}
        remapped_cell_colors = {}
        for linked_row, source_idx in enumerate(linked_to_src):
            for key, color in src_cell_colors.items():
                try:
                    parts = key.split(",")
                    if len(parts) != 2:
                        continue
                    r, c = int(parts[0]), parts[1]
                    if r == source_idx:
                        remapped_cell_colors[str(linked_row) + "," + c] = color
                except ValueError:
                    pass

        column_widths = {}
        source_col_widths = source_layout.get("column_widths", {}) or {}
        for c in range(sheet["cols"]):
            if str(c) in source_col_widths:
                column_widths[str(c)] = source_col_widths[str(c)]
            elif c in source_col_widths:
                column_widths[str(c)] = source_col_widths[c]

        sticky_row = None
        source_sticky = source_layout.get("sticky_row")
        if source_sticky is not None and preserve_headers:
            try:
                sticky_idx = header_rows.index(source_sticky)
                sticky_row = sticky_idx
            except ValueError:
                if source_sticky not in header_rows:
                    sticky_row = 0

        linked_layout = {
            "column_widths": column_widths,
            "row_heights": remapped_row_heights,
            "sticky_row": sticky_row,
            "alternate_row_colors": source_layout.get("alternate_row_colors", False),
            "cell_colors": remapped_cell_colors,
            "header_rows": list(range(len(header_rows))),
            "columnTypes": source_layout.get("columnTypes", {}),
            "data_rows": len(filtered),
            "data_cols": len(filtered[0]) if filtered else 0
        }

        return jsonify({
            "name": linked["display_name"],
            "data": filtered,
            "rows": len(filtered),
            "cols": len(filtered[0]) if filtered else 0,
            "source_sheet": source_sheet,
            "linked_id": linked_id,
            "filter_col": filter_col,
            "filter_op": filter_op,
            "filter_val": filter_val,
            "preserve_headers": preserve_headers,
            "layout": linked_layout
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@app.route("/api/linked-sheet", methods=["DELETE"])
def delete_linked_sheet():
    body = request.json
    linked_id = body.get("id")
    file_path = body.get("file_path")
    if not linked_id:
        return jsonify({"error": "Missing id"}), 400

    if file_path:
        try:
            p = Path(file_path)
            txl = load_txl(p)
            sheets = get_txl_sheets(txl)
            found = False
            for s in sheets:
                linked = s.get("linked_sheets") or []
                initial_len = len(linked)
                s["linked_sheets"] = [ls for ls in linked if ls["id"] != linked_id]
                if len(s["linked_sheets"]) < initial_len:
                    found = True
                    break
            if not found:
                txl["file"]["linked_sheets"] = [
                    ls for ls in get_txl_linked_sheets(txl) if ls["id"] != linked_id
                ]
            save_txl(p, txl)
        except Exception as e:
            return jsonify({"error": str(e)}), 400

    return jsonify({"success": True})


# ─────────────────────────────────────────────
# Sheet operations — now backed by .txl files
# ─────────────────────────────────────────────

def _unique_txl_sheet_name(sheets: list, base_name: str) -> str:
    existing = [s["name"] for s in sheets]
    if base_name not in existing:
        return base_name
    counter = 2
    while f"{base_name}_{counter}" in existing:
        counter += 1
    return f"{base_name}_{counter}"


@app.route("/api/sheet/duplicate", methods=["POST"])
def duplicate_sheet():
    data = request.json
    file_path = data.get("file_path")
    sheet_name = data.get("sheet_name")

    if not file_path or not sheet_name:
        return jsonify({"error": "Missing required fields"}), 400

    try:
        p = Path(file_path)
        txl = load_txl(p)
        sheets = get_txl_sheets(txl)
        src = get_txl_sheet(txl, sheet_name)
        if src is None:
            return jsonify({"error": f"Sheet '{sheet_name}' not found"}), 404

        new_name = _unique_txl_sheet_name(sheets, sheet_name)
        import copy
        new_sheet = copy.deepcopy(src)
        new_sheet["name"] = new_name
        sheets.append(new_sheet)
        save_txl(p, txl)

        return jsonify({"success": True, "sheets": get_txl_sheet_names(txl), "new_sheet": new_name})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/sheet/delete", methods=["POST"])
def delete_sheet_route():
    data = request.json
    file_path = data.get("file_path")
    sheet_name = data.get("sheet_name")

    if not file_path or not sheet_name:
        return jsonify({"error": "Missing required fields"}), 400

    try:
        p = Path(file_path)
        txl = load_txl(p)
        sheets = get_txl_sheets(txl)

        if len(sheets) <= 1:
            return jsonify({"error": "Cannot delete the last sheet"}), 400

        txl["file"]["sheets"] = [s for s in sheets if s["name"] != sheet_name]
        save_txl(p, txl)

        return jsonify({"success": True, "sheets": get_txl_sheet_names(txl)})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/sheet/create", methods=["POST"])
def create_sheet():
    data = request.json
    file_path = data.get("file_path")

    if not file_path:
        return jsonify({"error": "Missing file_path"}), 400

    try:
        p = Path(file_path)
        txl = load_txl(p)
        sheets = get_txl_sheets(txl)
        new_name = _unique_txl_sheet_name(sheets, "Sheet")
        new_sheet = {
            "name": new_name,
            "data": [[""]],
            "rows": 1,
            "cols": 1,
            "layout": {
                "column_widths": {},
                "row_heights": {},
                "sticky_row": None,
                "alternate_row_colors": False,
                "cell_colors": {},
                "header_rows": [],
                "columnTypes": {},
                "data_rows": 1,
                "data_cols": 1
            }
        }
        sheets.append(new_sheet)
        save_txl(p, txl)

        return jsonify({"success": True, "sheets": get_txl_sheet_names(txl), "new_sheet": new_name})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/sheet/reorder", methods=["POST"])
def reorder_sheets():
    data = request.json
    file_path = data.get("file_path")
    sheet_name = data.get("sheet_name")
    direction = data.get("direction")

    if not file_path or not sheet_name or direction not in ("left", "right"):
        return jsonify({"error": "Missing or invalid parameters"}), 400

    try:
        p = Path(file_path)
        txl = load_txl(p)
        sheets = get_txl_sheets(txl)
        names = [s["name"] for s in sheets]

        if sheet_name not in names:
            return jsonify({"error": f"Sheet '{sheet_name}' not found"}), 404

        idx = names.index(sheet_name)
        offset = -1 if direction == "left" else 1
        new_idx = idx + offset

        if new_idx < 0 or new_idx >= len(sheets):
            return jsonify({"error": "Sheet is already at the edge"}), 400

        # Move element
        sheet = sheets.pop(idx)
        sheets.insert(new_idx, sheet)
        save_txl(p, txl)

        return jsonify({"success": True, "sheets": get_txl_sheet_names(txl)})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ─────────────────────────────────────────────
# File metadata — read from .txl
# ─────────────────────────────────────────────

@app.route("/api/file-metadata", methods=["GET"])
def file_metadata():
    file_id = request.args.get("file_id")
    file_path = request.args.get("file")
    if not file_id or not file_path:
        return jsonify({"error": "Missing file_id or file parameter"}), 400

    try:
        p = Path(file_path)
        if not p.exists():
            return jsonify({"error": "Source file not found"}), 404

        txl = load_txl(p)
        original_name = get_txl_original_name(txl)
        sheets_info = get_txl_sheets(txl)
        linked_by_sheet = {}
        for s in sheets_info:
            linked_by_sheet[s["name"]] = get_txl_sheet_linked_sheets(txl, s["name"])

        sheets = []
        for s in sheets_info:
            layout = s.get("layout", {})
            sheets.append({
                "name": s["name"],
                "rows": s["rows"],
                "cols": s["cols"],
                "sticky_row": layout.get("sticky_row"),
                "header_rows": layout.get("header_rows", []),
                "alternate_row_colors": bool(layout.get("alternate_row_colors", False)),
                "data_rows": layout.get("data_rows", s["rows"]),
                "data_cols": layout.get("data_cols", s["cols"]),
            })

        return jsonify({
            "original_name": original_name,
            "file_id": file_id,
            "content_hash": "",
            "first_seen_at": "",
            "last_opened_at": "",
            "sheets": sheets,
            "linked_sheets_by_sheet": linked_by_sheet,
            "linked_sheets": get_txl_linked_sheets(txl),
            "file_size": p.stat().st_size,
            "total_sheets": len(sheets_info)
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=7026)
    args = parser.parse_args()
    app.run(debug=True, port=args.port)
