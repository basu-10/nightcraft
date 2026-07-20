# Alfred Runtime Review — Implementation Pipeline

> Cross-session checklist. Derived from the architecture review (ARCHITECTURE.md
> §4b/§4c) and the current `app-alfred/` codebase state.
> Each item: priority, file(s) to touch, done flag `[ ]`→`[x]`.

## Context (read before starting)
- Repo root: `nightcraft/app-alfred/`
- Key files: `alfred/models.py` (Asset, AssetRelation, Evidence, AgentRun),
  `alfred/agent/executor.py` (ReAct loop), `alfred/agent/planner.py` (plan),
  `alfred/api.py` (run lifecycle, ingest, relations), `alfred/keepalive.py`
  (process-local timer), `alfred/guards.py`, `run.py`, `requirements.txt`.
- Confirmed v1 decisions: workers=1; workspace_id kept nullable/unused;
  reindex = atomic swap; add Capability Versioning + Artifact Version Pinning.

---

## 🔴 P1 — Highest priority

- [x] **1. Gunicorn workers = 1 (deployment invariant)**
  - Add `gunicorn.conf.py` (or systemd unit) with `workers = 1`, `bind`,
    `timeout`. Document in prod unit. Code already single-process by assumption
    (`keepalive.py` globals, in-memory `_active_timers`).
  - Files: `app-alfred/gunicorn.conf.py`, `platform-infra/prod-debian/*` unit.
  - Verify: prod startup uses `--workers=1`; reject multi-worker configs.

- [x] **2. Runtime policies: idle timeout + max runtime (+ token/cost budget)**
  - Add to `AgentRun` (`alfred/models.py`): `max_runtime_seconds`,
    `token_budget`, `cost_budget` (nullable).
  - In `alfred/agent/executor.py` ReAct loop: track elapsed wall-clock; abort
    with `Fatal` status when exceeded. Track last-activity ts for idle timeout.
  - Files: `alfred/models.py`, `alfred/agent/executor.py`.
  - Verify: long run is terminated; idle run terminated; unit test with fake
    clock.

## 🟠 P2 — Important

- [x] **3. `/touch` authentication (operational security)**
  - Restrict Runtime Manager touch endpoint to `127.0.0.1` only (manager-side,
    `platform-infra`). Document multi-tenant future: Manager Secret / UDS / mTLS.
  - Files: `platform-infra/prod-debian/*` (manager endpoint), `alfred/keepalive.py`
    (already posts to 127.0.0.1:5700).
  - Verify: external-origin POST to /touch rejected.

- [x] **4. Evidence enforcement (schema, not promises)**
  - `Evidence` model exists. Add boundary validator: reject final artifact write
    if `lineage` claims derivation but `Evidence.sources` is empty.
  - Files: `alfred/models.py`, `alfred/api.py` / `alfred/agent/executor.py`
    (artifact write path).
  - Verify: derived artifact without provenance is rejected at write boundary.

- [x] **5. Asset isolation / ownership**
  - Add `require_owned_asset(asset_id, user)` helper; verify
    `asset.user_id == current_user.user_id` before lowering/using.
  - Apply in `alfred/api.py`: run-start (`referenced_asset_ids`), ingest,
    relation creation endpoints.
  - Files: `alfred/api.py` (new helper in `alfred/guards.py` or `alfred/models.py`).
  - Verify: client-supplied foreign `asset_id` is rejected.

## 🟡 P3 — Correctness / drift

- [x] **6. LangGraph checkpointer clarification (docs)**
  - In `ARCHITECTURE.md` §5 area, one sentence: Default `PostgresSaver`,
    Optional `MemorySaver`, Redis unsupported. (Mostly already noted; confirm.)
  - Files: `app-alfred/ARCHITECTURE.md`.

- [x] **7. Reindex without downtime (atomic swap)**
  - Vector index worker: build new embedding set B, atomically swap pointer
    (`active_embedding_set` row / version key / symlink), delete A. Never expose
    partial index; search always queries one generation.
  - Files: `alfred/ingest/*` (index worker), `alfred/rag/*`.
  - Verify: search returns consistent results mid-reindex.

- [x] **8. `workspace_id` — keep nullable/unused**
  - Confirm column stays nullable in `Asset`/`AgentRun`; no logic built around
    it. (Already nullable.) Document defer.
  - Files: `alfred/models.py` (no change needed except comment), `ARCHITECTURE.md`.

- [x] **9. Binary edits — explicit product rule**
  - DOCX ingest: emit new markdown `Asset`, preserve original. Surface
    "Generated markdown version — original unchanged" in UI.
  - Files: `alfred/ingest/*`, `app-alfred/templates/*`.
  - Verify: original DOCX blob untouched; new asset flagged as generated version.

## 🟢 P4 — Hygiene

- [x] **10. `requests` dependency**
  - Already in `requirements.txt` (2.32.3). Confirm import works; no action
    unless missing. (Review item was "missing dep" — verify present.)

- [x] **11. Startup health check (fail fast)**
  - In `create_app` post-init or `alfred/cli.py check`: verify providers → API
    keys → embedding model → storage → capabilities; abort before serving if any
    fail.
  - Files: `alfred/__init__.py` (create_app), `alfred/cli.py`.
  - Verify: missing API key → startup error, no serve.

- [x] **12. Documentation drift sweep**
  - Reconcile ARCHITECTURE.md with actual code (layer stack vs implemented
    routes/agent). No architecture change.
  - Files: `app-alfred/ARCHITECTURE.md`.

## ⭐ Missed gaps (confirmed: add both)

- [x] **13. Capability Versioning**
  - Add `capability`, `capability_version`, `manifest_hash` to `AgentRun`;
    populate at plan time in `alfred/agent/planner.py`.
  - Files: `alfred/models.py`, `alfred/agent/planner.py`.
  - Verify: each run records which capability+version+manifest hash compiled it.

- [x] **14. Artifact Version Pinning**
  - Add `content_hash` (or `revision`) to run-input binding / `AssetRelation`
    so input is pinned at resolution time, not compile time.
  - Files: `alfred/models.py`, `alfred/agent/planner.py`, `alfred/api.py`.
  - Verify: user edit after compile does not change executed input.

---

## Suggested first commits (lowest risk, highest priority)
1. #5 Asset isolation + #2 Runtime policies skeleton (pure app-alfred, no ext deps).
2. #1 workers=1 config + #11 startup health check.
3. #13 + #14 versioning (determinism).
4. #7 reindex atomic swap, #4 evidence enforcement, #3 /touch auth.
5. #9 binary rule, #6/#8/#10/#12 docs + hygiene.

## Verification conventions
- Tests live in `app-alfred/tests/`. Add a test per item where feasible.
- Run: `cd app-alfred && python -m pytest`.
- Lint/typecheck: check repo for configured command before committing.
