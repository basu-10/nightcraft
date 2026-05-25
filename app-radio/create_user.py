#!/usr/bin/env python
"""Create an testuser user for testing."""
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
        # Check if testuser exists
        testuser = LocalCredential.query.filter_by(username='testuser').first()
        if testuser:
            print("✓ Testuser already exists")
        else:
            # Create testuser
            testuser = LocalCredential(username='testuser', role='listener')
            testuser.set_password('testuser123')
            db.session.add(testuser)
            db.session.flush()
            db.session.add(UserProfile(user_id=str(testuser.id), username=testuser.username, is_admin=False))
            db.session.commit()
            print("✓ Testuser created successfully")
