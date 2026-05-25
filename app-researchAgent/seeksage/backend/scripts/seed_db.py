"""
Idempotent seed script — creates admin and test accounts if they don't exist.

Usage (from backend/ dir with venv active):
    python scripts/seed_db.py
    ADMIN_PASSWORD=secret TEST_PASSWORD=test123 python scripts/seed_db.py
"""
import os
import sys

# Ensure the backend package is importable when run from backend/
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app
from app.extensions import db
from app.models import User


ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", "admin@chotu.local")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "changeme1")
TEST_EMAIL = os.environ.get("TEST_EMAIL", "test@chotu.local")
TEST_PASSWORD = os.environ.get("TEST_PASSWORD", "testpass1")


def seed():
    app = create_app()
    with app.app_context():
        created = []

        admin = User.query.filter_by(email=ADMIN_EMAIL).first()
        if not admin:
            admin = User(email=ADMIN_EMAIL, is_admin=True)
            admin.set_password(ADMIN_PASSWORD)
            db.session.add(admin)
            created.append(f"admin  → {ADMIN_EMAIL}")
        else:
            print(f"[skip] admin already exists: {ADMIN_EMAIL}")

        test_user = User.query.filter_by(email=TEST_EMAIL).first()
        if not test_user:
            test_user = User(email=TEST_EMAIL, is_admin=False)
            test_user.set_password(TEST_PASSWORD)
            db.session.add(test_user)
            created.append(f"test   → {TEST_EMAIL}")
        else:
            print(f"[skip] test user already exists: {TEST_EMAIL}")

        if created:
            db.session.commit()
            for line in created:
                print(f"[created] {line}")
        print("Seed complete.")


if __name__ == "__main__":
    seed()
