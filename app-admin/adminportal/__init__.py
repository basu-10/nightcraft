"""Flask app factory for the admin handoff app."""
from flask import Flask
from werkzeug.middleware.proxy_fix import ProxyFix

from config import get_config


def create_app() -> Flask:
    app = Flask(__name__, static_folder="../static", template_folder="templates")
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)
    app.config.from_object(get_config())

    from .routes import main_bp

    app.register_blueprint(main_bp)
    return app
