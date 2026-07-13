from flask import abort, jsonify, render_template, request

from . import bp
from ..auth import _get_user_id, login_required
from ..matchmaking import (
    forfeit,
    get_room,
    submit_move,
)


@bp.route("/room/<room_id>")
@login_required
def room(room_id):
    user_id = _get_user_id()
    room_data = get_room(room_id)
    if room_data is None:
        from flask import redirect, url_for

        return redirect(url_for("game.landing"))
    if user_id not in (room_data["p1"], room_data["p2"]):
        return redirect(url_for("game.landing"))
    return render_template(
        "room.html",
        room_id=room_id,
        game_type=room_data["game"],
        user_id=user_id,
        is_p1=(user_id == room_data["p1"]),
    )


@bp.route("/room/<room_id>/state")
@login_required
def room_state(room_id):
    user_id = _get_user_id()
    room_data = get_room(room_id)
    if room_data is None:
        return jsonify({"error": "Room not found"}), 404
    if user_id not in (room_data["p1"], room_data["p2"]):
        return jsonify({"error": "Not a player"}), 403

    is_p1 = user_id == room_data["p1"]
    opponent_id = room_data["p2"] if is_p1 else room_data["p1"]

    if room_data["game"] == "tic_tac_toe":
        current_round = room_data.get("current_round") or {}
        payload = {
            "state": room_data["state"],
            "round": room_data["round"],
            "scores": room_data["scores"],
            "game": room_data["game"],
            "current_round": current_round,
            "my_turn": room_data["state"] == "playing"
            and current_round.get("turn") == user_id,
            "finished": room_data["state"] == "finished",
            "winner": room_data.get("winner") or None,
            "is_winner": room_data.get("winner") == user_id,
        }
        return jsonify(payload)

    moves = room_data.get("moves") or {}
    my_move = moves.get(user_id)
    opponent_moved = opponent_id in moves
    payload = {
        "state": room_data["state"],
        "round": room_data["round"],
        "scores": room_data["scores"],
        "game": room_data["game"],
        "current_round": room_data.get("current_round") or {},
        "my_move": my_move,
        "opponent_moved": opponent_moved,
        "results": room_data.get("results", {}),
        "winner": room_data.get("winner") or None,
        "is_winner": room_data.get("winner") == user_id,
        "finished": room_data["state"] == "finished",
    }
    return jsonify(payload)


@bp.route("/room/<room_id>/move", methods=["POST"])
@login_required
def room_move(room_id):
    user_id = _get_user_id()
    data = request.get_json(silent=True) or {}
    try:
        result = submit_move(room_id, user_id, data)
        return jsonify(result)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400


@bp.route("/room/<room_id>/leave", methods=["POST"])
@login_required
def room_leave(room_id):
    user_id = _get_user_id()
    try:
        result = forfeit(room_id, user_id)
        return jsonify(result)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
