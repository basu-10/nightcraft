from game import matchmaking


def test_try_match_seeds_ttt_board(app):
    with app.app_context():
        matchmaking.join_queue("u1", "tic_tac_toe")
        matchmaking.join_queue("u2", "tic_tac_toe")
        match = matchmaking.try_match("tic_tac_toe")
        assert match is not None
        assert match["p1"] == "u1"
        assert match["p2"] == "u2"

        room = matchmaking.get_room(match["room_id"])
        assert room is not None
        assert room["current_round"] not in (None, {})
        assert room["current_round"]["board"] == [None] * 9
        assert room["current_round"]["turn"] in ("u1", "u2")


def test_try_match_is_atomic_pairing(app):
    with app.app_context():
        matchmaking.join_queue("a", "tic_tac_toe")
        matchmaking.join_queue("b", "tic_tac_toe")
        matchmaking.join_queue("c", "tic_tac_toe")
        m1 = matchmaking.try_match("tic_tac_toe")
        assert m1 is not None
        # a and b consumed; c remains
        assert matchmaking.get_room_for_user("c") is None
        assert matchmaking.try_match("tic_tac_toe") is None


def test_queue_trims_stale_entries(app):
    with app.app_context():
        rc = matchmaking._rc()
        key = matchmaking._queue_key("tic_tac_toe")
        # Inject a stale entry far in the past, then two fresh joiners.
        rc.zadd(key, {"stale": 1})
        matchmaking.join_queue("a", "tic_tac_toe")
        matchmaking.join_queue("b", "tic_tac_toe")
        match = matchmaking.try_match("tic_tac_toe")
        assert match is not None
        assert set([match["p1"], match["p2"]]) == {"a", "b"}
        assert "stale" not in (match["p1"], match["p2"])


def test_first_player_random(app):
    with app.app_context():
        seen = set()
        for _ in range(20):
            matchmaking.join_queue("p1", "tic_tac_toe")
            matchmaking.join_queue("p2", "tic_tac_toe")
            match = matchmaking.try_match("tic_tac_toe")
            room = matchmaking.get_room(match["room_id"])
            seen.add(room["current_round"]["first_player"])
        assert seen == {"p1", "p2"}


def test_submit_ttt_x_wins_records_leaderboard(app):
    with app.app_context():
        matchmaking.join_queue("p1", "tic_tac_toe")
        matchmaking.join_queue("p2", "tic_tac_toe")
        match = matchmaking.try_match("tic_tac_toe")
        room_id = match["room_id"]
        room = matchmaking.get_room(room_id)
        first = room["current_round"]["first_player"]
        second = room["current_round"]["second_player"]

        # First player takes top row.
        m1 = matchmaking.submit_move(room_id, first, {"cell": 0})
        assert m1["event"] == "move_accepted"
        m2 = matchmaking.submit_move(room_id, second, {"cell": 3})
        assert m2["event"] == "move_accepted"
        m3 = matchmaking.submit_move(room_id, first, {"cell": 1})
        assert m3["event"] == "move_accepted"
        m4 = matchmaking.submit_move(room_id, second, {"cell": 4})
        assert m4["event"] == "move_accepted"
        m5 = matchmaking.submit_move(room_id, first, {"cell": 2})
        assert m5["event"] == "round_result"
        assert m5["game_over"] is True
        assert m5["winner"] == first

        finished = matchmaking.get_room(room_id)
        assert finished["state"] == "finished"

        from game import leaderboard

        assert leaderboard.get_elo("tic_tac_toe", first) > 1000
        assert leaderboard.get_elo("tic_tac_toe", second) < 1000
        assert leaderboard.get_stats("tic_tac_toe", first)["w"] == 1
        assert leaderboard.get_stats("tic_tac_toe", second)["l"] == 1


def test_submit_ttt_rejects_off_turn(app):
    with app.app_context():
        matchmaking.join_queue("p1", "tic_tac_toe")
        matchmaking.join_queue("p2", "tic_tac_toe")
        match = matchmaking.try_match("tic_tac_toe")
        room_id = match["room_id"]
        first = matchmaking.get_room(room_id)["current_round"]["first_player"]
        second = matchmaking.get_room(room_id)["current_round"]["second_player"]
        # second tries to move first -> rejected
        try:
            matchmaking.submit_move(room_id, second, {"cell": 0})
            assert False, "should have raised"
        except ValueError:
            pass
        # first moves, then second can move
        matchmaking.submit_move(room_id, first, {"cell": 0})
        matchmaking.submit_move(room_id, second, {"cell": 4})
