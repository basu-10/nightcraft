import io

from game import emulator


def _inserted_rom_id(app):
    with app.app_context():
        conn = emulator._get_conn()
        try:
            row = conn.execute("SELECT id FROM roms ORDER BY id DESC LIMIT 1").fetchone()
        finally:
            conn.close()
        return None if row is None else row["id"]


def test_index_requires_login_and_lists(client):
    resp = client.get("/game/emulator/")
    assert resp.status_code == 200
    assert b"My Games" in resp.data


def test_upload_rejects_disallowed_extension(client):
    data = {
        "rom": (io.BytesIO(b"not a rom"), "evil.zip"),
        "rights_confirm": "1",
    }
    resp = client.post("/game/emulator/upload", data=data, content_type="multipart/form-data")
    assert resp.status_code == 400


def test_upload_requires_rights_confirm(client):
    data = {
        "rom": (io.BytesIO(b"fake gba data"), "game.gba"),
    }
    resp = client.post("/game/emulator/upload", data=data, content_type="multipart/form-data")
    assert resp.status_code == 400


def test_upload_and_play_and_delete_flow(client, app):
    data = {
        "rom": (io.BytesIO(b"A" * 1024), "mygame.gba"),
        "rights_confirm": "1",
    }
    resp = client.post("/game/emulator/upload", data=data, content_type="multipart/form-data")
    assert resp.status_code == 302

    rom_id = _inserted_rom_id(app)
    assert rom_id is not None

    play = client.get(f"/game/emulator/play/{rom_id}")
    assert play.status_code == 200
    assert b"loader.js" in play.data
    assert b"EJS_core" in play.data

    rom = client.get(f"/game/emulator/rom/{rom_id}")
    assert rom.status_code == 200
    assert rom.data == b"A" * 1024

    # Unknown ROM id must 404 (never leak existence).
    missing = client.get("/game/emulator/rom/999999")
    assert missing.status_code == 404

    delete = client.post(f"/game/emulator/delete/{rom_id}")
    assert delete.status_code == 302
    assert _inserted_rom_id(app) is None
