import click

from .extensions import db


def register_cli(app):
    @app.cli.command("setup")
    def setup():
        with app.app_context():
            db.create_all()
        click.echo("Setup complete")
