"""Flask app factory for the landing app."""
from flask import Flask

from config import get_config


def create_app() -> Flask:
    app = Flask(__name__, static_folder="../static", template_folder="templates")
    app.config.from_object(get_config())

    from .routes import main_bp

    app.register_blueprint(main_bp)
    return app
