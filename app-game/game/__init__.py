from flask import Flask
from werkzeug.middleware.proxy_fix import ProxyFix

from config import get_config


def create_app() -> Flask:
    app = Flask(__name__, static_folder="../static", template_folder="templates")
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)
    app.config.from_object(get_config())

    from .views import register_blueprints
    register_blueprints(app)

    from .auth import auth_bp
    app.register_blueprint(auth_bp)

    from .emulator import emulator_bp, init_db
    app.register_blueprint(emulator_bp)
    with app.app_context():
        init_db()

    return app
