from flask import jsonify, render_template, request

from . import bp
from ..auth import _get_user_id
from ..games import LEADERBOARD_GAMES
from ..leaderboard import get_leaderboard, get_user_rank, record_result


@bp.route("/leaderboard")
def leaderboard():
    game = request.args.get("game", "tic_tac_toe")
    if game not in LEADERBOARD_GAMES:
        game = "tic_tac_toe"
    return render_template("leaderboard.html", game_type=game)


@bp.route("/leaderboard/data")
def leaderboard_data():
    game = request.args.get("game", "tic_tac_toe")
    if game not in LEADERBOARD_GAMES:
        return jsonify({"error": "Invalid game"}), 400
    data = {
        "game": game,
        "leaderboard": get_leaderboard(game),
    }
    user_id = _get_user_id()
    if user_id:
        data["me"] = get_user_rank(game, user_id)
    return jsonify(data)


@bp.route("/leaderboard/record", methods=["POST"])
def leaderboard_record():
    user_id = _get_user_id()
    if not user_id:
        # Guests play unranked.
        return jsonify({"ok": True, "recorded": False})

    data = request.get_json(silent=True) or {}
    game = data.get("game", "")
    if game not in LEADERBOARD_GAMES:
        return jsonify({"error": "Invalid game"}), 400

    mode = data.get("mode", "ai")
    if mode not in ("ai", "pvp"):
        return jsonify({"error": "Invalid mode"}), 400

    outcome = data.get("outcome", "")
    if outcome not in ("win", "loss", "draw"):
        return jsonify({"error": "Invalid outcome"}), 400

    tier = data.get("tier")
    if tier is not None:
        try:
            tier = int(tier)
        except (TypeError, ValueError):
            tier = None

    record_result(
        game,
        user_id,
        outcome,
        mode,
        opponent_id=None,
        tier=tier,
    )
    return jsonify({"ok": True, "recorded": True})
