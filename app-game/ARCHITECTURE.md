## PvP Architecture (SSE + POST) – Final Blueprint

### Overview
- **Transport**: Server‑Sent Events (SSE) for server‑to‑client updates, normal HTTP POST for client‑to‑server moves.
- **Room storage**: Redis hashes (single source of truth, works across all gunicorn workers).
- **Matchmaking**: Simple FIFO queue stored in Redis; each game type has its own queue.
- **Auth**: Bearer token from the shared OIDC service; token is validated on each request.
- **Deployment**: New systemd service `nightcraft-game.service` on port 5800, nginx upstream `app_game_upstream` with `proxy_buffering off` for SSE.

### Data Model (Redis)
- `matchmaking:queue:{game}` – list of waiting user IDs.
- `room:{room_id}` – hash containing `p1`, `p2`, `game`, `state`, `round`, `scores`, `current_round`, `last_activity`.
- `sse:user:{user_id}` – points to the active room for quick look‑ups.
- All rooms have an expiration (e.g., 1 hour) to clean up abandoned matches.

### Flow
1. **Join Queue** – `POST /game/queue/join` enqueues the user.
2. **Queue Events** – `GET /game/queue/events` is an SSE stream that emits `waiting` and `matched` events.
3. **Matched** – Server creates a Redis room and notifies both users with the room ID.
4. **Room Events** – `GET /game/room/<id>/events` streams state changes (opponent moved, round result, game over).
5. **Make Move** – `POST /game/room/<id>/move` validates the move, updates the room hash, and triggers a new SSE payload.
6. **Leave / Forfeit** – `POST /game/room/<id>/leave` ends the match and declares the opponent the winner.

### Game Logic Modules (both games use the same backend)
- `highest_number` – generates two numbers, player picks the higher one.
- `rock_paper_scissors` – classic RPS outcome matrix.
Both expose `init_round`, `validate_move`, and `evaluate_round` functions that the room manager calls.

### Required Deployment Changes (PROVISIONED)
- ✅ Install Redis (`apt install redis-server`) and enable it — handled by `setup-host.sh` and `start-all.sh`.
- ✅ Add `nightcraft-game.service` systemd unit (2 workers, bind 127.0.0.1:5800) with `After=/Wants=redis-server.service` so the game waits for Redis.
- ✅ `app-game.env` (`/etc/nightcraft/app-game.env`, template in `env-examples/app-game.env`) sets `REDIS_URL` + SSO vars.
- ⚠️ Update `nightcraft.conf` with `upstream app_game_upstream { server 127.0.0.1:5800; }` and the `/game/` location with `proxy_buffering off;` and a long `proxy_read_timeout` (needed for PvP SSE streams).
- ⚠️ **ROM uploads**: the same `/game/` location must raise `client_max_body_size` (e.g. `client_max_body_size 64m;`), otherwise the 64 MB EmulatorJS ROM uploads are rejected with HTTP 413 (nginx default is 1 MB). This is a live-config change not covered by this repo.
- Extend `deploy-all.sh` to copy the game folder, install its Python requirements (adds `redis`), and restart the new service — done.

### Runtime Footprint (Cheap VPS)
- Redis idle memory ~1‑3 MB, plus a few MB for room hashes.
- Each SSE connection consumes ~50 KB of RAM; 100 concurrent players ≈ 5 MB.
- Overall added load is well under 20 MB, negligible compared to existing Flask services and PostgreSQL.

### Open Configurable Items (you can tune later)
- Number of rounds per match (default 5, first to 3).
- Disconnect timeout (default 30 s) before declaring a forfeit.
- Queue timeout (default 120 s) before showing “no opponents”.

### User UI Flow

#### Entry Path

```
http://31.70.85.89/          → Landing page (game hub card)
  → clicks "Game Hub"        → http://31.70.85.89/game/
  → sees two game cards: "Highest Number" and "Rock Paper Scissors"
```

#### Screen-by-screen elements

**Screen 1 – Game landing (`/game/`)**
- Header: "Game Hub"
- Card 1: "Highest Number" – description + "Play vs AI" button + "Play vs Others" button
- Card 2: "Rock Paper Scissors" – description + "Play vs AI" button + "Play vs Others" button
- "Play vs AI" → existing single‑player mode (no change)
- "Play vs Others" → checked: is user logged in? No → redirect to `/game/auth/login`. Yes → proceed

**Screen 2 – Login (`/game/auth/login`)**
- Redirects to `/auth/authorize?client_id=game-app&redirect_uri=/game/auth/callback`
- After successful OIDC flow → browser lands back on the same game page with session cookie set
- "Play vs Others" now proceeds

**Screen 3 – Lobby (waiting screen, `GET /game/lobby?game=highest_number`)**
- Elements:
  - Title: "Looking for opponent…"
  - Spinner animation
  - Text: "Playing: Highest Number"
  - "Cancel" button → calls `POST /game/queue/cancel`, returns to game landing
  - On match found → SSE event `matched` received → auto‑navigate to `/game/room/<id>`
  - On timeout (120 s) → text changes to "No players found. Try again." + "Retry" button

**Screen 4 – Game room (`/game/room/<id>`)**
- Common header across both games:
  - Scoreboard: "You: 2 – Opponent: 1"
  - Round indicator: "Round 3 of 5"
  - "Leave / Forfeit" button
- Highest Number variant:
  - Two large number buttons (e.g., "[42]" "[73]")
  - Click one → button highlights, SSE sends `opponent_moved` after opponent picks
  - Result shown: "Correct! You win this round." or "Wrong – opponent gets the point"
  - "Next Round" button (appears after both have picked and results shown)
  - Game Over screen: "You Win!" or "You Lose!" with "Play Again" and "Back to Hub" buttons
- Rock Paper Scissors variant:
  - Three choice buttons: [🪨 Rock] [📄 Paper] [✂️ Scissors]
  - Once both pick → outcome revealed: "You chose Rock. Opponent chose Scissors. You Win!"
  - Same round progression, next round, and game over flow

**Screen 5 – Game Over (`/game/room/<id>` with state `finished`)**
- Elements:
  - Banner: "Victory!" or "Defeat"
  - Final score: "3 – 1"
  - "Play Again" → calls `POST /game/queue/join` again, redirects to `/game/lobby`
  - "Back to Hub" → links to `/game/`

#### Visual State Table (Highest Number Room Example)

| Player State | P1 sees | P2 sees |
|---|---|---|
| Waiting for opponent | [42] [73] (both enabled) + "Pick a number" | [42] [73] (both disabled) + "Waiting for opponent's move…" |
| Both picked | Both disabled + result text + "Next Round" | Both disabled + same result + "Next Round" |
| Game Over | "You Win! 3–1" + Play Again / Back | "You Lose! 1–3" + Play Again / Back |

### My Games — EmulatorJS (in-browser ROM player)

Users upload ROMs they own; the emulator (EmulatorJS, loaded from CDN) runs entirely client-side (WASM), so the server only stores files and serves them through an auth-gated route.

- **Routes** (`game/emulator.py`, blueprint `emulator`, prefix `/game/emulator`):
  - `GET /` — "My Games" library + upload form (login required).
  - `POST /upload` — extension allowlist + size cap (64 MB) + per-user quota (20 ROMs / 512 MB); rejects unless the rights-confirm checkbox is set; stores under `${GAME_SHARED_DIR}/uploads/<user_id>/<uuid><ext>` (random name, never the client basename) and inserts a row into the SQLite DB at `${GAME_SHARED_DIR}/emulator.db`.
  - `GET /play/<rom_id>` — renders the EmulatorJS loader (sets `EJS_*` vars, loads `loader.js` from CDN).
  - `GET /rom/<rom_id>` — streams the file bytes (explicit `Content-Type`, `send_file` with `conditional=True` for `Content-Length`/range). Same-origin fetch sends the session cookie → stays private.
  - `POST /delete/<rom_id>` — removes file + metadata (owner, or admin via `GAME_ADMIN_USER_IDS`).
- **Privacy**: ROMs are private to the uploader; the `rom`/`play` routes return 404 (not 403) for non-owners to avoid leaking which IDs exist.
- **Legal**: upload form requires an explicit rights-confirmation checkbox + short disclaimer; no BIOS files are bundled or distributed (GBA runs via mGBA HLE). Provide a DMCA contact + the admin removal path above.
- **Core mapping** (by extension): `.gba`→`gba`, `.gb`/`.gbc`→`gb`, `.nes`→`nes`, `.smc`/`.sfc`→`snes`, `.md`/`.genesis`→`segaMD`, `.sms`→`segaMS`, `.gg`→`segaGG`, `.32x`→`sega32x`.
- **SQLite concurrency**: `emulator.py` opens `sqlite3.connect(..., timeout=30, check_same_thread=False)` since 2 gunicorn workers write the DB.
- **No nginx change needed** for EmulatorJS itself (CDN), but the `/game/` `client_max_body_size` must cover uploads (see above).

