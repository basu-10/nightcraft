from pathlib import Path
import sys


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.database import _sqlite_sql_to_postgres


def test_rewrites_insert_or_ignore_and_qmark_params():
    sql = "INSERT OR IGNORE INTO note_tags (note_id, tag_id) VALUES (?, ?)"
    translated = _sqlite_sql_to_postgres(sql)

    assert translated == "INSERT INTO note_tags (note_id, tag_id) VALUES (%s, %s) ON CONFLICT DO NOTHING"


def test_preserves_question_mark_inside_string_literals():
    sql = "SELECT '?' AS marker, title FROM notes WHERE id=?"
    translated = _sqlite_sql_to_postgres(sql)

    assert "'?' AS marker" in translated
    assert translated.endswith("WHERE id=%s")


def test_rewrites_case_insensitive_comparison():
    sql = "SELECT id FROM users WHERE username=? COLLATE NOCASE"
    translated = _sqlite_sql_to_postgres(sql)

    assert "LOWER(username) = LOWER(%s)" in translated
    assert "COLLATE NOCASE" not in translated


def test_rewrites_sqlite_datetime_and_insert_id_functions():
    sql = "UPDATE notes SET updated_at=datetime('now') WHERE id=(SELECT last_insert_rowid() AS id)"
    translated = _sqlite_sql_to_postgres(sql)

    assert "CURRENT_TIMESTAMP" in translated
    assert "LASTVAL()" in translated
    assert "last_insert_rowid" not in translated.lower()
