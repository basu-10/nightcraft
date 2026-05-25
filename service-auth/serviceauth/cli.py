import click

from .extensions import db
from .models import OauthClient, User


def _upsert_user(username, email, password, is_admin):
    user = User.query.filter_by(username=username).first()
    if user is None:
        user = User(username=username, email=email, is_admin=is_admin)
        user.set_password(password)
        db.session.add(user)
        role_name = "admin" if is_admin else "user"
        click.echo(f"Created {role_name} user '{username}'")
        return

    changed = False
    if user.email != email:
        user.email = email
        changed = True
    if user.is_admin != is_admin:
        user.is_admin = is_admin
        changed = True

    if changed:
        role_name = "admin" if is_admin else "user"
        click.echo(f"Updated existing user '{username}' to match {role_name} seed settings")
    else:
        click.echo(f"User '{username}' already exists")


def _upsert_oauth_client(client_id, client_secret, redirect_uri):
    client = OauthClient.query.filter_by(client_id=client_id).first()
    if client is None:
        client = OauthClient(
            client_id=client_id,
            client_secret=client_secret,
            redirect_uris=redirect_uri,
            scope="openid profile email",
        )
        db.session.add(client)
        click.echo(f"Created oauth client '{client_id}'")
        return

    # Keep redirects additive for convenient local iteration.
    redirects = [r.strip() for r in client.redirect_uris.replace("\n", ",").split(",") if r.strip()]
    if redirect_uri not in redirects:
        redirects.append(redirect_uri)
        client.redirect_uris = ",".join(redirects)
        click.echo(f"Updated oauth client '{client_id}' redirect URIs")
    else:
        click.echo(f"Oauth client '{client_id}' already includes redirect URI")


def register_cli(app):
    @app.cli.command("seed-dev")
    @click.option("--username", default="devuser", show_default=True)
    @click.option("--email", default="devuser@example.com", show_default=True)
    @click.option("--password", default="devpass123", show_default=True)
    @click.option("--client-id", default="radio-app", show_default=True)
    @click.option("--client-secret", default="dev-secret", show_default=True)
    @click.option("--redirect-uri", default="http://127.0.0.1:5000/auth/callback", show_default=True)
    def seed_dev(username, email, password, client_id, client_secret, redirect_uri):
        _upsert_user(username=username, email=email, password=password, is_admin=False)
        _upsert_oauth_client(
            client_id=client_id,
            client_secret=client_secret,
            redirect_uri=redirect_uri,
        )

        db.session.commit()
        click.echo("Seed complete")

    @app.cli.command("seed-role-users")
    @click.option("--user-username", default="seeduser", show_default=True)
    @click.option("--user-email", default="seeduser@example.com", show_default=True)
    @click.option("--user-password", default="seeduser123", show_default=True)
    @click.option("--admin-username", default="seedadmin", show_default=True)
    @click.option("--admin-email", default="seedadmin@example.com", show_default=True)
    @click.option("--admin-password", default="seedadmin123", show_default=True)
    def seed_role_users(
        user_username,
        user_email,
        user_password,
        admin_username,
        admin_email,
        admin_password,
    ):
        _upsert_user(
            username=user_username,
            email=user_email,
            password=user_password,
            is_admin=False,
        )
        _upsert_user(
            username=admin_username,
            email=admin_email,
            password=admin_password,
            is_admin=True,
        )

        db.session.commit()
        click.echo("Role user seed complete")
