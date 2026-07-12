import click

from .extensions import db
from .models import LocalCredential, Pledge, UserProfile


DEFAULT_PLEDGES = [
    {
        "slug": "reduce-single-use-plastic",
        "title": "Cut single-use plastic",
        "description": "Refuse disposable plastic cutlery, straws, and bags; carry reusables.",
        "category": "waste",
    },
    {
        "slug": "climate-friendly-commute",
        "title": "Climate-friendly commute",
        "description": "Walk, cycle, carpool, or take transit at least 3 days a week.",
        "category": "transport",
    },
    {
        "slug": "plant-for-the-planet",
        "title": "Plant for the planet",
        "description": "Plant and care for at least one tree or native plant this year.",
        "category": "nature",
    },
]


def register_cli(app):
    @app.cli.command("setup")
    def setup():
        db.create_all()
        _seed_accounts()
        _seed_pledges()
        click.echo("Setup complete.")


def _seed_accounts():
    defaults = [
        ("admin", "admin123", "admin"),
        ("testuser", "test123", "member"),
    ]
    for username, password, role in defaults:
        user = LocalCredential.query.filter_by(username=username).first()
        if not user:
            user = LocalCredential(username=username, role=role)
            user.set_password(password)
            db.session.add(user)
            db.session.flush()
        else:
            user.role = role
            user.set_password(password)

        profile = UserProfile.query.filter_by(user_id=str(user.id)).first()
        if not profile:
            db.session.add(
                UserProfile(
                    user_id=str(user.id),
                    username=user.username,
                    is_admin=user.is_admin,
                    timezone_name="Asia/Kolkata",
                )
            )
        else:
            profile.username = user.username
            profile.is_admin = user.is_admin

    db.session.commit()


def _seed_pledges():
    for entry in DEFAULT_PLEDGES:
        existing = Pledge.query.filter_by(slug=entry["slug"]).first()
        if not existing:
            db.session.add(Pledge(**entry))
    db.session.commit()
