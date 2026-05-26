# pythonanywhere_wsgi.py
#
# Paste the contents of this file into your PythonAnywhere WSGI configuration
# file (Web tab → WSGI configuration file → edit).
#
# PythonAnywhere path: /var/www/<yourusername>_pythonanywhere_com_wsgi.py
#
# ── Required edits ────────────────────────────────────────────────────────────
# 1. Replace YOURUSER with your PythonAnywhere username.
# 2. Replace YOURVENV with your virtualenv name if different from "seeksage".
# 3. Set all environment variables in the dict below (or use a .env file).
# ─────────────────────────────────────────────────────────────────────────────

import os
import sys

# ── Paths ─────────────────────────────────────────────────────────────────────
# Adjust to wherever you cloned the repo on PythonAnywhere.
PROJECT_ROOT = "/home/YOURUSER/seeksage/seeksage_webapp/backend"
VENV_SITE    = "/home/YOURUSER/.virtualenvs/YOURVENV/lib/python3.12/site-packages"

if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)
if VENV_SITE not in sys.path:
    sys.path.insert(0, VENV_SITE)

# ── Environment variables ─────────────────────────────────────────────────────
# Set sensitive values here (or load from a .env file with python-dotenv).
os.environ.setdefault("SECRET_KEY",     "CHANGE-ME-to-a-long-random-string")
os.environ.setdefault("DATABASE_URL",   "postgresql+psycopg://USER:PASSWORD@HOST:5432/nightcraft_seeksage")
os.environ.setdefault("CORS_ORIGINS",   "https://YOURUSER.pythonanywhere.com")
# If you serve the frontend from the same origin, set CORS_ORIGINS to that URL.
# For a separate Vite/React app hosted elsewhere, add its URL here (comma-separated).

# ── WSGI application ──────────────────────────────────────────────────────────
from app import create_app  # noqa: E402

application = create_app()
