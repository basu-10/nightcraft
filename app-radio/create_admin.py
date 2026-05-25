#!/usr/bin/env python
"""Create an admin user for testing."""
import os
from pathlib import Path

from devradio import create_app
from devradio.extensions import db
from devradio.models import LocalCredential, UserProfile

_SHARED_INSTANCE = Path(
    os.getenv("RADIO_SHARED_INSTANCE_DIR", "/platform-infra/runtime/shared/dev-podcast-app/instance")
)
_SHARED_INSTANCE.mkdir(parents=True, exist_ok=True)

if __name__ == '__main__':
    app = create_app(instance_path=str(_SHARED_INSTANCE))
    
    with app.app_context():
        # Check if admin user exists
        admin = LocalCredential.query.filter_by(username='admin').first()
        if admin:
            print("✓ Admin user already exists")
        else:
            # Create admin user
            admin = LocalCredential(username='admin', role='admin')
            admin.set_password('admin123')
            db.session.flush()
            db.session.add(UserProfile(user_id=str(admin.id), username=admin.username, is_admin=True))
            db.session.commit()
            print("✓ Admin user created successfully")
