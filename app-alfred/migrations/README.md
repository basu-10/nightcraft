# Alfred Database Migrations

Alfred uses SQLAlchemy `db.create_all()` at app startup (`alfred/__init__.py`)
as its schema bootstrap. There is **no Alembic setup** yet; the additive
`AgentRun` / `Asset` columns added during the runtime review were introduced on
a fresh schema, so `create_all()` picks them up automatically on next boot.

## Upgrading an existing production database

For a database that was bootstrapped *before* these columns existed, run the
following idempotent SQL **before** deploying the new code (or run it alongside
a blue/green deploy). All additions are nullable, so they cannot lose data.

```sql
-- agent_run: runtime policies (P1 #2)
ALTER TABLE agent_run
  ADD COLUMN IF NOT EXISTS max_runtime_seconds INTEGER,
  ADD COLUMN IF NOT EXISTS idle_timeout_seconds INTEGER,
  ADD COLUMN IF NOT EXISTS token_budget INTEGER,
  ADD COLUMN IF NOT EXISTS cost_budget_usd DOUBLE PRECISION,
  -- capability versioning (P2 #13)
  ADD COLUMN IF NOT EXISTS capability VARCHAR(80),
  ADD COLUMN IF NOT EXISTS capability_version VARCHAR(40),
  ADD COLUMN IF NOT EXISTS manifest_hash VARCHAR(64),
  -- artifact version pinning (P2 #14)
  ADD COLUMN IF NOT EXISTS run_input_hash VARCHAR(64),
  -- live accounting
  ADD COLUMN IF NOT EXISTS started_at TIMESTAMP WITHOUT TIME ZONE,
  ADD COLUMN IF NOT EXISTS last_activity_at TIMESTAMP WITHOUT TIME ZONE,
  ADD COLUMN IF NOT EXISTS tokens_used INTEGER NOT NULL DEFAULT 0,
  ADD COLUMN IF NOT EXISTS cost_usd DOUBLE PRECISION NOT NULL DEFAULT 0.0;

-- asset: deferred workspace_id (P3 #8) — nullable / unused
ALTER TABLE asset
  ADD COLUMN IF NOT EXISTS workspace_id VARCHAR(100);

-- agent_run: workspace_id (P3 #8) — nullable / unused
ALTER TABLE agent_run
  ADD COLUMN IF NOT EXISTS workspace_id VARCHAR(100);
```

## Future: when to add Alembic

Once Alfred has non-additive schema changes (column renames, type changes,
drops), introduce Alembic and generate an initial migration from the current
model, then switch `create_all()` to `alembic upgrade head` in startup. Until
then, additive columns + this documented SQL are sufficient and low-risk.
