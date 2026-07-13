import time

from flask import jsonify, render_template, request

from . import bp
from ..auth import _get_user_id, login_required
from ..games import VALID_GAME_TYPES
from ..matchmaking import get_room, get_room_for_user, join_queue, leave_queue, try_match


@bp.route("/lobby")
@login_required
def lobby():
    game = request.args.get("game", "")
    if game not in VALID_GAME_TYPES:
        from flask import redirect, url_for

        return redirect(url_for("game.landing"))
    return render_template("lobby.html", game_type=game)


@bp.route("/queue/join", methods=["POST"])
@login_required
def queue_join():
    user_id = _get_user_id()
    data = request.get_json(silent=True) or {}
    game = data.get("game", "")
    if game not in VALID_GAME_TYPES:
        return jsonify({"error": "Invalid game type"}), 400

    existing_room = get_room_for_user(user_id)
    if existing_room:
        room = get_room(existing_room)
        opponent = None
        if room:
            opponent = room["p2"] if user_id == room["p1"] else room["p1"]
        return jsonify({"room_id": existing_room, "matched": True, "opponent": opponent})

    join_queue(user_id, game)
    match = try_match(game)
    if match:
        return jsonify({
            "matched": True,
            "room_id": match["room_id"],
            "opponent": match["p2"] if user_id == match["p1"] else match["p1"],
        })
    return jsonify({"matched": False, "waiting": True})


@bp.route("/queue/cancel", methods=["POST"])
@login_required
def queue_cancel():
    user_id = _get_user_id()
    data = request.get_json(silent=True) or {}
    game = data.get("game", "")
    if game in VALID_GAME_TYPES:
        leave_queue(user_id, game)
    return jsonify({"ok": True})


@bp.route("/queue/status")
@login_required
def queue_status():
    user_id = _get_user_id()
    game = request.args.get("game", "")
    if game not in VALID_GAME_TYPES:
        return jsonify({"error": "Invalid game type"}), 400

    existing_room = get_room_for_user(user_id)
    if existing_room:
        room = get_room(existing_room)
        opponent = None
        if room:
            opponent = room["p2"] if user_id == room["p1"] else room["p1"]
        return jsonify({"matched": True, "room_id": existing_room, "opponent": opponent})

    match = try_match(game)
    if match and user_id in (match["p1"], match["p2"]):
        opponent = match["p2"] if user_id == match["p1"] else match["p1"]
        return jsonify({"matched": True, "room_id": match["room_id"], "opponent": opponent})

    return jsonify({"waiting": True})
