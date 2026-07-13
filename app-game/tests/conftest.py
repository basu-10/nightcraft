import os
import tempfile

# Set the shared dir BEFORE importing `game`, because config.py reads
# GAME_SHARED_DIR at import time.
_TMP_SHARED = tempfile.mkdtemp(prefix="nightcraft-game-test-")
os.environ["GAME_SHARED_DIR"] = _TMP_SHARED

import fakeredis  # noqa: E402
import pytest  # noqa: E402

from game import create_app, matchmaking, leaderboard  # noqa: E402


@pytest.fixture
def app():
    application = create_app()
    application.config["TESTING"] = True
    application.config["GAME_SHARED_DIR"] = _TMP_SHARED
    application.config["EMULATOR_UPLOAD_DIR"] = os.path.join(_TMP_SHARED, "uploads")
    application.config["EMULATOR_DB_PATH"] = os.path.join(_TMP_SHARED, "emulator.db")

    fake = fakeredis.FakeStrictRedis(decode_responses=True)
    original_mm = matchmaking._rc
    original_lb = leaderboard._rc
    matchmaking._rc = lambda: fake
    leaderboard._rc = lambda: fake

    yield application

    matchmaking._rc = original_mm
    leaderboard._rc = original_lb


@pytest.fixture
def client(app):
    return app.test_client()
