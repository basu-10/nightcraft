import math

from flask import current_app

from .games import LEADERBOARD_GAMES

K_FACTOR = 32
DEFAULT_ELO = 1000

# Virtual opponent ratings for the client-side AI tiers (1=Recruit .. 5=Commander).
BOT_RATINGS = {
    1: 800,
    2: 1000,
    3: 1200,
    4: 1400,
    5: 1600,
}

LEADERBOARD_LIMIT = 50


def _rc():
    url = current_app.config["REDIS_URL"]
    import redis

    return redis.Redis.from_url(url, decode_responses=True)


def _elo_key(game):
    return f"lb:elo:{game}"


def _stats_key(game, user_id):
    return f"lb:stats:{game}:{user_id}"


def _mode_key(game, user_id):
    return f"lb:mode:{game}:{user_id}"


def _expected(ra, rb):
    return 1.0 / (1.0 + 10 ** ((rb - ra) / 400.0))


def get_elo(game, user_id):
    rc = _rc()
    score = rc.zscore(_elo_key(game), user_id)
    if score is None:
        return DEFAULT_ELO
    return int(round(score))


def get_stats(game, user_id):
    rc = _rc()
    data = rc.hgetall(_stats_key(game, user_id))
    return {
        "w": int(data.get("w", 0)),
        "l": int(data.get("l", 0)),
        "d": int(data.get("d", 0)),
    }


def record_result(game, user_id, outcome, mode, opponent_id=None, tier=None):
    if not user_id:
        return
    if game not in LEADERBOARD_GAMES:
        return

    rc = _rc()

    ra = get_elo(game, user_id)
    if opponent_id:
        rb = get_elo(game, opponent_id)
    else:
        rb = BOT_RATINGS.get(tier, DEFAULT_ELO)

    score = 1.0 if outcome == "win" else 0.0 if outcome == "loss" else 0.5
    new_ra = ra + K_FACTOR * (score - _expected(ra, rb))
    new_ra = int(round(new_ra))

    pipe = rc.pipeline()
    pipe.zadd(_elo_key(game), {user_id: new_ra})
    stat_field = "w" if outcome == "win" else "l" if outcome == "loss" else "d"
    pipe.hincrby(_stats_key(game, user_id), stat_field, 1)
    mode_field = "ai" if mode == "ai" else "pvp"
    pipe.hincrby(_mode_key(game, user_id), mode_field, 1)
    pipe.execute()


def get_leaderboard(game):
    rc = _rc()
    rows = rc.zrevrange(_elo_key(game), 0, LEADERBOARD_LIMIT - 1, withscores=True)
    leaderboard = []
    for user_id, elo in rows:
        stats = get_stats(game, user_id)
        leaderboard.append(
            {
                "user_id": user_id,
                "elo": int(round(elo)),
                "wins": stats["w"],
                "losses": stats["l"],
                "draws": stats["d"],
            }
        )
    return leaderboard


def get_user_rank(game, user_id):
    rc = _rc()
    rank = rc.zrevrank(_elo_key(game), user_id)
    if rank is None:
        return None
    return {
        "rank": rank + 1,
        "elo": get_elo(game, user_id),
        "stats": get_stats(game, user_id),
    }
