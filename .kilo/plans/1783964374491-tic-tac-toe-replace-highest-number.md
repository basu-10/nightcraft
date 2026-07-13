# Plan: Replace "Highest Number" with Tic-Tac-Toe (no streaming, weak-server safe, + leaderboard)

## Goal
Remove the Highest Number game **everywhere (whole repo)** — grep for `highest_number` / `Highest Number` across `app-game`, the `app-landing` root hub, nginx config, README/docs, and delete all references — then add **Tic-Tac-Toe (3×3)** with two modes:
- **Play vs AI** — single player, 5 difficulty tiers. Runs **client-side** (zero server load).
- **Play vs Others** — global matchmaking queue vs a random human (server-authoritative, client polling).

Plus a **server-side leaderboard** (Redis) covering **both hub games** (Tic-Tac-Toe + Rock-Paper-Scissors) with **ELO + W/L/D**.

## Hard constraints (user)
- **No streaming** (no SSE / no WebSockets). Weak server.
- **No heavy server-side polling.** Turn-based updates only.
- **AI must be client-side JS** (server only stores leaderboard results).
- Keep the **gamer-y neon theme**; make code **modular / smaller files**.

## Confirmed design decisions
1. **Transport = lightweight client polling** every ~2s, only while waiting for a move. No open connections. RPS also migrated off SSE → app has **zero streaming**.
2. **Reuse FIFO Redis queue** (`join_queue`/`try_match`); swap key `highest_number` → `tic_tac_toe`. Harden with a **sorted set + 60s TTL trim** so a tab-close can't leave a ghost entry.
3. **3×3 board, single board per match.** Reuses the existing room loop by setting `WINS_REQUIRED=1` so the first board decides W/L/D.
4. **First move = coin toss.** PvP: server randomly picks first player at room creation. AI: client coin-toss for first move, and the **user always picks their side (X/O)**; AI takes the other.
5. **AI is fully client-side** (JS minimax/heuristics). It reports the final result to the server to update the leaderboard.
6. **Leaderboard** in Redis (AOF-enabled for durability) for **both `tic_tac_toe` and `rock_paper_scissors`**: per-user ELO + W/L/D. **AI mode is open to anonymous players**; a result is recorded to the leaderboard only when the player is logged in (guests play unranked).

## 5 AI difficulty tiers (client-side, 3×3)
| Tier | Name | Behavior |
|---|---|---|
| 1 | Recruit | Random legal move. |
| 2 | Rookie | Take immediate win; block immediate loss ~60%; else random. |
| 3 | Grunt | Always take win + always block loss; else random. |
| 4 | Veteran | Perfect minimax but 25% of moves are random (beatable). |
| 5 | Commander | Perfect unbeatable minimax (instant on 3×3). |

All in `static/js/tic_tac_toe_ai.js`; `chooseMove(board, tier, mySymbol)` returns a cell index.

## Matchmaking / global queue (reuse + harden)
- Replace plain list with a **Redis sorted set** (`ZADD` join timestamp; `ZREMRANGEBYSCORE` drops entries >60s old on each join/poll). Self-cleaning, no workers.
- `POST /queue/join` enqueues (login required). Client then polls `GET /queue/status?game=tic_tac_toe` (~2s).
- `GET /queue/status` trims stale, calls `try_match`, returns `{matched, room_id, opponent}` or `{waiting:true}`. Replaces SSE `/queue/events`.
- `try_match` atomic two-pop pairing; stores `first_player` randomly in the room.

## Turn order (new for TTT)
TTT needs enforced turn order (RPS/HN were simultaneous). `init_round` returns `{board:[9 nulls], turn: first_player, first_player}`. `validate_move` rejects moves when it's not the mover's turn or the cell is occupied. `evaluate_round` returns win/draw/cats-game for the current board.

## Leaderboard subsystem (Redis)
Schema:
- `lb:elo:{game}` — sorted set, member=user_id, score=elo (start 1000).
- `lb:stats:{game}:{user_id}` — hash `{w,l,d}`.
- `lb:mode:{game}:{user_id}` — optional hash of `{ai:N, pvp:N}` counts (nice-to-have).

Endpoints (`views/leaderboard.py`):
- `GET /leaderboard?game=tic_tac_toe|rock_paper_scissors` → top 50 (user, elo, w/l/d) + current user's rank. Open to all.
- `POST /leaderboard/record` → body `{game, mode:'ai'|'pvp', tier?, outcome:'win'|'loss'|'draw'}`. If not logged in, returns 200 and does nothing (guests play unranked).
  - PvP: server records automatically on game-over/forfeit (no client trust needed).
  - AI: client reports outcome only when logged in; **trust note** — client could lie, acceptable for a casual hub (no prizes). Could add a server-side re-sim later if needed.

**Durability:** enable Redis AOF (`appendonly yes`, `appendfsync everysec`) via the host setup script so the leaderboard survives restarts. Queue/room keys stay ephemeral (already TTL'd).

ELO: standard formula, K=32. PvP uses opponent's rating. AI uses a fixed virtual bot rating per tier (T1≈800 … T5≈1600). Draws split minimal.

## Proposed modular file layout
```
app-game/game/
  __init__.py                # registers blueprints
  auth.py                    # (keep)
  views/
    __init__.py
    landing.py               # / , /tic-tac-toe (AI tier+side select), /rock-paper-scissors
    lobby.py                 # /lobby , /queue/join , /queue/cancel , /queue/status
    room.py                  # /room/<id> , /room/<id>/state , /move , /leave
    leaderboard.py           # /leaderboard (GET) , /leaderboard/record (POST)
  games/
    __init__.py              # registry (drop highest_number, add tic_tac_toe)
    rock_paper_scissors.py   # (keep logic; add leaderboard recording hook)
    tic_tac_toe.py           # init_round / validate_move / evaluate_round (turn-aware, 3x3)
  matchmaking.py             # renamed redis_manager: sorted-set queue + room state helpers + leaderboard ops
  templates/
    landing.html             # Tic-Tac-Toe card replaces Highest Number
    lobby.html               # polls /queue/status (no EventSource)
    room.html                # thin shell; loads per-game JS by game_type
    tic_tac_toe_ai.html      # tier select + side pick -> starts client-side game
    tic_tac_toe_board.html   # shared 3x3 board UI (used by AI screen)
    rock_paper_scissors.html # (keep; add leaderboard link)
    leaderboard.html         # rankings table
  static/js/
    room_core.js             # shared: state-poll loop, scoreboard, leave/forfeit
    room_ttt.js              # 3x3 render + move submit (PvP)
    room_rps.js              # RPS render + move submit (PvP, polling)
    lobby.js                 # queue-status polling
    tic_tac_toe_ai.js        # client-side game: coin toss, side pick, turn loop, AI tiers
    tic_tac_toe_board.js     # 3x3 board DOM render (shared by AI + PvP shells)
    leaderboard.js           # fetch + render table
```
Delete: `games/highest_number.py`, `templates/highest_number.html`, `routes.py`, `sse_utils.py` (unused after SSE removal). Remove all `EventSource` usage.

## Backend behavior
- **PvP room (TTT):** `POST /queue/join` → match → `GET /room/<id>/state` (same payload shape as old SSE: `state, round, scores, my_move, opponent_moved, current_round, results, winner, is_winner`). Turn enforced by `tic_tac_toe.validate_move`. On game-over, server records PvP result to leaderboard.
- **AI (client-side):** no Redis room. `tic_tac_toe_ai.html` runs the whole game in JS (coin toss, user side pick, AI tiers). On finish, if logged in, `POST /leaderboard/record` with outcome (guests skip).
- **RPS PvP:** migrated to polling; on game-over/forfeit, server records to `rock_paper_scissors` leaderboard.
- **No login for viewing** leaderboard; **login required only to be ranked** (AI play is open to all; PvP already requires login).

## Frontend behavior (gamer-y)
- `landing.html`: Tic-Tac-Toe card → "▶ Play vs AI" (`/tic-tac-toe`: pick Combat Tier + your side X/O) and "⚔ Play vs Others" (`/lobby?game=tic_tac_toe`). Add a "🏆 Leaderboard" link.
- `lobby.html`: poll `/queue/status`; on `matched` → `/room/<id>`; 60s no-match → "No players found. Retry."
- `room.html`: thin shell loading `room_core.js` + (`room_ttt.js` | `room_rps.js`); core loop polls `/state` every 2s while waiting.
- Theme: dark slab, neon cyan/magenta/lime, glowing X/O cells, "DEPLOY BOT — Select Combat Tier", "VICTORY/DEFEAT" banners, "🏆 Leaderboard" table.

## Deployment notes (low risk)
- SSE nginx tweaks (`proxy_buffering off`, long `proxy_read_timeout`) for `/game/` no longer needed for these routes (keep `client_max_body_size` for ROM uploads).
- **Enable Redis AOF** in the host setup (`setup-host.sh` / `redis.conf`: `appendonly yes`, `appendfsync everysec`) so the leaderboard persists across restarts.
- No new Python deps; Redis sorted-set + hash commands already available.
- ELO/stats writes are tiny Redis ops — negligible load.

## Validation
- `pytest` (app-game/tests):
  - `tic_tac_toe`: `init_round` empty 3×3 + turn set; `validate_move` rejects off-turn/occupied; `evaluate_round` detects row/col/diag win + draw.
  - AI: simulate T5 vs random 200 games → T5 never loses; T1 loses sometimes; T3/T4 behave per spec.
  - `matchmaking`: sorted-set queue trims stale entries; `try_match` pairs two; first_player random.
  - `leaderboard`: ELO moves correctly on win/loss/draw; W/L/D counters; per-game separation (TTT vs RPS).
  - Polling endpoints return correct shapes; `/queue/events` & `/room/<id>/events` removed; no `EventSource` remains.
- Manual: `/game/` → AI tier 5 (verify unbeatable) and tier 1; "Play vs Others" in two browsers (match + polling sync + forfeit + leaderboard update); check `/leaderboard` for both games.

## Open / out of scope
- Per-tier AI leaderboard breakdown (currently TTT combined; tier only tagged in stats hash as nice-to-have).
- Anti-cheat verification of client-reported AI results (deferred; no prizes at stake).
- EmulatorJS feature untouched.
- Persistent SQLite leaderboard (chose Redis + AOF per weak-server constraint).

## Whole-repo cleanup checklist (do this, not "out of scope")
- [ ] Delete `app-game/game/games/highest_number.py` and `app-game/game/templates/highest_number.html`.
- [ ] Remove `highest_number` from `app-game/game/games/__init__.py` registry and `VALID_GAME_TYPES`.
- [ ] Delete `app-game/game/routes.py` + `sse_utils.py`; migrate to `views/` blueprints.
- [ ] Grep whole repo for `highest_number` / `Highest Number` / `highest-number` and remove: root landing card (app-landing), any nginx `/game/` SSE-specific tweaks, README/docs mentions.
- [ ] Update `app-game/ARCHITECTURE.md` and `README.md` to reflect polling (no SSE) + leaderboard.
