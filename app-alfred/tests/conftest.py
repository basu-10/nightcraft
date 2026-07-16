import importlib
import os
import sys
from pathlib import Path

import pytest

APP_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP_ROOT))


def _has_postgres():
    return bool(os.getenv("DATABASE_URL"))


pytestmark = pytest.mark.skipif(
    not _has_postgres(),
    reason="PostgreSQL DATABASE_URL not set; skipping Alfred DB integration tests",
)


@pytest.fixture(scope="session")
def _app_once(tmp_path_factory):
    base = tmp_path_factory.mktemp("alfred_uploads")
    os.environ["AUTH_MODE"] = "local"
    os.environ["FLASK_ENV"] = "development"
    os.environ["UPLOADS_DIR"] = str(base / "uploads")
    import alfred as alfred_pkg

    return alfred_pkg.create_app()


@pytest.fixture
def app(_app_once):
    _app_once.config.update(TESTING=True)
    return _app_once


@pytest.fixture
def client(app):
    from alfred.extensions import db

    with app.app_context():
        db.drop_all()
        db.create_all()
    with app.test_client() as c:
        yield c
    with app.app_context():
        db.drop_all()


@pytest.fixture
def runner(app):
    return app.test_cli_runner()
