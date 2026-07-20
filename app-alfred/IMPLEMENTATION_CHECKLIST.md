# Alfred Runtime Review — Implementation Checklist (Cross-Session)

> Durable, resumable checklist for `nightcraft/app-alfred/` (and `platform-infra/prod-debian/`).
> Companion to `app-alfred/IMPLEMENTATION_PIPELINE.md` (the original review) and
> `app-alfred/ARCHITECTURE.md` (design + Implementation Status section).
>
> Status legend: `[x]` done · `[~]` partial / follow-up needed · `[ ]` not started.
> Each item records: what to do, file(s), and the current state as of last session.

---

## Environment notes (read first — saves time)
- Repo root: `nightcraft/app-alfred/`. DB-backed tests need `DATABASE_URL` set.
- `pytest.ini` + `tests/conftest.py` skip all DB tests when `DATABASE_URL` is unset
  (`pytestmark = skipif(not _has_postgres())`). So pure-logic tests run without PG.
- **KNOWN BLOCKER:** in this sandbox, `flask_sqlalchemy`/`sqlalchemy` is incompatible
  with Python 3.14 (collection-time `AssertionError: ... TypingOnly`). The existing
  `test_core.py`/`test_planner.py` fail identically at collection. The suite cannot
  run here — run `cd app-alfred && python -m pytest` only in a properly provisioned
  env (matching `requirements.txt`, e.g. the `/runtime/venvs/app-alfred` venv).
- `py_compile` works for syntax checks even without the full stack.

---

## 🔴 P1 — Highest priority

- [x] **1. Gunicorn workers = 1 (deployment invariant)**
  - Files: `app-alfred/gunicorn.conf.py` (NEW), `platform-infra/prod-debian/systemd/nightcraft-alfred.service`, `platform-infra/prod-debian/products.yml`
  - Done: `gunicorn.conf.py` pins `workers=1`, rejects multi-worker `GUNICORN_WORKERS` overrides (warns + forces 1). systemd + products.yml set `workers: 1`.
  - Verify: prod startup uses `--workers=1` via `--config gunicorn.conf.py`.

- [x] **2. Runtime policies: idle timeout + max runtime (+ token/cost budget)**
  - Files: `alfred/models.py` (`AgentRun` cols), `alfred/agent/executor.py` (`_RuntimePolicy`, `_PolicyClock`, loop checks)
  - Done: `AgentRun` has `max_runtime_seconds`, `idle_timeout_seconds`, `token_budget`, `cost_budget_usd`, plus `started_at`/`last_activity_at`/`tokens_used`/`cost_usd`. Executor aborts with status `fatal` on breach. Added `_utcnow()` helper.
  - [~] **FOLLOW-UP:** budgets are *structural only* — `policy.touch(tokens=0, cost=0.0)` is stubbed; `api.py` does not yet read policy overrides from client/settings. See follow-up items F1–F2.

## 🟠 P2 — Important

- [x] **3. `/touch` authentication (operational security)**
  - Files: `platform-infra/prod-debian/runtime-manager/nightcraft-runtime-manager.py` (`Handler._client_is_loopback` + 403 on non-loopback `/touch`)
  - Done: manager rejects non-loopback `/touch` callers; multi-tenant future (Manager Secret/UDS/mTLS) documented in code comment.

- [x] **4. Evidence enforcement (schema, not promises)**
  - Files: `alfred/models.py` (`assert_derivation_has_sources`), `alfred/agent/tools.py` (called in `tool_save_report` + `tool_transform_asset`)
  - Done: derived artifact write rejected when `Evidence.sources` empty.
  - [~] **FOLLOW-UP:** RAG `library_search` (alfred/rag/__init__.py) creates `Evidence` with possibly-empty sources (legit when no matches) — validator must stay scoped to derived-artifact writes; add a test proving RAG path is exempt (F6).

- [x] **5. Asset isolation / ownership**
  - Files: `alfred/guards.py` (`require_owned_asset`), `alfred/api.py` (applied in `start_run` to `referenced_asset_ids`)
  - Done: client-supplied referenced asset ids are validated as owned before run start.
  - [~] **FOLLOW-UP:** relation-creation / asset-deletion paths in `library.py`/`api.py` not yet guarded (F5).

## 🟡 P3 — Correctness / drift

- [x] **6. LangGraph checkpointer clarification (docs)** — ARCHITECTURE.md §4b already states PostgresSaver default / MemorySaver optional / Redis unsupported. No code change needed.

- [x] **7. Reindex without downtime (atomic swap)**
  - Files: `alfred/ingest/__init__.py` (`reindex_library` rewritten)
  - Done: builds temp generation `<model>#reindex`, then in one transaction deletes old generation and renames temp→active. Search never sees partial index.
  - [~] **FOLLOW-UP:** no guard against concurrent reindexes per user (F11).

- [x] **8. `workspace_id` — keep nullable/unused** — confirmed nullable in `Asset` + `AgentRun` with clarifying comments; no logic built around it.

- [x] **9. Binary edits — explicit product rule**
  - Files: `alfred/ingest/__init__.py` (original flagged `is_original`/`original_preserved`), `alfred/agent/tools.py` (reports flagged `is_generated_version`), `templates/alfred/asset.html` (banner), `static/alfred/styles.css` (`.notice`)
  - Done: original preserved; generated markdown version surfaces "Generated markdown version — the original asset is unchanged."

## 🟢 P4 — Hygiene

- [x] **10. `requests` dependency** — confirmed present in `requirements.txt` (2.32.3).

- [x] **11. Startup health check (fail fast)**
  - Files: `alfred/cli.py` (`flask check` command + `_check_*` helpers), `alfred/providers/__init__.py` (`resolve_provider_ok`)
  - Done: `flask check` verifies providers → API key → embedding model → storage → pgvector, exits non-zero on failure.
  - [~] **FOLLOW-UP:** `create_app` does NOT yet call the check at startup (pipeline wants fail-fast before serving). Add opt-in `FAIL_FAST_HEALTHCHECK` config (F3).

- [x] **12. Documentation drift sweep** — ARCHITECTURE.md §4b gained an "Implementation Status" subsection mapping each item to code; no architecture change.

## ⭐ Missed gaps (confirmed: both added)

- [x] **13. Capability Versioning**
  - Files: `alfred/models.py` (`capability`/`capability_version`/`manifest_hash`), `alfred/agent/planner.py` (`plan_goal_capability`, `_classify_capability`, `ALFRED_CAPABILITY_VERSION`)
  - Done: each run records capability + version + manifest hash at plan time.
  - [~] **FOLLOW-UP:** hash is recorded but not consumed — add replay/consistency check (F7).

- [x] **14. Artifact Version Pinning**
  - Files: `alfred/models.py` (`run_input_hash`), `alfred/api.py` (`_pin_input_hash`, stored on `AgentRun` at start)
  - Done: referenced asset ids + content hashes pinned at run-start.
  - [~] **FOLLOW-UP:** hash recorded but not compared at exec time — add stale-input guard (F8).

---

## 🔧 Follow-up backlog (discovered during implementation)

Priority order suggested. Each is a concrete next patch.

- [x] **F1. Surface runtime policies as admin settings** — keys added to `alfred/settings_keys.py` (`alfred_max_runtime_seconds`, `alfred_idle_timeout_seconds`, `alfred_token_budget`, `alfred_cost_budget_usd`) with resolvers; `start_run` resolves admin defaults when the client omits an override (negative ⇒ unbounded).
- [x] **F2. Real token/cost accounting** — `LLMProvider_openai_chat` returns the response; `run_workflow` reads `resp.usage` via `_usage_from_response` and feeds tokens/cost into `policy.touch()` so token/cost budgets now fire. `run.tokens_used`/`cost_usd` persisted.
- [x] **F3. Fail-fast startup** — `_fail_fast_healthcheck` in `alfred/__init__.py` runs the same checks as `flask check` during `create_app` when `FAIL_FAST_HEALTHCHECK` config is set; raises on failure.
- [x] **F4. Interruptible max-runtime** — `_RuntimePolicy.deadline()` computes remaining wall-clock; threaded as the OpenAI request `timeout` so a single long call cannot overrun `max_runtime`.
- [x] **F5. Ownership on relation/delete paths** — `delete_asset` (library.py) routed through `require_owned_asset`; `tool_save_report` only links `derived_from` to assets the user owns; `tool_transform_asset` already filters the source by `user_id`.
- [x] **F6. Prove RAG Evidence is exempt** — added `test_rag_evidence_exempt_from_derivation_validator` proving RAG `Evidence` with empty sources is constructed without the validator (validator stays scoped to derived-artifact writes).
- [x] **F7. Replay from `manifest_hash`** — `flask replay <run_id>` re-runs only if the current planner manifest hash matches the stored one; refuses on drift.
- [x] **F8. Stale-input guard** — `run_workflow` recomputes `_pin_input_hash` and aborts with `status=error` if a referenced asset changed after compile.
- [x] **F9. DB migration** — no Alembic; added `app-alfred/migrations/README.md` documenting the `db.create_all()` assumption and idempotent upgrade SQL for existing prod DBs (additive nullable columns).
- [x] **F10. UI for policies + capability badges** — admin settings form gains a Runtime Policies section; asset page shows capability/version + run status badge (`fatal` styled red); library generated cards carry a "generated" badge.
- [x] **F11. Reindex concurrency lock** — `reindex_library` guarded per-user by an in-process `_reindex_locks` flag (set for `workers=1` runtime).
- [x] **F12. Multi-tenant `/touch`** — runtime manager `_client_is_authorized` allows loopback OR a config-gated `X-Manager-Secret` (`NC_MANAGER_SECRET`) for external callers (Manager Secret stub for the multi-tenant future).

> Also fixed: `api.py start_run` never defined `run_id` (NameError at run creation) — now generated via `uuid.uuid4().hex` and threaded through keepalive/worker.

## 🧪 Tests added
- `app-alfred/tests/test_pipeline.py` (NEW): pure-logic tests for `_RuntimePolicy`/`_PolicyClock` (max-runtime, idle, token, cost, unbounded), `assert_derivation_has_sources`, `_classify_capability`, `plan_goal_capability` shape, `require_owned_asset` abort, and a DB-backed (`@pytest.mark.integration`) test for capability + input-hash recording.
- F6 added `test_rag_evidence_exempt_from_derivation_validator` proving RAG `Evidence` with empty sources is not blocked by the derivation validator (validator stays scoped to derived-artifact writes in `tools.py`).
- Note: can't run here (see Environment notes blocker). Run in provisioned env.

## ✅ Definition of "done" for a session
- All target items' code compiles (`python3 -m py_compile`).
- New/changed behavior covered by a test in `tests/` (pure-logic preferred when no DB).
- `IMPLEMENTATION_PIPELINE.md` updated (`[ ]`→`[x]`); this file updated (`[~]`/`[ ]`→`[x]`); ARCHITECTURE.md "Implementation Status" updated if behavior changed.

---

## 🧭 Next natural patches (post F1–F12 — forward backlog)

> Resumable across sessions. Each item: what, why, files, suggested test. Order is
> a suggested priority, not a hard sequence. Status legend: `[ ]` not started.

### Correctness / reliability

- [x] **N1. Run-status surfaced in the live UI** — the polling `ask` view now
  shows a live `#run-status-banner` driven by `GET /runs/<id>/events` status
  (`queued`/`running`/`done`/`error`/`fatal`, `fatal` styled red). Implemented in
  `ask.js` (`showRunStatus`) + `ask.html` + `styles.css`. Test:
  `test_run_events_returns_terminal_status` (integration).

- [ ] **N2. Cost model accuracy (F2 follow-up)** — `_usage_from_response` uses a
  flat `$2/1M-token` blended rate, which misprices expensive models. Move the rate
  to a per-model map in `settings_keys.py` (or read from the provider's
  `cost`/`system` fingerprint) so token budgets stay meaningful. Files:
  `alfred/agent/executor.py`, `alfred/settings_keys.py`.

- [ ] **N3. Idle-timeout accuracy** — `_RuntimePolicy._exceeded` computes idle from
  `last_activity` using `datetime.now()`, while wall-clock uses `time.monotonic()`.
  Mixed clocks are fine but the idle check compares against `started_at` semantics;
  add a unit test pinning `last_activity` to prove idle fires after the window with
  no tool calls. Files: `tests/test_pipeline.py`.

- [ ] **N4. Ownership on AssetRelation delete path** — F5 guarded delete + create,
  but there is still **no API endpoint to delete a relation**, and `get_relation_graph`
  is read-only. Add `DELETE /alfred/api/assets/<id>/relations/<to_id>` that verifies
  the user owns *both* sides before removing (prevents orphaned provenance edges on
  another user's data). Files: `alfred/api.py`, `alfred/guards.py`, `tests/`.

- [ ] **N5. Replay needs the stored plan, not a fresh one (F7 follow-up)** — `flask replay`
  re-derives `run.plan`, but the intent of replay is to reproduce the *original*
  compiled plan. Use `run.plan_json` (already persisted) instead of `plan_goal` so a
  planner drift in *planning* (not just the manifest hash) is also replayed faithfully.
  Files: `alfred/cli.py`.

- [ ] **N6. Stale-input guard should be configurable (F8 follow-up)** — today it hard-aborts
  on any change. Add an opt-in `ALFRED_STRICT_INPUT_PIN` (default off) so a changed
  reference downgrades to a warning event instead of `error`, matching the
  "dynamic inputs only" design principle. Files: `alfred/agent/executor.py`,
  `alfred/settings_keys.py`.

### Architecture / scale

- [ ] **N7. Move execution to a queue (post-v1)** — ARCHITECTURE §4b says workers=1 is
  a v1 invariant; the next scale step is a Runtime Process behind a queue
  (Temporal/Celery/Dramatiq) so the web tier can scale independently. Track as a
  design spike; no code yet. Files: `alfred/agent/executor.py`, `keepalive.py`,
  `gunicorn.conf.py`.

- [ ] **N8. Alembic migrations (F9 follow-up)** — replace the `db.create_all()` +
  `migrations/README.md` SQL with a real Alembic setup before the first non-additive
  schema change. Generate an initial migration from the current model. Files:
  `migrations/`, `alfred/__init__.py` (swap `create_all` → `alembic upgrade head`).
  Test: `alembic upgrade head` on a fresh DB matches `create_all()` schema.

- [ ] **N9. Real-time events via SSE/WebSocket** — the live UI polls
  `GET /runs/<id>/events` every Ns. Upgrade to SSE (`text/event-stream`) for lower
  latency and to drop the poll loop. Files: `alfred/api.py`, `ask.html`, `ask.js`.

- [ ] **N10. Embedding-model switch integrity** — changing `alfred_embedding_model`
  leaves old-model vectors in `asset_embedding`; `library_search` already filters by
  active model, but orphaned rows accumulate. Add a janitor/CLI to prune
  non-active-model rows. Files: `alfred/rag/__init__.py`, `alfred/cli.py`.

### Product / UX

- [x] **N11. Capability badges on the library list (F10 follow-up)** — capability +
  run-status badges now appear on generated cards in `library.html` by resolving
  `lineage.generated_by_run` via the existing `alfred_run` template global.
  Files: `templates/alfred/library.html`, `styles.css`. Test:
  `test_library_generated_card_shows_run_badge` (integration).

- [x] **N12. Run history / dashboard** — `/alfred/runs` lists past `AgentRun`s
  (goal, capability, status, tokens, cost), scoped to the user, with status
  filter chips. Re-run affordance links from `error`/`fatal` rows.
  Files: `alfred/routes.py` (`run_history`), `templates/alfred/runs.html`,
  sidebar nav in `ask.html` + `library.html`. Test:
  `test_run_history_route_scoped_to_user` (integration).

- [x] **N17. Janitorial worker (§4 runtime health)** — background daemon thread
  (`alfred/janitor.py`) runs every 60s reconciling the three-system consistency
  model: reaps non-terminal `AgentRun`s, reconciles `indexing` assets (promote to
  `ready`, retry embeddings, or reap orphaned blobs), retries `embedding_pending`
  assets, and prunes embeddings of `superseded` assets. Also exposed as
  `flask janitor [--once|--report]`. Wired into `create_app` (workers=1 safe).
  Test: `test_janitor_reaps_failed_ingest_orphan` (integration).

- [x] **N13. `fatal` recovery affordance** — when a run ends `fatal`/`error`, the live
  banner (N1) and the run-history rows (N12) link to `/alfred/ask?rerun=<run_id>`,
  which prefills the goal and (for `fatal`) sets `relax_bounds`. `start_run` accepts
  `relax_bounds` to force all policy bounds unbounded so a prior breach doesn't
  immediately re-abort. Ties N1 + F1. Files: `ask.html`, `ask.js`, `api.py`,
  `routes.py`, `styles.css`. Tests: `test_relax_bounds_forces_unbounded_policies`,
  `test_ask_rerun_prefills_goal_and_relaxes_fatal` (integration).

### Ops / hardening

- [ ] **N14. `/touch` UDS path (F12 follow-up)** — the Manager Secret stub exists;
  add the Unix Domain Socket variant (manager listens on a socket, Alfred posts
  there) so loopback isn't the only non-secret option. Files:
  `platform-infra/prod-debian/runtime-manager/nightcraft-runtime-manager.py`.

- [ ] **N15. Health-check coverage gap** — `flask check` / fail-fast (F3) does not yet
  verify the *runtime manager* reachability (`RUNTIME_MANAGER_URL`) or that the
  on-demand service can actually `systemctl start`. Add a probe. Files: `alfred/cli.py`.

- [ ] **N16. Secrets management for `NC_MANAGER_SECRET`** — document sourcing the
  manager secret from the secrets store / systemd `EnvironmentFile` rather than a
  process env var; add to `products.yml` + systemd unit. Files:
  `platform-infra/prod-debian/products.yml`, `systemd/nightcraft-alfred.service`.

### Suggested next-session start (lowest risk, highest value)
1. **N1** (run status in live UI) — visible correctness win, reuses existing endpoint.
2. **N3 + N2** (policy test + cost accuracy) — hardens F2/F4 with real coverage.
3. **N4** (relation delete ownership) — closes the last ownership gap from F5.
4. **N11** (capability badges on library list) — rounds out F10 UX.
   *(N12 Run history + N17 Janitorial worker implemented this session.)*

---

## 🧭 Next Natural Patches — Resumable Backlog (for future chat sessions)

> Pick up any item below in a fresh session. Each entry is self-contained:
> **what to do · why · files · suggested test.** Priority order is a suggestion,
> not a hard sequence. Status legend: `[ ]` not started.
> Last curated: 2026-07-20 (after N1 + N11 + N13 landed).

### 🟢 Tier 1 — Visible correctness / UX wins (do first)
- [x] **N1. Run-status banner in live chat UI** — done this session (`ask.js`
  `showRunStatus` + `ask.html` `#run-status-banner` + `styles.css`).
- [x] **N11. Capability badges on library list** — done this session (`library.html`
  generated card badges via `alfred_run`).
- [x] **N13. `fatal` recovery affordance** — done this session (`/alfred/ask?rerun=`
  prefill + `relax_bounds` in `start_run`).
- (Tier 1 complete; remaining open items are Tier 2+. See individual N-entries above.)

### 🟡 Tier 2 — Reliability hardening (close F2/F4/F5/F7/F8 follow-ups)
- **N2. Cost model accuracy** — `_usage_from_response` uses a flat `$2/1M-token`
  blended rate, mispricing expensive models. Move to a per-model map in
  `settings_keys.py` (or read from the provider's cost fingerprint) so token/cost
  budgets stay meaningful. Files: `alfred/agent/executor.py`, `alfred/settings_keys.py`.
- **N3. Idle-timeout accuracy** — add a unit test pinning `last_activity` to prove
  idle fires after the window with no tool calls (mixed `datetime.now()` vs
  `time.monotonic()` clocks noted in N3). Files: `tests/test_pipeline.py`.
- **N4. Ownership on AssetRelation delete path** — F5 guarded delete + create, but
  there is still no API endpoint to delete a relation, and `get_relation_graph` is
  read-only. Add `DELETE /alfred/api/assets/<id>/relations/<to_id>` verifying the
  user owns *both* sides. Files: `alfred/api.py`, `alfred/guards.py`, `tests/`.
- **N5. Replay uses stored plan, not a fresh one** — `flask replay` re-derives
  `run.plan`; use `run.plan_json` (already persisted) so planner drift in *planning*
  is replayed faithfully, not just manifest-hash drift. Files: `alfred/cli.py`.
- **N6. Stale-input guard configurable** — F8 hard-aborts on any change. Add opt-in
  `ALFRED_STRICT_INPUT_PIN` (default off) so a changed reference downgrades to a
  warning event instead of `error`. Files: `alfred/agent/executor.py`,
  `alfred/settings_keys.py`.

### 🟠 Tier 3 — Scale / architecture spikes (post-v1, design first)
- **N7. Execution behind a queue** — ARCHITECTURE §4b says workers=1 is a v1
  invariant; next scale step is a Runtime Process behind a queue (Temporal/Celery/
  Dramatiq) so the web tier scales independently. Design spike; no code yet.
  Files: `alfred/agent/executor.py`, `keepalive.py`, `gunicorn.conf.py`.
- **N8. Alembic migrations** — replace `db.create_all()` + `migrations/README.md`
  SQL with real Alembic before the first non-additive schema change. Generate an
  initial migration from current models. Test: `alembic upgrade head` on a fresh DB
  matches `create_all()` schema.
- **N9. SSE/WebSocket for live events** — replace the `GET /runs/<id>/events` poll
  loop with `text/event-stream` for lower latency. Files: `alfred/api.py`, `ask.html`,
  `ask.js`.
- **N10. Embedding-model switch integrity** — changing `alfred_embedding_model`
  leaves old-model vectors in `asset_embedding`. Add a janitor/CLI prune (the N17
  janitor already prunes `superseded`; extend it or add `flask janitor --prune-embeddings`).
  Files: `alfred/rag/__init__.py`, `alfred/cli.py` / `alfred/janitor.py`.

### 🔵 Tier 4 — Ops / hardening
- **N14. `/touch` UDS path** — F12 added a Manager Secret stub; add the Unix Domain
  Socket variant (manager listens on a socket, Alfred posts there) so loopback isn't
  the only non-secret option. Files: `platform-infra/prod-debian/runtime-manager/…`.
- **N15. Health-check coverage gap** — `flask check` / fail-fast (F3) doesn't yet
  verify runtime-manager reachability (`RUNTIME_MANAGER_URL`) or that the on-demand
  service can `systemctl start`. Add a probe. Files: `alfred/cli.py`.
- **N16. Secrets management for `NC_MANAGER_SECRET`** — source the manager secret
  from the secrets store / systemd `EnvironmentFile`, not a process env var; update
  `products.yml` + systemd unit. Files: `platform-infra/prod-debian/products.yml`,
  `systemd/nightcraft-alfred.service`.

### Recommended multi-session plan
- **Session A:** N1 + N11 + N13 (visible UX completion of F10/N12) — DONE.
- **Session B:** N3 + N2 + N4 (reliability hardening, real test coverage).
- **Session C:** N5 + N6 (replay/input-pin fidelity).
- **Session D:** N10 (embeddings prune) + N15 (health probe) — ops hygiene.
- **Later:** N7/N8/N9 (scale spikes) when traffic justifies it.

> Definition of "done" per session: code compiles (`py_compile`), behavior covered
> by a test in `tests/` (pure-logic preferred; `@pytest.mark.integration` for DB),
> and this checklist + ARCHITECTURE "Implementation Status" updated.

