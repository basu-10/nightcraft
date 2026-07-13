# Game Hub: Fix PvP + Add EmulatorJS (richer experience)

## Context (verified against current code)

The `app-game` Flask app at `app-game/` is more complete than its README/ARCHITECTURE docs imply:

- **Single-player "vs AI"** pages (`highest_number.html`, `rock_paper_scissors.html`) are fully working standalone.
- **PvP "vs Others"** backend is implemented (`game/redis_manager.py`, `game/routes.py`, `game/sse_utils.py`) and the frontend (`lobby.html`, `room.html`) is fully wired for both `highest_number` and `rock_paper_scissors`.
- **Deployment is wired**: `nightcraft-game.service` (port 5800), nginx `/game` upstream, `seed-game-client.sh` (OAuth client `game-app`, redirect `/game/auth/callback`), `deploy-game.sh`. No infra gaps.

### Why "vs Others" is currently unplayable (Workstream A root cause)

In `game/redis_manager.py`:
- `try_match()` creates the room with an **empty `current_round`** (`json.dumps({})`).
- `submit_move()` only calls `game_mod.init_round()` (which generates the two numbers for Highest Number, etc.) **on the first move**.

But `room_events` in `routes.py` only emits `your_turn` when `current_round` is truthy, and `room.html` keeps all controls **disabled** until `your_turn` fires. Result: both players sit on "Waiting for round to start…" with disabled buttons, can never submit a move, so `current_round` is never seeded → **deadlock**. Repeats every subsequent round. This is the concrete bug behind "they can't be played against others yet."

### Library decision (Workstream B)

For "a third-party library for a richer experience, running on the client's hardware, with ROMs uploaded under user accounts," the right fit is **EmulatorJS** — a mature, free/open-source in-browser multi-system emulator (GBA/GB/GBC/NES/SNES/Genesis) built on Emscripten/WASM. We load its loader from the EmulatorJS CDN (so it's fetched once and cached), the WASM core executes entirely in the player's browser (no server CPU), and ROMs are uploaded/stored by us under each user's account. This **replaces Poki/CrazyGames** entirely (no Poki integration planned).

## Decisions (from Q&A)

- **ROM visibility:** private to the uploader only — never listed or shared publicly. Reduces copyright/DMCA exposure.
- **EmulatorJS hosting:** load `loader.js` + cores from `https://cdn.emulatorjs.org/stable/data/loader.js` (CDN). Server stays lean; emulator still runs client-side.
- **ROM storage:** files on the persistent shared volume `${GAME_SHARED_DIR}/uploads/<user_id>/<uuid>` (i.e. `/runtime/shared/app-game/uploads/...`), served only via an auth-gated route; metadata in a small **SQLite** DB at `${GAME_SHARED_DIR}/emulator.db` (stdlib `sqlite3`, no new infra).

---

## Workstream A — Fix PvP "vs Others"

### Changes
1. **`game/redis_manager.py` → `try_match()`**: after building the `room` dict, call `game_mod = get_game_module(game)` and set `"current_round": json.dumps(game_mod.init_round())` so the first round's state (e.g. the two numbers) is present from room creation.
2. **`game/redis_manager.py` → `submit_move()`**: when a round completes and the match is **not** over, seed the *next* round immediately: set `"current_round": json.dumps(game_mod.init_round())` in the same `_update_room(...)` call that advances `round`/resets `moves`. (Currently it resets `current_round` to `{}`, which re-triggers the deadlock.)
3. **`game/routes.py` → `room_events()`**: change the `your_turn` branch condition from `elif not my_move and current_round:` to `elif not my_move:`. **Why this matters for both games:** `rock_paper_scissors.init_round()` returns `{}` (no round data needed), which is falsy, so the old condition would *also* deadlock RPS even after step 1. Emitting `your_turn` whenever it's the player's turn to move (and they haven't) is correct for both games. The `waiting_round` event becomes unreachable but its frontend handler can stay.
4. Verify `highest_number.init_round()` returns `{"values": [...], "correct_index": ...}`; `room.html` reads `current_round.values` — compatible after step 1. RPS needs no round values.

### Production dependency: Redis (REQUIRED before A can ship)
PvP uses Redis for matchmaking/rooms, but **prod-debian does not install or enable Redis** (only the Docker-based dev setup runs `nightcraft-redis`; `reset-stack.sh`/`deploy-all.sh` have no redis step, and `ARCHITECTURE.md` still lists "Install Redis and enable it" as TODO). In prod the PvP routes will raise a Redis connection error on first queue/room call. Fixes:
- Add `platform-infra/prod-debian/scripts/install-redis.sh` (or extend `setup-host.sh`): `apt-get install -y redis-server` then `systemctl enable --now redis-server`.
- `deploy-all.sh`: run the redis install (or ensure `setup-host.sh` covers it) before `deploy-game.sh`.
- `nightcraft-game.service`: add `After=redis-server.service` and `Wants=redis-server.service` so the game unit waits for Redis. (Optionally add `redis-server` to `start-all.sh`/`stop-all.sh`/`status-all.sh` for ops convenience.)
- `app-game.env` (lives at `/etc/nightcraft/app-game.env`, sourced from `platform-infra/prod-debian/env/` which is **not committed** — implementer must create it): set `REDIS_URL=redis://127.0.0.1:6379/0` plus the SSO vars (`AUTH_MODE=sso`, `AUTH_SERVICE_URL`, `OIDC_CLIENT_ID=game-app`, `OIDC_CLIENT_SECRET=game-app-client-secret-2026`, `OIDC_REDIRECT_URI=http://31.70.85.889/game/auth/callback` — must match the seeded client in `seed-game-client.sh`).
- Mark the `ARCHITECTURE.md` "Install Redis" TODO as resolved.

### Validation
- Manual: two logged-in sessions (or one + incognito) → both click "Play vs Others" for the same game → matched → numbers/choices appear and are clickable → pick → round resolves → scoreboard updates → next round auto-seeds → game-over screen with correct winner.
- Optional automated: add `app-game/tests/` using `fakeredis` to assert `try_match` returns a room with non-empty `current_round` and that two `submit_move` calls produce `results` + incremented `scores`. (App currently has no tests; this is the first.)

---

## Workstream B — EmulatorJS integration

### New routes (add a `emulator_bp` blueprint in `game/emulator.py`, registered in `game/__init__.py`)
- `GET /game/emulator` (`login_required`) — "My Games" page: lists the current user's ROM metadata, an **Upload** form, and per-ROM **Play** buttons.
- `POST /game/emulator/upload` (`login_required`) — accepts a ROM file:
  - Extension allowlist only: `.gba .gb .gbc .nes .smc .sfc .md .genesis .sms .gg` (no archives/`.zip` to avoid extraction attacks).
  - Enforce `MAX_CONTENT_LENGTH` (e.g. 64 MB) and a per-user quota (e.g. max 20 ROMs or 512 MB).
  - Save to `${GAME_SHARED_DIR}/uploads/<user_id>/<uuid><ext>` (= `/runtime/shared/app-game/uploads/...`; the persistent shared volume, **not** the gitignored source `instance/`) (random name; never trust original filename for path → prevents traversal/overwrite).
  - Insert metadata row; redirect back to the list.
- `GET /game/emulator/play/<rom_id>` (`login_required` + owner check) — renders the EmulatorJS loader template (sets `EJS_*` vars, loads CDN `loader.js`).
- `GET /game/emulator/rom/<rom_id>` (`login_required` + owner check) — streams the file bytes with the correct `Content-Type`/`Content-Length`. This URL is what `EJS_gameUrl` points to; the authenticated session cookie is sent by the in-page fetch, so it stays private. Use the DB `rom_id` (not the filesystem uuid) as the public handle.
- `POST /game/emulator/delete/<rom_id>` (`login_required` + owner) — removes file + metadata.
- Admin: a simple removal helper (same owner-check bypass for admin) to honor DMCA takedowns.

### EmulatorJS loader template (`game/templates/emulator_play.html`)
Set, before loading the CDN script:
```js
EJS_player = '#game';
EJS_core = '<core>';                                  // see mapping below
EJS_gameUrl = '/game/emulator/rom/<rom_id>';          // same-origin -> session cookie sent -> auth-gated
EJS_pathtodata = 'https://cdn.emulatorjs.org/stable/data/';
EJS_gameID = <numeric_rom_id_or_hash>;                // isolates saves/states per ROM
EJS_gameName = '<safe_display_name>';
// EJS_threads left false on purpose: enabling threads requires COOP/COEP cross-origin-isolation headers.
```
Then `<script src="https://cdn.emulatorjs.org/stable/data/loader.js"></script>`.

**Core mapping (from file extension) — verified against EmulatorJS docs:**
| ext | `EJS_core` |
|-----|-----------|
| `.gba` | `gba` (core `mgba`) |
| `.gb`, `.gbc` | `gb` |
| `.nes` | `nes` |
| `.smc`, `.sfc` | `snes` |
| `.md`, `.genesis` | `segaMD` (NOT `genesis`) |
| (optional) `.sms`/`.gg`/`.32x` | `segaMS`/`segaGG`/`sega32x` |

**BIOS:** GBA BIOS is **optional** (md5 `a860e8c0b6d573d191e4ec7db1b1e4f6`); the mGBA core runs without it (HLE). **Do not bundle or distribute any BIOS file.** (Optional future: allow a user-provided `EJS_biosUrl` if they own one.)

### Storage / metadata
- Store under the existing persistent shared dir, not `instance/` (which is inside the gitignored source checkout and not on the shared volume):
  - ROM files: `${GAME_SHARED_DIR}/uploads/<user_id>/<uuid><ext>` (= `/runtime/shared/app-game/uploads/...`).
  - Metadata DB: `${GAME_SHARED_DIR}/emulator.db` (SQLite, stdlib `sqlite3`); table `roms(id, user_id, system, stored_name, original_name, size, created_at)`.
- `deploy-game.sh` already does `ensure_dir "${GAME_SHARED_DIR}"`; add `ensure_dir "${GAME_SHARED_DIR}/uploads"` (and `chown_tree`) so the path exists with correct ownership.

### Security
- Server-side extension check + size cap + quota; reject everything else.
- Random stored filenames; serve only through the auth+owner-gated route (never a static path).
- `Content-Type` set explicitly; do not reflect client-supplied type.
- Note: binary ROMs can't be meaningfully AV-scanned; rely on extension+size+auth. Optional future: ClamAV scan on upload, and magic-byte/size heuristics. Flag as open item, not blocking.

### Legal / ToS (must-have, not optional)
- Upload form requires an explicit checkbox + short disclaimer: user affirms they own a legal copy / have rights to the uploaded ROM, uploads are **private** and not shared, and the operator may remove content on DMCA notice.
- Keep ROMs private (per decision); no public browse/listing of other users' ROMs.
- GBA may require a copyrighted BIOS for some titles. EmulatorJS mGBA core runs HLE without a BIOS for most games; do **not** bundle or distribute any BIOS. If a user needs one, they must supply their own (out of scope for v1).
- Provide a DMCA / takedown contact and the admin removal path above.

### Validation
- Log in → upload a known-good homebrew GBA/ROM (e.g. a free homebrew `.gba`) → it appears only in *your* "My Games" → Play launches EmulatorJS and the game runs in-browser → another logged-in user cannot see or fetch your ROM (401/404 on the rom route) → delete removes file + row.
- Confirm zero server CPU spike during play (WASM runs client-side).

---

## Dropped
- Poki / CrazyGames integration — not pursued. EmulatorJS covers the "richer experience" need and keeps everything under our accounts.

## Rollout
- **Prerequisite (Workstream A):** provision Redis in prod-debian (`install-redis.sh` / `setup-host.sh`), add `After=/Wants=redis-server.service` to `nightcraft-game.service`, and create `/etc/nightcraft/app-game.env` with `REDIS_URL` + SSO vars (see "Production dependency: Redis"). Without this, PvP fails at runtime.
- No new systemd *unit* or nginx upstream needed (app-game service + `/game` already exist).
- `deploy-game.sh`: add `ensure_dir "${GAME_SHARED_DIR}/uploads"` so ROM storage exists.
- EmulatorJS via CDN → no static asset additions, no nginx changes.
- New blueprint + templates + SQLite init; redeploy via existing `deploy-game.sh` + `restart nightcraft-game.service`.

## Open questions / risks
- SQLite vs Postgres for ROM metadata: chosen SQLite to keep app-game self-contained (no new DB infra). Switch to Postgres later if unified storage is desired.
- BIOS handling for GBA left to user-supplied/out-of-scope.
- ROM AV scanning deferred.
- Whether to also persist PvP match history / leaderboards later (out of scope for this plan).
