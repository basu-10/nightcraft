import os

import click

from .extensions import db
from .models import LocalCredential, UserProfile


def _check_providers():
    errors = []
    from .providers import _api_key, resolve_provider_ok

    if not _api_key():
        errors.append("No LLM API key configured (set alfred_openrouter_api_key or OPENROUTER_API_KEY).")
    if not resolve_provider_ok():
        errors.append("LLM provider client could not be constructed.")
    return errors


def _check_embedding_model():
    from .settings_keys import resolve_embedding_model

    model = resolve_embedding_model()
    if not model:
        return ["No embedding model configured."]
    return []


def _check_storage():
    from flask import current_app

    base = current_app.config.get("UPLOADS_DIR", "uploads")
    if not os.path.isabs(base):
        base = os.path.join(current_app.instance_path, base)
    try:
        os.makedirs(base, exist_ok=True)
        probe = os.path.join(base, ".healthcheck")
        with open(probe, "w") as fh:
            fh.write("ok")
        os.remove(probe)
    except Exception as exc:  # noqa: BLE001
        return [f"Uploads directory not writable ({base}): {exc}"]
    return []


def _check_pgvector():
    try:
        with db.engine.begin() as conn:
            conn.exec_driver_sql("SELECT 1 FROM pg_extension WHERE extname='vector'")
    except Exception as exc:  # noqa: BLE001
        return [f"pgvector unavailable: {exc}"]
    return []


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

    @app.cli.command("check")
    def check():
        """Fail-fast startup health check: providers, API key, embeddings, storage, pgvector."""
        errors = []
        errors += _check_providers()
        errors += _check_embedding_model()
        errors += _check_storage()
        errors += _check_pgvector()

        if errors:
            click.echo("Health check FAILED:")
            for e in errors:
                click.echo(f"  - {e}")
            raise SystemExit(1)
        click.echo("Health check passed.")
