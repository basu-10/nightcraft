import json
import time
import uuid
from typing import Any, Optional

import redis

from flask import current_app

from .games import get_game_module, VALID_GAME_TYPES
from .leaderboard import record_result


def _rc() -> redis.Redis:
    url = current_app.config["REDIS_URL"]
    return redis.Redis.from_url(url, decode_responses=True)


def _queue_key(game: str) -> str:
    return f"matchmaking:queue:{game}"


def _room_key(room_id: str) -> str:
    return f"room:{room_id}"


def _user_key(user_id: str) -> str:
    return f"room:user:{user_id}"


def _now() -> float:
    return time.time()


def _queue_ttl() -> int:
    return int(current_app.config.get("QUEUE_TTL", 60))


def join_queue(user_id: str, game: str) -> bool:
    if game not in VALID_GAME_TYPES:
        raise ValueError(f"Unknown game type: {game}")
    rc = _rc()
    queue = _queue_key(game)
    rc.zrem(queue, user_id)
    rc.zadd(queue, {user_id: _now()})
    return True


def leave_queue(user_id: str, game: str) -> bool:
    rc = _rc()
    removed = rc.zrem(_queue_key(game), user_id)
    return removed > 0


def _trim_stale(queue: str):
    rc = _rc()
    cutoff = _now() - _queue_ttl()
    rc.zremrangebyscore(queue, "-inf", cutoff)


def try_match(game: str) -> Optional[dict]:
    rc = _rc()
    queue = _queue_key(game)
    _trim_stale(queue)
    members = rc.zrange(queue, 0, 1)
    if len(members) < 2:
        return None
    p1, p2 = members[0], members[1]
    rc.zrem(queue, p1, p2)

    room_id = str(uuid.uuid4())
    game_mod = get_game_module(game)

    if game == "tic_tac_toe":
        first = game_mod.random_first_player(p1, p2)
        second = p2 if first == p1 else p1
        current_round = game_mod.init_round(first, second)
    else:
        current_round = game_mod.init_round()

    room = {
        "room_id": room_id,
        "p1": p1,
        "p2": p2,
        "game": game,
        "state": "playing",
        "round": 0,
        "scores": json.dumps({p1: 0, p2: 0}),
        "current_round": json.dumps(current_round),
        "moves": json.dumps({}),
        "results": json.dumps({}),
        "last_activity": str(_now()),
    }
    expiry = current_app.config.get("ROOM_EXPIRY", 3600)
    pipe = rc.pipeline()
    pipe.hset(_room_key(room_id), mapping=room)
    pipe.expire(_room_key(room_id), expiry)
    pipe.set(_user_key(p1), room_id, ex=expiry)
    pipe.set(_user_key(p2), room_id, ex=expiry)
    pipe.execute()
    return {
        "room_id": room_id,
        "p1": p1,
        "p2": p2,
        "game": game,
    }


def get_room(room_id: str) -> Optional[dict]:
    rc = _rc()
    data = rc.hgetall(_room_key(room_id))
    if not data:
        return None
    return {
        "room_id": data.get("room_id", room_id),
        "p1": data["p1"],
        "p2": data["p2"],
        "game": data["game"],
        "state": data.get("state", "playing"),
        "round": int(data.get("round", 0)),
        "scores": json.loads(data.get("scores", "{}")),
        "current_round": json.loads(data.get("current_round", "{}")),
        "moves": json.loads(data.get("moves", "{}")),
        "results": json.loads(data.get("results", "{}")),
        "last_activity": float(data.get("last_activity", "0")),
    }


def get_room_for_user(user_id: str) -> Optional[str]:
    rc = _rc()
    return rc.get(_user_key(user_id))


def _update_room(room_id: str, fields: dict):
    rc = _rc()
    key = _room_key(room_id)
    fields["last_activity"] = str(_now())
    rc.hset(key, mapping=fields)
    expiry = current_app.config.get("ROOM_EXPIRY", 3600)
    rc.expire(key, expiry)


def _record_pvp(room, winner):
    p1, p2 = room["p1"], room["p2"]
    game = room["game"]
    if winner == p1:
        record_result(game, p1, "win", "pvp", opponent_id=p2)
        record_result(game, p2, "loss", "pvp", opponent_id=p1)
    elif winner == p2:
        record_result(game, p2, "win", "pvp", opponent_id=p1)
        record_result(game, p1, "loss", "pvp", opponent_id=p2)
    else:
        record_result(game, p1, "draw", "pvp", opponent_id=p2)
        record_result(game, p2, "draw", "pvp", opponent_id=p1)


def submit_move(room_id: str, user_id: str, move_data: dict) -> dict:
    room = get_room(room_id)
    if room is None:
        raise ValueError("Room not found")
    if room["state"] != "playing":
        raise ValueError("Game is not in playing state")
    if user_id not in (room["p1"], room["p2"]):
        raise ValueError("User is not a player in this room")

    game_mod = get_game_module(room["game"])
    if room["game"] == "tic_tac_toe":
        return _submit_ttt(room, user_id, move_data, game_mod)
    return _submit_simultaneous(room, user_id, move_data, game_mod)


def _submit_ttt(room, user_id, move_data, game_mod) -> dict:
    round_state = room["current_round"]
    if not round_state:
        raise ValueError("No active round")

    valid, err = game_mod.validate_move(move_data, round_state, user_id)
    if not valid:
        raise ValueError(err)

    cell = move_data["cell"]
    new_state = game_mod.apply_move(round_state, user_id, cell)
    result = game_mod.evaluate_round(new_state)

    scores = room.get("scores") or {room["p1"]: 0, room["p2"]: 0}
    game_over = False
    winner = None

    if result["result"] == "win":
        winner = result["winner"]
        scores[winner] = scores.get(winner, 0) + 1
        game_over = True
    elif result["result"] == "draw":
        game_over = True
        winner = None

    if game_over:
        _update_room(
            room["room_id"],
            {
                "current_round": json.dumps(new_state),
                "scores": json.dumps(scores),
                "state": "finished",
                "winner": winner or "",
                "last_activity": str(_now()),
            },
        )
        _record_pvp(room, winner)
        return {
            "event": "round_result",
            "result": result,
            "scores": scores,
            "game_over": True,
            "winner": winner,
        }

    _update_room(room["room_id"], {"current_round": json.dumps(new_state)})
    return {
        "event": "move_accepted",
        "board": new_state["board"],
        "turn": new_state["turn"],
    }


def _submit_simultaneous(room, user_id, move_data, game_mod) -> dict:
    round_state = room["current_round"]
    if not round_state:
        round_state = game_mod.init_round()
        _update_room(room["room_id"], {"current_round": json.dumps(round_state), "moves": json.dumps({})})

    valid, err = game_mod.validate_move(move_data, round_state)
    if not valid:
        raise ValueError(err)

    moves = room.get("moves") or {}
    moves[user_id] = move_data
    _update_room(room["room_id"], {"moves": json.dumps(moves)})

    players = [room["p1"], room["p2"]]
    if all(p in moves for p in players):
        results = game_mod.evaluate_round(moves, round_state)
        scores = room.get("scores") or {room["p1"]: 0, room["p2"]: 0}
        for pid, res in results.items():
            if res.get("result") == "win" or res.get("correct"):
                scores[pid] = scores.get(pid, 0) + 1

        wins_required = current_app.config.get("WINS_REQUIRED", 3)
        rounds_per_match = current_app.config.get("ROUNDS_PER_MATCH", 5)
        new_round = room["round"] + 1
        game_over = False
        winner = None

        for pid, score in scores.items():
            if score >= wins_required:
                game_over = True
                winner = pid
                break

        if not game_over and new_round >= rounds_per_match:
            game_over = True
            p1, p2 = room["p1"], room["p2"]
            if scores.get(p1, 0) > scores.get(p2, 0):
                winner = p1
            elif scores.get(p2, 0) > scores.get(p1, 0):
                winner = p2

        update = {
            "scores": json.dumps(scores),
            "round": str(new_round),
            "current_round": json.dumps(game_mod.init_round()),
            "moves": json.dumps({}),
            "results": json.dumps(results),
            "last_activity": str(_now()),
        }
        if game_over:
            update["state"] = "finished"
            update["winner"] = winner or ""
            _update_room(room["room_id"], update)
            _record_pvp(room, winner)
        else:
            _update_room(room["room_id"], update)

        return {
            "event": "round_result",
            "results": results,
            "scores": scores,
            "round": new_round,
            "game_over": game_over,
            "winner": winner,
        }

    return {
        "event": "opponent_moved",
        "waiting_for_opponent": True,
    }


def forfeit(room_id: str, user_id: str) -> dict:
    room = get_room(room_id)
    if room is None:
        raise ValueError("Room not found")
    if user_id not in (room["p1"], room["p2"]):
        raise ValueError("User is not a player in this room")

    winner = room["p2"] if user_id == room["p1"] else room["p1"]
    _update_room(
        room["room_id"],
        {
            "state": "finished",
            "winner": winner,
            "last_activity": str(_now()),
        },
    )
    _record_pvp(room, winner)
    return {
        "event": "forfeit",
        "winner": winner,
        "forfeited_by": user_id,
    }


def cleanup_room(room_id: str):
    rc = _rc()
    room = get_room(room_id)
    if room is None:
        return
    pipe = rc.pipeline()
    if room.get("p1"):
        pipe.delete(_user_key(room["p1"]))
    if room.get("p2"):
        pipe.delete(_user_key(room["p2"]))
    pipe.delete(_room_key(room_id))
    pipe.execute()
