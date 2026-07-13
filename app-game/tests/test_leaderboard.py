from game import leaderboard


def test_elo_rises_on_win_falls_on_loss(app):
    with app.app_context():
        leaderboard.record_result("tic_tac_toe", "alice", "win", "pvp", opponent_id="bob")
        leaderboard.record_result("tic_tac_toe", "bob", "loss", "pvp", opponent_id="alice")
        assert leaderboard.get_elo("tic_tac_toe", "alice") > 1000
        assert leaderboard.get_elo("tic_tac_toe", "bob") < 1000
        assert leaderboard.get_stats("tic_tac_toe", "alice") == {"w": 1, "l": 0, "d": 0}
        assert leaderboard.get_stats("tic_tac_toe", "bob") == {"w": 0, "l": 1, "d": 0}


def test_draw_splits_minimal(app):
    with app.app_context():
        leaderboard.record_result("tic_tac_toe", "alice", "draw", "pvp", opponent_id="bob")
        leaderboard.record_result("tic_tac_toe", "bob", "draw", "pvp", opponent_id="alice")
        assert leaderboard.get_stats("tic_tac_toe", "alice")["d"] == 1
        assert leaderboard.get_stats("tic_tac_toe", "bob")["d"] == 1


def test_ai_uses_tier_rating(app):
    with app.app_context():
        # Beating the unbeatable Commander (T5) should gain more than beating Recruit (T1).
        before = leaderboard.get_elo("tic_tac_toe", "player")
        leaderboard.record_result("tic_tac_toe", "player", "win", "ai", tier=1)
        after_t1 = leaderboard.get_elo("tic_tac_toe", "player")
        leaderboard.record_result("tic_tac_toe", "player", "loss", "ai", tier=5)
        after_t5_loss = leaderboard.get_elo("tic_tac_toe", "player")
        assert after_t1 > before
        assert after_t5_loss < after_t1


def test_per_game_separation(app):
    with app.app_context():
        leaderboard.record_result("tic_tac_toe", "alice", "win", "pvp", opponent_id="bob")
        # RPS leaderboard must be independent of TTT.
        assert leaderboard.get_stats("rock_paper_scissors", "alice") == {"w": 0, "l": 0, "d": 0}
        assert leaderboard.get_user_rank("rock_paper_scissors", "alice") is None


def test_guest_not_ranked(app):
    with app.app_context():
        leaderboard.record_result("tic_tac_toe", None, "win", "ai", tier=5)
        board = leaderboard.get_leaderboard("tic_tac_toe")
        assert all(row["user_id"] is not None for row in board)


def test_leaderboard_ordering(app):
    with app.app_context():
        leaderboard.record_result("tic_tac_toe", "low", "loss", "pvp", opponent_id="high")
        leaderboard.record_result("tic_tac_toe", "high", "win", "pvp", opponent_id="low")
        board = leaderboard.get_leaderboard("tic_tac_toe")
        assert board[0]["user_id"] == "high"
        assert board[0]["elo"] > board[1]["elo"]
