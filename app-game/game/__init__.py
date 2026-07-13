from flask import Flask

from config import get_config


def create_app() -> Flask:
    app = Flask(__name__, static_folder="../static", template_folder="templates")
    app.config.from_object(get_config())

    from .routes import game_bp
    app.register_blueprint(game_bp)

    from .auth import auth_bp
    app.register_blueprint(auth_bp)

    from .emulator import emulator_bp, init_db
    app.register_blueprint(emulator_bp)
    with app.app_context():
        init_db()

    return app
