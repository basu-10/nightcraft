from game import redis_manager


def test_try_match_seeds_current_round(app):
    with app.app_context():
        redis_manager.join_queue("u1", "highest_number")
        redis_manager.join_queue("u2", "highest_number")
        match = redis_manager.try_match("highest_number")
        assert match is not None
        assert match["p1"] == "u1"
        assert match["p2"] == "u2"

        room = redis_manager.get_room(match["room_id"])
        assert room is not None
        # The first round's state must be present (no deadlock on first round).
        assert room["current_round"] not in (None, {})
        assert "values" in room["current_round"]


def test_submit_move_produces_results_and_seeds_next_round(app):
    with app.app_context():
        redis_manager.join_queue("a", "highest_number")
        redis_manager.join_queue("b", "highest_number")
        match = redis_manager.try_match("highest_number")
        room_id = match["room_id"]
        room = redis_manager.get_room(room_id)
        correct_index = room["current_round"]["correct_index"]
        wrong_index = 1 - correct_index

        first = redis_manager.submit_move(room_id, "a", {"index": correct_index})
        assert first["event"] == "opponent_moved"

        second = redis_manager.submit_move(room_id, "b", {"index": wrong_index})
        assert second["event"] == "round_result"
        assert second["scores"]["a"] == 1
        assert second["scores"]["b"] == 0
        assert second["round"] == 1
        # Next round is immediately seeded so the next your_turn fires.
        updated = redis_manager.get_room(room_id)
        assert updated["current_round"] not in (None, {})


def test_submit_move_rps_seeds_empty_round(app):
    with app.app_context():
        redis_manager.join_queue("p1", "rock_paper_scissors")
        redis_manager.join_queue("p2", "rock_paper_scissors")
        match = redis_manager.try_match("rock_paper_scissors")
        room_id = match["room_id"]
        room = redis_manager.get_room(room_id)
        # RPS init_round returns {} which is falsy; the deadlock fix must still seed it.
        assert room["current_round"] == {}

        r1 = redis_manager.submit_move(room_id, "p1", {"choice": "rock"})
        assert r1["event"] == "opponent_moved"
        r2 = redis_manager.submit_move(room_id, "p2", {"choice": "scissors"})
        assert r2["event"] == "round_result"
        updated = redis_manager.get_room(room_id)
        # Next RPS round is again {} but must be seeded (not missing).
        assert "current_round" in updated
