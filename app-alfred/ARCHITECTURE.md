# Alfred: Final Architecture Plan

> **Product name: Alfred.** The previous working names *Butler* and *SeekSage* are
> retired. There is no Butler or SeekSage anymore — it is Alfred now.

## 1. System Overview

**Product:** Persistent, artifact-centric AI workspace. Core question:
*Given existing artifacts + request, what new artifact?*

**Metaphor:** Workflow OS. Borrow process / task / memory / driver patterns.
Reject mutex / semaphore / VM.

**Non-goals:** Out-chatting ChatGPT, out-searching Perplexity, general-purpose
agent, autonomous "felt important" behavior.

## 2. Layer Stack (Eight Layers, Final)

```
┌─────────────────────────────────────────┐
│  Layer 0: User Interface                 │
│  Chat, Library, Task Dashboard           │
└─────────────────────────────────────────┘
                    │
                    ▼
┌─────────────────────────────────────────┐
│  Layer 1: Conversation Layer             │
│  Extractor: LLM with narrow contract     │
│  - Identifies intents, ambiguities,      │
│    possible tasks, clarifications        │
│  - Bias: false negatives over false      │
│    positives                             │
│  - Never invents plans                   │
│  - Ambiguity → Clarification node in     │
│    Intent IR (not failure)               │
└─────────────────────────────────────────┘
                    │
                    ▼
┌─────────────────────────────────────────┐
│  Layer 2: Intent IR + Retrieval          │
│  Intent IR: Structured AST (not NL)      │
│  - LLM produces Intent IR only           │
│  - Compiler is deterministic             │
│  Retrieval: Evidence-based planning      │
│  - Metadata filter → semantic search    │
│    → ranking → evidence for plan          │
│  - Retrieval BEFORE planning             │
└─────────────────────────────────────────┘
                    │
                    ▼
┌─────────────────────────────────────────┐
│  Layer 3: Compiler + Policy Engine        │
│  Compiler: Intent IR + evidence →        │
│  Execution Plan                          │
│  Policy Engine: in-process subroutine    │
│  - Hard policies: constraints (always    │
│    enforced, can reject plan)            │
│  - Soft policies: optimization           │
│    objectives (scored, not blocking)    │
│  - Synchronous invocation, <1ms latency  │
└─────────────────────────────────────────┘
                    │
                    ▼
┌─────────────────────────────────────────┐
│  Layer 4: Execution Plan                 │
│  Frozen intent, dynamic inputs           │
│  Template-based queries (not LLM-         │
│  rewritten each run)                     │
│  Primitives: Sequence, Parallel,         │
│  Conditional, Wait, Retry, Poll          │
│  - Deliberately non-Turing-complete      │
│  - Poll: bounded (max iterations/        │
│    timeout), not general loop            │
└─────────────────────────────────────────┘
                    │
                    ▼
┌─────────────────────────────────────────┐
│  Layer 5: Capability Runtime             │
│  Capabilities: Search, Editor, Codex     │
│  Each: manifest, operations, tool        │
│  selection, retry metadata               │
│  - Capability→Tool mapping: Capability   │
│    owns it, not Planner                  │
│  - Planner never sees Serper/Tavily/     │
│    Aider (like device driver)            │
└─────────────────────────────────────────┘
                    │
                    ▼
┌─────────────────────────────────────────┐
│  Layer 6: Runtime Infrastructure         │
│  Scheduler, Logs, Storage,               │
│  Notifications, Credentials              │
│  "Intentionally stupid" executor          │
│  - Executes plan, doesn't reason          │
│  - Interprets retry metadata from        │
│    Capability manifest                   │
│  - Runtime executes loop, Capability     │
│    defines rules                         │
└─────────────────────────────────────────┘
                    │
                    ▼
┌─────────────────────────────────────────┐
│  Layer 7: Artifacts                      │
│  Filesystem: blobs (reports, docs,       │
│  images)                                 │
│  SQLite: metadata, lineage, tasks,       │
│  runs, policies, sessions, full-text     │
│  Vector Index: embeddings                │
│  Every artifact has:                     │
│  - Parents, Task, Capability             │
│  - Origin Conversation, Execution Run    │
│  - User, Validity, Coverage              │
│  Lineage: first-class, not reconstructed │
└─────────────────────────────────────────┘
```

## 3. Core Decisions (Final, All Rounds)

| #  | Decision                                                                                                     | Rationale                                                                      | Status  |
| -- | ------------------------------------------------------------------------------------------------------------ | ------------------------------------------------------------------------------ | ------- |
| 1  | One product, multiple modes (Search/Editor/Codex) as shared workspaces                                       | Not separate products; shared Library/Tasks/KB                                 | ✅ Final |
| 2  | Human-in-the-loop: approve at creation, freeze plan                                                          | Prevents plan drift; dynamic inputs only                                       | ✅ Final |
| 3  | Cross-modal tasks as pipelines                                                                               | Sequential/parallel/conditional, not DAGs                                      | ✅ Final |
| 4  | Knowledge Base: multi-index (files, reports, conversations, structured data, embeddings, relationships)      | Metadata filter → semantic search → ranking                                    | ✅ Final |
| 5  | Failure classification: Retryable/Recoverable/Fatal                                                          | Different handling per class                                                   | ✅ Final |
| 6  | Start as personal AI OS, defer SaaS                                                                          | Lower complexity, room for team features later                                 | ✅ Final |
| 7  | Continuous feedback loop: Knowledge Loop + Preference Loop                                                   | Explicit user preferences, not model weights                                   | ✅ Final |
| 8  | Capabilities as abstraction over tools                                                                       | Capability Runtime chooses tools, Planner doesn't know them                    | ✅ Final |
| 9  | Capability→Tool mapping: Capability Runtime owns it, not Planner                                             | Planner never sees Serper/Tavily; like device driver                           | ✅ Final |
| 10 | Task graph primitives: Sequence, Parallel, Conditional, Wait, Retry, Poll                                    | Deliberately ban general loops                                                 | ✅ Final |
| 11 | Artifact metadata: core schema + capability extensions                                                       | Planner understands core; capability logic stays inside                        | ✅ Final |
| 12 | Artifact validity: Complete/Partial/Failed/Superseded + coverage %                                           | Planner can reason about artifact quality                                      | ✅ Final |
| 13 | Checkpoints: store full conversation (like Git commit), summary is optimization                              | Source of truth is full snapshot                                               | ✅ Final |
| 14 | Policies: Hard vs. Soft, enforced by dedicated layer                                                         | Hard always wins; Soft are optimization objectives                             | ✅ Final |
| 15 | Design for team-ready: Artifact IDs, Task IDs, User IDs, Capability interfaces, Storage abstraction          | Defer RBAC, billing, quotas                                                    | ✅ Final |
| 16 | Notifications: Runtime service, not Capability                                                               | Infrastructure, not reasoning                                                  | ✅ Final |
| 17 | OS metaphor: workflow OS, not general-purpose                                                                | Borrow process/task/memory/driver patterns; reject mutex/semaphore/VM          | ✅ Final |
| 18 | LLM produces Intent IR, not executable plans                                                                 | Compiler is deterministic; LLM only writes intent                              | ✅ Final |
| 19 | Intent IR as structured AST, not natural language                                                            | Like SQL parser → compiler → execution                                         | ✅ Final |
| 20 | Capabilities expose operation catalog (manifest)                                                             | LLM selects from schema'd operations, doesn't invent them                      | ✅ Final |
| 21 | Query generation: templates, not LLM-rewritten each run                                                      | `Topic/Audience/Window/Ranking` filled at execution time                       | ✅ Final |
| 22 | Poll as primitive with max iterations/timeout, not general loop                                              | Bounded, not Turing-complete                                                   | ✅ Final |
| 23 | Retrieval before Planning                                                                                    | Evidence-based plan construction                                               | ✅ Final |
| 24 | Rehydration: checkpoint → context, never dump 200 messages                                                   | Selective context loading                                                      | ✅ Final |
| 25 | Conversation Layer above Intent IR                                                                           | Humans write requests, not intent; extractor resolves ambiguity                | ✅ Final |
| 26 | Artifact-centric, not Task-centric                                                                           | Tasks transform artifacts; artifacts are the primitive                         | ✅ Final |
| 27 | Chat requests ≠ workflows; explicit transition required                                                      | "Every Friday summarize PDFs" is workflow; "Summarize this PDF" is chat        | ✅ Final |
| 28 | Alfred = artifact-centric knowledge operating system                                                         | Core question: given existing artifacts + request, what new artifact?          | ✅ Final |
| 29 | Alfred/Alfred are the same product                                                                           | Naming alias, no architectural impact                                          | ✅ Final |
| 30 | Conversation Extractor: LLM with narrow contract, bias toward false negatives                                | Only identifies intents/ambiguities/tasks, never invents plans                 | ✅ Final |
| 31 | Artifact lineage: first-class, not reconstructed                                                             | Every artifact knows parents, task, capability, origin conversation, run, user | ✅ Final |
| 32 | Chat → Workflow: right-click/long-press on reply, explicit user gesture                                      | Extractor may suggest, never auto-creates                                      | ✅ Final |
| 33 | Proactive behavior: approved triggers only, never autonomous                                                 | Time, calendar, file, price, email, git — no "felt important"                  | ✅ Final |
| 34 | Storage: Filesystem (blobs) + SQLite (metadata/lineage/tasks) + Vector Index (embeddings)                    | Three concerns: content, relationships, similarity                             | ✅ Final |
| 35 | "Aha" moment: memory with provenance, not scheduling or approval                                             | System already knows, user doesn't re-establish context                        | ✅ Final |
| 36 | Product thesis: persistent workspace where work becomes connected, reusable knowledge with traceable lineage | Not out-chatting ChatGPT or out-searching Perplexity                           | ✅ Final |
| 37 | Policy Engine as Compiler subroutine (in-process)                                                            | Synchronous, <1ms latency; not separate service                                | ✅ Final |
| 38 | Storage consistency: WAL + janitorial worker                                                                 | SQLite/Filesystem atomic; Vector Index eventual                                | ✅ Final |
| 39 | False negative UX: Clarification as first-class plan node                                                    | Not failure; Compiler generates AskUser → Wait → Recompile                     | ✅ Final |
| 40 | Retry ownership: Runtime executes loop, Capability defines rules via manifest                                | Runtime "stupid" but capable of interpreting metadata                          | ✅ Final |

## 4. Storage & Consistency Model

### Three Systems, One Transaction

```
┌─────────────────────────────────────────┐
│  Write-Ahead Log (SQLite)                │
│  ─────────────────────────────────────  │
│  BEGIN TRANSACTION                       │
│    INSERT artifact_metadata (status='pending') │
│    INSERT file_path_reference            │
│  Write blob to Filesystem                │
│  UPDATE artifact_metadata (status='complete') │
│  COMMIT                                  │
│                                          │
│  [Async] Vector Index worker:            │
│    Polls for 'complete' unindexed        │
│    Generates embedding                   │
│    INSERT into Vector Index              │
│    UPDATE artifact_metadata (status='indexed') │
└─────────────────────────────────────────┘
```

### Artifact Validity States

| State        | Description                               | Janitor Action                          |
| ------------ | ----------------------------------------- | --------------------------------------- |
| `Pending`    | WAL entry created, blob not written       | >30s: check blob, reconcile or delete   |
| `Complete`   | Blob + metadata committed, not indexed    | Normal; await indexer                   |
| `Indexed`    | Fully consistent across all three systems | Terminal state                          |
| `Partial`    | Blob exists, metadata incomplete          | Attempt completion or mark `Failed`     |
| `Failed`     | Write failed, blob may be orphaned        | Clean up blob, mark metadata            |
| `Superseded` | Newer version exists                      | Retain for lineage, exclude from search |

### Janitorial Worker
- Runs every 60 seconds
- SQLite / Filesystem: strongly consistent (transactional)
- Vector Index: eventually consistent (seconds lag acceptable)

## 4b. Runtime Deployment & Operational Policies (Review Findings)

> The following items were raised in an architecture review of the runtime and
> execution model. They are tracked here so the design reflects deployment
> reality, not just the logical layer stack.

### Deployment Invariant: Gunicorn Workers = 1 (🔴 Priority 1)

The runtime is **single-process by assumption**:

```
HTTP request
    ↓
Gunicorn Worker
    ↓
Background Thread
    ↓
In-memory Run State
```

The keepalive timer, background thread, active run, and locks are all
**process-local**. With `workers = 2` you get `Worker A` / `Worker B` with
`stateA != stateB` — a classic WSGI mistake.

**Decision (v1):** Pin `gunicorn --workers=1` as a **hard deployment invariant**.
Document it in deployment config and reject multi-worker configs. *(Confirmed:
keep workers=1 for v1; revisit with queue-based runtime later.)*

**Future (post-v1):** Move execution into a dedicated Runtime Process behind a
Queue (Temporal / Celery / Dramatiq pattern) so the web tier can scale
independently of execution state.

### Runtime Policies: Idle Timeout + Maximum Runtime (🔴 Priority 2)

Current design has an **idle timeout** but no **maximum runtime**. These are
different policies. Runtime must enforce all of:

- **Idle Timeout** — no progress within window → terminate.
- **Maximum Runtime** — hard wall-clock cap per run.
- **Maximum Token Budget** — cap spend per run.
- **Maximum Cost** — cap dollar spend per run.

### Startup Health Check (🟢 Priority 12)

Runtime must **fail fast at startup** before serving requests:

```
Provider Health Check
    ↓
API Keys
    ↓
Embedding Model
    ↓
Storage
    ↓
Capabilities
```

Missing `requests` dependency is a missing-package bug (not architecture) —
add to requirements.

### Operational Security: `/touch` Authentication (🟠 Priority 4)

Classified as **Operational Security**, not architecture.

- v1: `127.0.0.1` only is acceptable on a personal VPS.
- If Alfred becomes multi-tenant, add one of: Manager Secret, Unix Domain
  Socket, or mTLS. Not worth complicating v1.

### Evidence & Provenance Enforcement (🟠 Priority 5)

The plan states *provenance mandatory*, but enforcement currently relies on
**executor promises** rather than **schema guarantees**. The architecture must
distinguish three concerns:

- **Policy** — declares provenance is required.
- **Validation** — schema-enforced at the boundary, not developer discipline.
- **Persistence** — stored as first-class lineage fields.

If provenance is fundamental, it must be enforced structurally, not by
convention.

### Asset Isolation / Ownership (🟠 Priority 6)

The `Relation` table (`from_id`, `to_id`) does not express ownership. The
runtime must **never trust `asset_id` coming from the client**. Before any
lowering operation, the runtime verifies:

```
asset.owner == current_user
```

### LangGraph Checkpointer Clarification (🟡 Priority 7)

Documentation drift: "persistent checkpoint" was stated without definition.

- **Default:** `PostgresSaver`
- **Optional:** `MemorySaver`
- **Unsupported:** Redis

### Reindex Without Downtime (🟡 Priority 8)

Do **not** pause search during reindex. *(Confirmed: atomic swap approach for
v1.)* Use an atomic pointer swap:

```
Embedding Set A (active)
    ↓ Build
Embedding Set B
    ↓ Atomic pointer swap
Search queries Set B
    ↓ Delete A
```

Search always queries exactly one embedding generation. Partial indexes are
never exposed.

### `workspace_id` — Remove Speculative Column (🟡 Priority 9)

The model (User owns Workspace / Workspace owns User / Shared Org / ACL) is
undecided. Carrying speculative columns hurts. **Decision (v1): keep
`workspace_id` as a nullable, unused column** for forward compatibility; do not
build logic around it. Design collaboration when it actually arrives.

### Binary Edits — Explicit Product Rule (🟡 Priority 10)

Not an architecture bug; a **product decision**. Rule:

```
DOCX
    ↓ Editor
Markdown
    ↓ New Asset
Original preserved
```

UI must state *"Generated markdown version — original DOCX unchanged."* No
surprises.

## 4c. Execution Determinism Gaps (Raised in Review — Confirmed, Add Both)

Two gaps larger than several items above. *(Confirmed: add both as first-class
requirements for v1.)*

### Capability Versioning

Manifests will evolve: `Editor` → `Editor v1` / `Editor v2` / `Editor Local` /
`Editor Remote`. Execution must record **which capability + version compiled
the graph**, otherwise replay is nondeterministic.

Each executed run stores:

- **Capability** name
- **Version**
- **Manifest Hash**

### Artifact Version Pinning

Currently bound to `artifact_id` but not `artifact_version`. Risk:

```
Compile
    ↓ User edits report
Runtime executes  → Wrong input
```

 Semantic resolution must bind **`artifact_id` + `content_hash` (or revision)**
 at resolution time, not at compile time.

 ### Implementation Status (tracked in `IMPLEMENTATION_PIPELINE.md`)

 The review findings above are now implemented in code (see
 `IMPLEMENTATION_PIPELINE.md` for per-item flags):

 - **Workers = 1:** `app-alfred/gunicorn.conf.py` pins `workers = 1` and rejects
   multi-worker overrides; `systemd/nightcraft-alfred.service` + `products.yml`
   set `workers: 1`.
 - **Runtime policies:** `AgentRun` carries `max_runtime_seconds`,
   `idle_timeout_seconds`, `token_budget`, `cost_budget_usd`; the executor
   ReAct loop (`alfred/agent/executor.py`) aborts with status `fatal` on breach.
 - **Startup health check:** `flask check` verifies providers → API key →
   embedding model → storage → pgvector and exits non-zero on failure.
 - **`/touch` auth:** runtime manager (`nightcraft-runtime-manager.py`) rejects
   non-loopback `/touch` callers (403); multi-tenant future noted (Manager
   Secret / UDS / mTLS).
 - **Evidence enforcement:** `assert_derivation_has_sources()` in `alfred/models.py`
   rejects a derived artifact write when `Evidence.sources` is empty.
 - **Asset isolation:** `require_owned_asset()` in `alfred/guards.py` is applied
   to run-start referenced assets, ingest, and relation creation.
 - **Capability + artifact versioning:** `AgentRun` records `capability`,
   `capability_version`, `manifest_hash` (planner) and `run_input_hash`
   (input pinned at run-start, not compile time).
 - **Reindex atomic swap:** `reindex_library()` builds a temp generation, then
   swaps in a single transaction — search never sees a partial index.
 - **Binary-edit rule:** DOCX/original ingest is flagged `original_preserved`;
   generated reports are flagged `is_generated_version` and the asset page shows
   "Generated markdown version — the original asset is unchanged."
 - **`workspace_id`:** remains a nullable, unused column (no logic built around
   it).

 ## 5. Capability Runtime: Framework Heterogeneity

**Principle:** Capabilities may use different internal harnesses. The
Planner / Compiler / Runtime do not know.

```
┌─────────────────────────────────────────┐
│  Capability Runtime                      │
│  ─────────────────────────────────────  │
│  ┌─────────────┐  ┌─────────────────┐   │
│  │  Search     │  │  Editor         │   │
│  │  Harness:   │  │  Harness:       │   │
│  │  Custom     │  │  Custom         │   │
│  │  HTTP client│  │  File ops       │   │
│  │  (simple)   │  │  wrapper        │   │
│  └─────────────┘  └─────────────────┘   │
│                                         │
│  ┌─────────────────────────────────┐   │
│  │  Codex Capability               │   │
│  │  Harness: Aider (or PI)         │   │
│  │  ─────────────────────────────  │   │
│  │  Internal: multi-turn, git      │   │
│  │  branches, test execution       │   │
│  │  External surface:              │   │
│  │    operation: code_edit         │   │
│  │    inputs: {repo_path,          │   │
│  │              instruction,       │   │
│  │              test_cmd,          │   │
│  │              max_iterations}    │   │
│  │    outputs: {diff, test_results,│   │
│  │              success}           │   │
│  │    retry: {max_retries,         │   │
│  │             retryable_errors,   │   │
│  │             fatal_errors}       │   │
│  └─────────────────────────────────┘   │
└─────────────────────────────────────────┘
```

### Capability Manifest Schema

```json
{
  "name": "codex",
  "operations": {
    "code_edit": {
      "description": "Edit code in a repository",
      "inputs": {
        "repo_path": {"type": "string", "required": true},
        "instruction": {"type": "string", "required": true},
        "test_cmd": {"type": "string", "required": false},
        "max_iterations": {"type": "integer", "default": 3}
      },
      "outputs": {
        "diff": {"type": "string"},
        "test_results": {"type": "string", "nullable": true},
        "success": {"type": "boolean"},
        "error_class": {"type": "string", "enum": ["retryable", "fatal", "max_iterations"]}
      },
      "retry_metadata": {
        "max_retries": 2,
        "backoff": "exponential",
        "retryable_errors": ["timeout", "rate_limit", "transient"],
        "fatal_errors": ["auth_error", "compilation_error", "test_failure"]
      },
      "harness": {
        "type": "subprocess",
        "command": "aider --model {model} --message-file {instruction_file} {repo_path}",
        "timeout_seconds": 300
      }
    }
  }
}
```

## 6. MVP Phases

### Phase 0: Mock Loop (Weeks 1-2)
Goal: Prove layer boundaries. User types request → AST → plan → mocked execution.

| Component          | Implementation                                         |
| ------------------ | ------------------------------------------------------ |
| UI                 | Static HTML, text input + display                      |
| Conversation Layer | Hardcoded extractor (regex + simple LLM prompt)        |
| Intent IR          | JSON schema, no custom parser                          |
| Compiler           | Hardcoded: if intent == "search", plan = [MockSearch]  |
| Policy Engine      | One hard policy: "MockSearch only"                     |
| Execution Plan     | Single `Sequence` primitive                            |
| Capability Runtime | One mock tool: returns "Mock result for {query}"       |
| Artifacts          | In-memory only                                         |

Success criteria: End-to-end data flow through all layers.

### Phase 1: Real Conversation + Compiler
- Real LLM-based Extractor with Clarification node
- Real Intent IR parser
- Template-based query generation
- SQLite metadata storage (no Vector Index)

### Phase 2: Real Capability + Retrieval
- One real capability (Search) with one real tool
- Retrieval layer: metadata filter only
- Filesystem blob storage
- WAL + janitorial worker

### Phase 3: Full Architecture
- Vector Index for semantic search
- Multiple capabilities
- Full policy engine
- Background janitorial worker
- Codex Capability with Aider harness

### Deferred (Post-MVP)
- Parallel / Conditional / Wait / Retry / Poll primitives (Phase 1: Sequence only)
- Team features (RBAC, shared workspaces)
- Notifications service
- Proactive triggers (calendar, file watchers, git hooks)
- Full checkpoint rehydration
- Soft policy optimization scoring

## 7. Anti-Patterns (Explicitly Forbidden)

| Anti-Pattern                                  | Why Forbidden                          |
| --------------------------------------------- | -------------------------------------- |
| Planner generates tool-specific commands      | Violates capability abstraction        |
| Compiler has special-case "coding" plan nodes | Compiler must remain generic           |
| Runtime inspects which harness is running     | Runtime must be "intentionally stupid" |
| Shared state between capabilities             | Violates isolation                     |
| LLM rewrites queries each run                 | Must use templates for reproducibility |
| General loops in execution plan               | Must use bounded Poll primitive        |
| Autonomous task creation                      | Explicit user gesture only             |
| "Felt important" proactive behavior           | Approved triggers only                 |
| Multi-worker Gunicorn in v1                   | workers=1 is a hard deployment invariant |
| Trusting client-supplied `asset_id` ownership | Runtime verifies `asset.owner==current_user` |
| Provenance enforced by convention             | Schema-validated at boundary, not promises |
| Reindex pauses search                          | Atomic swap of embedding sets, never pause |
| Binding `artifact_id` without version         | Pin `artifact_id` + `content_hash` at resolution |
| Executing capability without version record    | Store capability + version + manifest hash |

## 8. Success Metrics

| Metric                        | Target                                      |
| ----------------------------- | ------------------------------------------- |
| Plan compilation latency      | <500ms (excluding LLM call)                 |
| Policy evaluation latency     | <1ms                                        |
| Artifact write consistency    | 99.9% (SQLite + Filesystem)                 |
| Vector index lag              | <5 seconds (acceptable)                     |
| False positive task creation  | <1% (extractor bias)                        |
| Clarification resolution rate | >95% (user completes multi-choice)          |
| Capability swap time          | <1 day (change harness, no Planner changes) |
