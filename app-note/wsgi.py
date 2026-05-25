"""
WSGI entry point for PythonAnywhere deployment.

In your PythonAnywhere WSGI config file, point to this module:
    from wsgi import application
Or set the WSGI file path to this file and ensure the working directory is the
repo root, then add it to sys.path if needed.
"""
import sys
import os

# Add repo root to path so `app` is importable
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault("FLASK_ENV", "production")

from app import create_app  # noqa: E402

application = create_app()
