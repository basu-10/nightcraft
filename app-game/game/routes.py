import json
import time

from flask import (
    Blueprint,
    jsonify,
    make_response,
    redirect,
    render_template,
    request,
    Response,
    session,
    stream_with_context,
    url_for,
)

from .auth import _get_user_id, login_required
from .games import VALID_GAME_TYPES
from .redis_manager import (
    cleanup_room,
    forfeit,
    get_room,
    get_room_for_user,
    join_queue,
    leave_queue,
    submit_move,
    try_match,
)
from .sse_utils import heartbeat, sse_event, stream_with_heartbeat

game_bp = Blueprint("game", __name__, template_folder="templates")


@game_bp.route("/")
def landing():
    return render_template("landing.html")


@game_bp.route("/highest-number")
def highest_number():
    return render_template("highest_number.html")


@game_bp.route("/rock-paper-scissors")
def rock_paper_scissors():
    return render_template("rock_paper_scissors.html")


@game_bp.route("/lobby")
@login_required
def lobby():
    game = request.args.get("game", "")
    if game not in VALID_GAME_TYPES:
        return redirect(url_for("game.landing"))
    return render_template("lobby.html", game_type=game)


@game_bp.route("/room/<room_id>")
@login_required
def room(room_id):
    user_id = _get_user_id()
    room_data = get_room(room_id)
    if room_data is None:
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


@game_bp.route("/queue/join", methods=["POST"])
@login_required
def queue_join():
    user_id = _get_user_id()
    data = request.get_json(silent=True) or {}
    game = data.get("game", "")
    if game not in VALID_GAME_TYPES:
        return jsonify({"error": "Invalid game type"}), 400

    existing_room = get_room_for_user(user_id)
    if existing_room:
        return jsonify({"room_id": existing_room, "matched": True})

    join_queue(user_id, game)
    match = try_match(game)
    if match:
        return jsonify({
            "matched": True,
            "room_id": match["room_id"],
            "opponent": match["p2"] if user_id == match["p1"] else match["p1"],
        })
    return jsonify({"matched": False, "waiting": True})


@game_bp.route("/queue/cancel", methods=["POST"])
@login_required
def queue_cancel():
    user_id = _get_user_id()
    data = request.get_json(silent=True) or {}
    game = data.get("game", "")
    if game in VALID_GAME_TYPES:
        leave_queue(user_id, game)
    return jsonify({"ok": True})


@game_bp.route("/queue/events")
@login_required
def queue_events():
    user_id = _get_user_id()
    game = request.args.get("game", "")
    if game not in VALID_GAME_TYPES:
        return jsonify({"error": "Invalid game type"}), 400

    queue_timeout = 120

    def generate():
        start = time.time()
        join_queue(user_id, game)
        yield sse_event("waiting", game=game)

        while True:
            elapsed = time.time() - start
            if elapsed >= queue_timeout:
                leave_queue(user_id, game)
                yield sse_event("timeout")
                return

            existing_room = get_room_for_user(user_id)
            if existing_room:
                room_data = get_room(existing_room)
                opponent = None
                if room_data:
                    opponent = room_data["p2"] if user_id == room_data["p1"] else room_data["p1"]
                yield sse_event("matched", room_id=existing_room, opponent=opponent)
                return

            match = try_match(game)
            if match and user_id in (match["p1"], match["p2"]):
                opponent = match["p2"] if user_id == match["p1"] else match["p1"]
                yield sse_event("matched", room_id=match["room_id"], opponent=opponent)
                return

            time.sleep(1)

    return Response(
        stream_with_heartbeat(stream_with_context(generate())),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


@game_bp.route("/room/<room_id>/events")
@login_required
def room_events(room_id):
    user_id = _get_user_id()
    room_data = get_room(room_id)
    if room_data is None:
        return jsonify({"error": "Room not found"}), 404
    if user_id not in (room_data["p1"], room_data["p2"]):
        return jsonify({"error": "Not a player"}), 403

    def generate():
        last_state = None
        while True:
            room_data = get_room(room_id)
            if room_data is None:
                yield sse_event("room_closed")
                return

            state_key = (
                room_data["state"],
                room_data["round"],
                json.dumps(room_data["scores"], sort_keys=True),
                json.dumps(room_data.get("moves", {}), sort_keys=True),
                json.dumps(room_data.get("current_round", {}), sort_keys=True),
            )

            if state_key != last_state:
                last_state = state_key
                is_p1 = user_id == room_data["p1"]
                opponent_id = room_data["p2"] if is_p1 else room_data["p1"]

                moves = room_data.get("moves", {})
                current_round = room_data.get("current_round", {})
                my_move = moves.get(user_id)
                opponent_moved = opponent_id in moves

                payload = {
                    "state": room_data["state"],
                    "round": room_data["round"],
                    "scores": room_data["scores"],
                    "my_move": my_move,
                    "opponent_moved": opponent_moved,
                    "current_round": current_round if current_round else None,
                    "results": room_data.get("results", {}),
                    "winner": room_data.get("winner"),
                }

                if room_data["state"] == "finished":
                    payload["is_winner"] = room_data.get("winner") == user_id
                    yield sse_event("game_over", **payload)
                    return

                if my_move and opponent_moved:
                    yield sse_event("round_ready", **payload)
                elif my_move and not opponent_moved:
                    yield sse_event("waiting_opponent", **payload)
                elif not my_move:
                    yield sse_event("your_turn", **payload)
                else:
                    yield sse_event("waiting_round", **payload)

            if room_data["state"] == "finished":
                return

            time.sleep(0.5)

    return Response(
        stream_with_heartbeat(stream_with_context(generate())),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


@game_bp.route("/room/<room_id>/move", methods=["POST"])
@login_required
def room_move(room_id):
    user_id = _get_user_id()
    data = request.get_json(silent=True) or {}
    try:
        result = submit_move(room_id, user_id, data)
        return jsonify(result)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400


@game_bp.route("/room/<room_id>/leave", methods=["POST"])
@login_required
def room_leave(room_id):
    user_id = _get_user_id()
    try:
        result = forfeit(room_id, user_id)
        return jsonify(result)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
