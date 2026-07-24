import os
import time

import click
from flask import current_app

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
    base = current_app.config.get("UPLOADS_DIR", "uploads")
    if not os.path.isabs(base):
        base = os.path.join(current_app.instance_path, base)
    try:
        os.makedirs(base, exist_ok=True)
        probe = os.path.join(base, ".healthcheck")
        with open(probe, "w") as fh:
            fh.write("ok")
        os.remove(probe)
    except Exception as exc:
        return [f"Uploads directory not writable ({base}): {exc}"]
    return []


def _check_pgvector():
    try:
        with db.engine.begin() as conn:
            conn.exec_driver_sql("SELECT 1 FROM pg_extension WHERE extname='vector'")
    except Exception as exc:
        return [f"pgvector unavailable: {exc}"]
    return []


def _replay_manifest_hash():
    """Recompute the planner manifest hash as of now (F7: replay from manifest_hash)."""
    from .agent.planner import plan_goal_capability

    return plan_goal_capability("replay-probe", "__replay_probe__")["manifest_hash"]


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

    @app.cli.command("janitor")
    @click.option("--once", is_flag=True, help="Run a single reconciliation pass and exit.")
    @click.option("--report", is_flag=True, help="Print cumulative janitor stats and exit.")
    def janitor(once, report):
        """§4 Janitorial worker: reconcile asset/run consistency; loop every 60s by default."""
        from .janitor import run_janitor_pass, stats

        if report:
            s = stats()
            click.echo("Janitor stats:")
            for k, v in s.items():
                click.echo(f"  {k}: {v}")
            return

        if once:
            summary = run_janitor_pass()
            click.echo("Janitor pass complete:")
            for k, v in (summary or {}).items():
                click.echo(f"  {k}: {v}")
            return

        click.echo("Starting janitor loop (every 60s). Ctrl-C to stop.")
        from .janitor import start

        start()
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            from .janitor import stop

            stop()
            click.echo("Janitor stopped.")

    @app.cli.command("replay")
    @click.argument("run_id")
    def replay(run_id):
        """F7: Re-run a prior AgentRun only if the planner manifest hash is unchanged.

        Catches silent recompile drift: if the planner contract changed since the run
        was compiled, refuse to replay (the recorded manifest_hash would no longer
        match) and exit non-zero.
        """
        from .models import AgentRun

        run = AgentRun.query.filter_by(run_id=run_id).first()
        if run is None:
            click.echo(f"Run '{run_id}' not found.")
            raise SystemExit(2)

        current_hash = _replay_manifest_hash()
        if run.manifest_hash != current_hash:
            click.echo("Replay REFUSED: planner manifest hash drifted since compile.")
            click.echo(f"  stored : {run.manifest_hash}")
            click.echo(f"  current: {current_hash}")
            raise SystemExit(1)

        click.echo(f"Replay OK: manifest hash matches ({current_hash[:12]}…). Re-running '{run_id}'.")
        import threading

        from .agent import executor as executor_module

        plan = run.plan
        if not plan or not plan.get("phases"):
            click.echo("Run has no stored plan; cannot replay.")
            raise SystemExit(1)

        app_obj = current_app._get_current_object()

        def _worker():
            with app_obj.app_context():
                executor_module.run_workflow(run.run_id, run.user_id, run.goal, plan)

        threading.Thread(target=_worker, daemon=True).start()
        click.echo("Replay dispatched.")
