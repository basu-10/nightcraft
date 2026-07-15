# Green Pledge → On-Demand via a Nightcraft Runtime Manager

## Goal
Convert **only** Green Pledge to `on_demand` startup, leaving every other Nightcraft
product (auth, landing, admin, note, tinyxl, game, artsy/neera, radio, …) completely
unchanged. This is an **infrastructure / deployment refactor only** — the Green Pledge
application code, repo, venv, DB, and systemd `.service` file stay byte-for-byte identical;
only its **startup policy** changes.

Proof-of-concept: the same pattern later applies to Artsy, Game, DevRadio, etc. by **adding
a manifest entry** (plus a one-time nginx `include`).

## Key decision: mechanism
**A small always-on Runtime Manager built around systemd + a manifest.** NOT socket
activation.

Why not socket activation:
- Gunicorn has **no native systemd socket-activation support** (upstream PR #487 never
  merged). Real socket activation would need an fd-passing wrapper or `systemd-socket-proxyd`
  — more invasive to the app runtime and changes the service file.
- Socket activation **cannot naturally express idle-shutdown** (an explicit requirement);
  it starts on first connection but has no "stop after N minutes idle" without a separate
  watcher anyway.
- The requirements explicitly ask for two policies (`always_on`, `on_demand`), start on
  first request, refresh `last_access` per request, **auto-stop after a configurable idle
  timeout**, per-product idle timeout in the manifest, manifest-driven, and "prefer a simple
  manager around systemd services." A manager satisfies all of this cleanly.

### Runtime flow (on_demand product, e.g. Green Pledge)
```
Browser ─▶ nginx
              ├─ always_on products: proxy normally (UNCHANGED, hand-written blocks)
              └─ on_demand / generated products (e.g. /pledge/):
                    ├─ mirror ─▶ Runtime Manager  /touch/green
                    │              • last_access[green] = now
                    │              • if service inactive → systemctl start nightcraft-pledge.service
                    ├─ proxy ─▶ app_pledge_upstream (127.0.0.1:5300)
                    │     ├─ service up   → served normally
                    │     └─ service down → 502 → error_page → 302 → branded loading page
                    └─ loading page JS polls /_nc_probe/green (also mirrored → self-heals start)
                        on 200 → redirect to /pledge/

Runtime Manager (always-on, 127.0.0.1:5700, run as root, Restart=always):
   • GET/POST /touch/<slug> → record access (lock) + lazily start on_demand service
   • GET /healthz           → liveness
   • startup: seed last_access=now for every currently-active on_demand service
   • background sweep every 30s: for each on_demand service that is active and
     (now - last_access[slug]) > idle_timeout → systemctl stop <service>
```
The user **never sees a raw 502/503**: cold hits are intercepted and shown a branded
loading page that retries and redirects once the manager has started the service.

## Manifest (authoritative registry)
New file `platform-infra/prod-debian/products.yml`. Extended schema:

```yaml
products:
  auth:
    display_name: Authentication
    slug: auth
    runtime:
      policy: always_on
      service: nightcraft-auth.service
      port: 5100
      workers: 3
  green:
    display_name: Green Pledge
    slug: green
    public_paths: [/pledge, /green-pledge]      # nginx generates blocks for these paths
    runtime:
      policy: on_demand
      service: nightcraft-pledge.service
      port: 5300
      workers: 3            # keep current production value; tune to 1 later if desired
      idle_timeout: 15m
  radio:   { display_name: DevRadio, slug: radio,   runtime: { policy: always_on, service: nightcraft-radio.service,    port: 5333, workers: 1 } }
  neera:   { display_name: Artsy,   slug: neera,   runtime: { policy: always_on, service: nightcraft-neera.service,    port: 5600, workers: 2 } }
  landing: { display_name: Landing, slug: landing, runtime: { policy: always_on, service: nightcraft-landing.service,  port: 5400, workers: 2 } }
  admin:   { display_name: Admin,   slug: admin,   runtime: { policy: always_on, service: nightcraft-admin.service,    port: 5500, workers: 2 } }
  game:    { display_name: Game,    slug: game,    runtime: { policy: always_on, service: nightcraft-game.service,     port: 5800, workers: 2 } }
  note:    { display_name: NoteStack, slug: note,  runtime: { policy: always_on, service: nightcraft-note.service,     port: 5900, workers: 2 } }
  tinyxl:  { display_name: TinyXL,  slug: tinyxl,  runtime: { policy: always_on, service: nightcraft-tinyxl.service,   port: 5200, workers: 2 } }
```
- Initially everything is `always_on` except `green` (`on_demand`).
- `public_paths` is **optional**. A product that declares it is **nginx-generated** (its
  `location` blocks come from the generator, in either mode). Products without it keep their
  existing hand-written nginx blocks untouched. This keeps the diff minimal: only Green
  Pledge's blocks move into the generator.
- `idle_timeout` only applies to `on_demand` products.

## Files

### NEW
1. `platform-infra/prod-debian/products.yml` — the manifest above.
2. `platform-infra/prod-debian/scripts/products.py` — small, dependency-light manifest
   reader (stdlib + PyYAML, already present). Importable by the manager AND usable as a CLI
   by bash: `python3 products.py get <slug> <field>` (dotted, e.g. `runtime.policy`),
   `python3 products.py slugs --policy on_demand`, `python3 products.py public_paths <slug>`.
   Used by `common.sh` helpers.
3. `platform-infra/prod-debian/runtime-manager/nightcraft-runtime-manager.py` — the manager
   daemon. **Stdlib only** (`http.server`, `threading`, `subprocess`, `yaml`). Listens on
   `127.0.0.1:5700`. Reads `/etc/nightcraft/products.yml`. Endpoints:
   `GET/POST /touch/<slug>` (lock-guarded; record `last_access`; if inactive and not already
   starting → spawn a background thread that runs `systemctl start <service>`; a `starting`
   flag prevents both blocking the HTTP thread and repeated starts). `GET /healthz`. On startup,
   seed `last_access=now` for every on_demand service currently `systemctl is-active`. A
   background thread sweeps every 30s and stops idle on_demand services using each product's
   `idle_timeout` (parsed from `15m`/`1h`). Persists `last_access` to
   `/runtime/nightcraft/manager/last_access.json`.
   Runs as root (needs `systemctl`); `Restart=always`.
4. `platform-infra/prod-debian/systemd/nightcraft-runtime-manager.service` — always-on
   systemd unit for the manager (`WantedBy=multi-user.target`, `Restart=always`).
5. `platform-infra/prod-debian/scripts/gen-nginx-on-demand.sh` — reads `products.yml`,
   writes `/etc/nginx/sites-include/on-demand.conf`. For each product with `public_paths`:
   - emit bare redirects (`location = /pledge { return 301 /pledge/; }`, same for
     `/green-pledge`);
   - emit one `location <path>/` per public path: `proxy_pass http://<upstream>/` with the
     correct `X-Forwarded-Prefix`, plus `mirror /_nc_touch_<slug>;`;
   - if `policy == on_demand`: add `proxy_intercept_errors on;` +
     `error_page 502 503 504 = @nc_cold_<slug>;`, an `@nc_cold_<slug>` block that 302s to
     `/_nc_loading?slug=<slug>&next=<url-encoded path>/` (URL-encode `next`), and a readiness
     probe `location = /_nc_probe/<slug>` that **also mirrors** `/_nc_touch_<slug>` and proxies
     to the upstream with `proxy_intercept_errors off` (self-heals the start if the manager was
     briefly down).
   - emit the shared `location = /_nc_loading` block exactly **once** (it serves the loader for
     every product).
   - if `policy == always_on`: emit a plain proxy block (so flipping a product back to
     `always_on` keeps working with no git revert — only a regenerate).
   Also copies `nginx/loaders/on-demand.html` → `/runtime/nightcraft/loaders/on-demand.html`
   and ensures `/etc/nginx/sites-include/` exists. Idempotent; safe to re-run in
   `deploy-all.sh` / `install-nginx.sh`.
6. `platform-infra/prod-debian/nginx/loaders/on-demand.html` — **one shared** branded loading
   page. Reads `?slug=…&next=…`, polls `/_nc_probe/<slug>`, on success
   `location.href = next`. Reused by every on_demand product.

### MODIFIED (minimal, Green-Pledge/on_demand scoped; other products untouched)
7. `nginx/nightcraft.conf`
   - Add upstream `nightcraft_runtime_manager_upstream { server 127.0.0.1:5700; keepalive 8; }`.
   - Add `include /etc/nginx/sites-include/on-demand.conf;` in the `server` block.
   - **Remove** only the Green Pledge hand-written blocks: `location /pledge/`,
     `location /green-pledge/`, `location = /pledge`, `location = /green-pledge`. All other
     (always_on) blocks stay untouched.
8. `scripts/common.sh` — add manifest helpers (`nc_policy`, `nc_service`, `nc_port`,
   `nc_workers`, `nc_idle`, `nc_public_paths`, `nc_is_on_demand <slug>`) backed by
   `products.py`. No behavior change for the existing flow.
9. `scripts/deploy-pledge.sh` — read `workers`/`port`/`policy`/`idle_timeout` from the
   manifest (instead of hardcoding `--workers 3`). Keep venv/deps/`flask setup`. Do **not**
   force-start the service. App untouched.
10. `scripts/install-systemd.sh` — copy `products.yml` → `/etc/nightcraft/products.yml`
    (like env files). Install + `enable --now` the runtime-manager unit. For `on_demand`
    products: install the product `.service` file but **do not `enable` it** (manager starts
    it on demand), and install a drop-in
    `/etc/systemd/system/<service>.d/nightcraft-on-demand.conf`:
    ```
    [Service]
    Restart=no
    ```
    This overrides the base `Restart=always` so the manager's idle `systemctl stop` actually
    sticks (otherwise systemd would resurrect the service). Create the drop-in **before** the
    script's final `systemctl daemon-reload`. For `always_on`: unchanged (`enable`, no drop-in).
11. `scripts/install-nginx.sh` — before `nginx -t`, run `gen-nginx-on-demand.sh` and ensure
    `/runtime/nightcraft/loaders/on-demand.html` exists.
12. `scripts/deploy-all.sh` — (a) copy `products.yml` → `/etc/nightcraft/products.yml` so the
    manager sees policy updates; (b) run `gen-nginx-on-demand.sh`; (c) install + start/restart
    the manager (re-reads the manifest); (d) for `on_demand` products, **do not**
    `systemctl restart/start` the product (leave stopped; manager starts on first request);
    for `always_on` keep existing restarts; (e) `systemctl reload nginx`. Other products'
    lines untouched.
13. `scripts/start-all.sh` — skip `on_demand` products (don't `systemctl start` them); ensure
    the manager is started. `always_on` + other logic unchanged.
14. `scripts/stop-all.sh` / `restart-all.sh` / `status-all.sh` / `reset-stack.sh` — no required
    changes for the POC (optional: `reset-stack.sh` may also remove the manager unit +
    `last_access.json`).

## Implementation phases (preserve behavior first, migrate only Green Pledge after)
**Phase 1 — manifest system, no runtime change.**
- Add `products.yml` + `products.py` + `common.sh` helpers.
- Refactor `deploy-all.sh` / `install-systemd.sh` / `deploy-pledge.sh` / `start-all.sh` to
  *read* values from the manifest but produce **identical** behavior (all products still
  `always_on`, still started/restarted as today).
- Validate `deploy-all.sh` behaves exactly as before.

**Phase 2 — Runtime Manager + on_demand for Green Pledge only.**
- Add manager (#3, #4), generator (#5), shared loader (#6).
- Edit `nightcraft.conf` (#7): manager upstream + include; remove only the two Green Pledge
  blocks.
- Flip `green.runtime.policy` to `on_demand` in the manifest.
- Wire `deploy-all.sh` / `install-nginx.sh` / `install-systemd.sh` to generate nginx, deploy
  the loader, install/start the manager; skip starting pledge.
- `deploy-pledge.sh` / `install-systemd.sh` honor the `on_demand` policy.

## Adding a future product (the extensibility proof)
1. Add a `products:<slug>` block with `public_paths` and `runtime:` (`policy: on_demand`,
   `service`, `port`, `workers`, `idle_timeout`) to `products.yml`.
2. Create the `Restart=no` drop-in for that service (re-run `install-systemd.sh`, or extend
   `deploy-all.sh` to create it) and `systemctl daemon-reload`.
3. Re-run `gen-nginx-on-demand.sh` (automatic in `deploy-all.sh` / `install-nginx.sh`).
That's it — the manager is already generic (reads the manifest) and the loader is shared.
No new deployment logic, no new systemd unit, no app changes.

## Rollback (trivial)
All changes are in tracked files; the Green Pledge `.service` file is never modified.
- Quick toggle: set `green.runtime.policy: always_on` and re-run
  `gen-nginx-on-demand.sh` + `systemctl restart nightcraft-runtime-manager.service`. The
  generator emits a plain proxy block for Green Pledge, so it works with no git revert.
- Full revert: `git revert` the changed files, then
  `systemctl enable --now nightcraft-pledge.service` (runs as before) and optionally
  `systemctl disable --now nightcraft-runtime-manager.service` (harmless if left running —
  with no `on_demand` products it manages nothing, since the generated `on-demand.conf` is
  empty).
The Green Pledge application, venv, DB, deploy script, and `.service` definition are
untouched, so rollback is purely flipping systemd enablement + regenerating config.

## Risks / edge cases (resolved)
- **Manager briefly down:** mirror subrequests fail non-fatally, but the readiness probe
  `/_nc_probe/<slug>` is *also* mirrored, so once the manager recovers (Restart=always) the
  next probe poll re-triggers the start. The loading page self-heals.
- **Concurrent first requests:** multiple `/touch` calls → multiple `systemctl start`; the
  second is a no-op. Idempotent.
- **Stop during an in-flight request:** rare; if the sweep stops a service between requests,
  the next request just cold-starts again (loading page). Acceptable for POC.
- **Manager restart:** seeds `last_access=now` for already-active on_demand services, so it
  will not wrongly stop a service that is merely idle-but-should-stay right after a restart.
- **Idle-stop vs `Restart=always`:** the base pledge unit uses `Restart=always`; a bare
  `systemctl stop` could be defeated if systemd auto-resurrects it. Mitigated by the
  `Restart=no` drop-in installed for `on_demand` products, so the manager owns the lifecycle
  (the next request restarts it via `/touch`). With `Restart=no`, a crash while idle also
  stays down until the next request — acceptable for a low-traffic on_demand app.
- **`mirror` fires on every request** (including a failed/cold one and static assets). This
  is a slight superset of "successful request" and is safer (keeps the service alive while the
  page is used, and the first 502 still triggers the start).
- **nginx `mirror`** requires nginx ≥ 1.13.4 (Debian 11/12 satisfy). Verify with `nginx -v`.
- **Manager runs as root** (needs `systemctl start/stop`). Acceptable for POC; future
  hardening via polkit limiting it to start/stop only declared product units.
- **Idle sweep interval (30s)** vs `idle_timeout` (15m): service stops within ~30s after the
  idle window. Tune as needed.
- **Port 5700** is free (apps use 5100–5900, radio 5333). Confirm on target.

## Validation
- `python3 -m py_compile` the manager and `products.py`; `bash -n` on every edited shell
  script.
- `nginx -t` after regenerating `on-demand.conf`.
- On target (31.70.85.89): `systemctl stop nightcraft-pledge.service`;
  `curl -sI http://localhost/pledge/` → expect 302 to the loading page; confirm the manager
  started the service (`systemctl is-active nightcraft-pledge.service`); probe returns 200;
  browser redirected into the app. With no traffic > `idle_timeout`, the service stops.
- Confirm other apps (`/auth/`, `/notes/`, `/game/`, `/neera/`, …) still serve normally and
  are unaffected.
- `deploy-all.sh` still completes and restarts `always_on` products as before; manager is
  active (`/healthz` → 200).
