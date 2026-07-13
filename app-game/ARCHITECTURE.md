## PvP Architecture (Client Polling + POST) – Final Blueprint

### Overview
- **Transport**: Lightweight client **polling** (every ~2s while waiting for a move) plus normal HTTP `POST` for moves. **No Server-Sent Events / WebSockets** — the weak server keeps zero open connections.
- **Room storage**: Redis hashes (single source of truth, shared across all gunicorn workers).
- **Matchmaking**: Self-cleaning Redis **sorted set** (score = join timestamp) per game type. A 60s TTL trim drops ghost entries left by closed tabs, so no worker is needed.
- **Auth**: Bearer token from the shared OIDC service in SSO mode (local mode assigns a per-IP guest id); the leaderboard records only logged-in users (guests play unranked).
- **Deployment**: `nightcraft-game.service` on port 5800, nginx upstream `app_game_upstream`. No `proxy_buffering off` / long read timeout needed anymore (removed when SSE was dropped); `client_max_body_size 64m` stays for EmulatorJS ROM uploads.

### Data Model (Redis)
- `matchmaking:queue:{game}` – sorted set of waiting user IDs (score = join time).
- `room:{room_id}` – hash containing `p1`, `p2`, `game`, `state`, `round`, `scores`, `current_round`, `moves`, `results`, `last_activity`.
- `room:user:{user_id}` – points to the active room for quick look-ups.
- `lb:elo:{game}` – sorted set, member=user_id, score=elo (starts 1000).
- `lb:stats:{game}:{user_id}` – hash `{w,l,d}`.
- `lb:mode:{game}:{user_id}` – hash `{ai,pvp}` counts (nice-to-have).
- All rooms have an expiration (1h) to clean up abandoned matches. Queue keys are trimmed by timestamp.

### Flow
1. **Join Queue** – `POST /game/queue/join` enqueues the user and immediately tries to match.
2. **Queue Status** – `GET /game/queue/status?game=…` trims stale entries, tries to match, and returns `{matched, room_id, opponent}` or `{waiting:true}`. The lobby polls this ~every 2s (no EventSource).
3. **Matched** – Server creates a Redis room (first player randomly chosen for turn-based games) and returns the room ID.
4. **Room State** – `GET /game/room/<id>/state` returns the current payload (board for TTT, scores/results for RPS). The room polls this ~every 2s while playing.
5. **Make Move** – `POST /game/room/<id>/move` validates the move, updates the room hash, and returns immediately.
6. **Leave / Forfeit** – `POST /game/room/<id>/leave` ends the match and records the result.
7. **Game Over** – Server records the result to the leaderboard for both players (PvP). The client shows the banner.

### Game Logic Modules
- `tic_tac_toe` – 3×3 board, turn-aware. `init_round(first, second)` returns `{board, turn, first_player, second_player}`; `validate_move` rejects off-turn/occupied moves; `apply_move` flips the turn; `evaluate_round` detects row/col/diag win or draw. First board decides the match (single board, `WINS_REQUIRED` effectively 1).
- `rock_paper_scissors` – classic RPS outcome matrix (simultaneous moves, best-of-5, first to 3).
Both expose `init_round`, `validate_move`, and `evaluate_round` (plus TTT-specific `apply_move`) that the room manager calls.

### Leaderboard (Redis, ELO + W/L/D)
- `GET /game/leaderboard?game=tic_tac_toe|rock_paper_scissors` → top 50 (user, elo, w/l/d) + the current user's rank. Open to all.
- `POST /game/leaderboard/record` → `{game, mode:'ai'|'pvp', tier?, outcome:'win'|'loss'|'draw'}`. If not logged in, returns 200 and does nothing (guests unranked).
  - **PvP**: server records automatically on game-over/forfeit (no client trust needed).
  - **AI**: client reports the outcome only when logged in. (Client could lie; acceptable for a casual hub — no prizes. Re-sim could be added later.)
- ELO: standard formula, K=32. PvP uses the opponent's rating; AI uses a fixed virtual bot rating per tier (T1≈800 … T5≈1600). Draws split minimally.

### Durability
Redis AOF is enabled by `setup-host.sh` (`appendonly yes`, `appendfsync everysec`) so the leaderboard survives restarts. Queue/room keys stay ephemeral (TTL'd).

### Runtime Footprint (Cheap VPS)
- Redis idle memory ~1–3MB plus a few MB for room hashes and the leaderboard sorted sets/hashes.
- No long-lived connections; polling is a handful of tiny GETs per active player.
- ELO/stats writes are tiny Redis ops — negligible load.

### User UI Flow

#### Entry Path
```
/                     → Landing page (game hub card)
  → "Game Hub"        → /game/
  → sees: "Tic-Tac-Toe" and "Rock Paper Scissors" + "🏆 Leaderboard"
```

#### Screen-by-screen
- **Landing (`/game/`)** – cards for Tic-Tac-Toe and Rock Paper Scissors, each with "▶ Play vs AI" and "⚔ Play vs Others", plus a Leaderboard link.
- **Tic-Tac-Toe AI (`/game/tic-tac-toe`)** – pick Combat Tier (Recruit→Commander) + your side (X/O); client coin-toss decides first move; the whole game runs in JS (minimax tiers); result is reported to the leaderboard when logged in.
- **Lobby (`/game/lobby?game=…`)** – spinner + "Searching for a match…"; polls `/queue/status`; on match → `/room/<id>`; on 60s timeout → "No players found. Retry."
- **Room (`/game/room/<id>`)** – scoreboard, 3×3 board (TTT) or RPS choices, "Leave / Forfeit". Polls `/state` every 2s. TTT enforces turn order; game over shows VICTORY/DEFEAT/DRAW and records to the leaderboard.
- **Leaderboard (`/game/leaderboard`)** – tabs for each game, ELO-ranked table, current-user highlight.

### My Games — EmulatorJS (in-browser ROM player)
Users upload ROMs they own; the emulator (EmulatorJS, loaded from CDN) runs entirely client-side (WASM), so the server only stores files and serves them through an auth-gated route.
- **Routes** (`game/emulator.py`, blueprint `emulator`, prefix `/game/emulator`): `GET /` library + upload, `POST /upload`, `GET /play/<rom_id>`, `GET /rom/<rom_id>`, `POST /delete/<rom_id>`.
- **Privacy**: ROMs are private to the uploader; non-owners get 404.
- **Legal**: upload requires an explicit rights-confirmation checkbox; no BIOS files bundled.
- **No nginx change needed** for EmulatorJS itself (CDN), but `/game/` keeps `client_max_body_size 64m` for uploads.
