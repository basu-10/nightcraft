"""WSGI entry point for production."""
import os

from adminportal import create_app

os.environ.setdefault("FLASK_ENV", "production")
application = create_app()
