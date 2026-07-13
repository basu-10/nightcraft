from flask import Blueprint

bp = Blueprint("game", __name__)


def register_blueprints(app):
    # Importing the modules executes their @bp.route decorators so the
    # routes are registered on the shared `bp` blueprint. url_for('game.<x>')
    # references continue to work for existing templates.
    from . import landing  # noqa: F401
    from . import lobby  # noqa: F401
    from . import room  # noqa: F401
    from . import leaderboard  # noqa: F401

    app.register_blueprint(bp)
