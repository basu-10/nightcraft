"""
Local development server entry point.
Run:  python app-note/run.py
"""
import os
import sys

# Allow running from repo root: python app-note/run.py
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault("FLASK_ENV", "development")

from app import create_app

if __name__ == "__main__":
    app = create_app()
    host = os.environ.get("FLASK_HOST", "127.0.0.1")
    port = int(os.environ.get("FLASK_PORT", "5335"))
    app.run(host=host, port=port, debug=True)
