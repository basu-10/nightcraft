import click

from .extensions import db
from .models import LocalCredential, UserProfile


def register_cli(app):
    @app.cli.command("setup")
    @click.option("--username", default="testuser", show_default=True)
    @click.option("--password", default="test123", show_default=True)
    def setup(username, password):
        user = LocalCredential.query.filter_by(username=username).first()
        if user is None:
            user = LocalCredential(username=username)
            user.set_password(password)
            db.session.add(user)
            db.session.flush()
            user.ensure_profile()
            db.session.commit()
            click.echo(f"Created local user '{username}'")
        else:
            click.echo(f"User '{username}' already exists")

        click.echo("Setup complete")
