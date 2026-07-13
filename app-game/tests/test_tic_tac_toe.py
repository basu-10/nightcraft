from game import matchmaking
from game.games import tic_tac_toe as ttt


def test_init_round_shape():
    r = ttt.init_round("p1", "p2")
    assert r["board"] == [None] * 9
    assert r["turn"] == "p1"
    assert r["first_player"] == "p1"
    assert r["second_player"] == "p2"


def test_validate_move_rejects_off_turn():
    r = ttt.init_round("p1", "p2")
    ok, _ = ttt.validate_move({"cell": 0}, r, "p2")
    assert ok is False
    ok, _ = ttt.validate_move({"cell": 0}, r, "p1")
    assert ok is True


def test_validate_move_rejects_occupied_and_invalid():
    r = ttt.init_round("p1", "p2")
    r["board"][0] = "X"
    ok, _ = ttt.validate_move({"cell": 0}, r, "p1")
    assert ok is False
    ok, _ = ttt.validate_move({"cell": 9}, r, "p1")
    assert ok is False


def test_apply_move_flips_turn_and_marks():
    r = ttt.init_round("p1", "p2")
    new = ttt.apply_move(r, "p1", 4)
    assert new["board"][4] == "X"
    assert new["turn"] == "p2"
    # first_player stays p1, so p1 is X, p2 is O
    new2 = ttt.apply_move(new, "p2", 0)
    assert new2["board"][0] == "O"
    assert new2["turn"] == "p1"


def test_evaluate_round_row_win():
    r = ttt.init_round("p1", "p2")
    r["board"][0] = "X"
    r["board"][1] = "X"
    r["board"][2] = "X"
    res = ttt.evaluate_round(r)
    assert res["result"] == "win"
    assert res["winner"] == "p1"
    assert res["line"] == [0, 1, 2]


def test_evaluate_round_draw():
    r = ttt.init_round("p1", "p2")
    # Cats game pattern
    board = ["X", "O", "X", "X", "O", "O", "O", "X", "X"]
    r["board"] = board
    res = ttt.evaluate_round(r)
    assert res["result"] == "draw"
    assert res["winner"] is None


def test_evaluate_round_ongoing():
    r = ttt.init_round("p1", "p2")
    r["board"][0] = "X"
    res = ttt.evaluate_round(r)
    assert res["result"] is None
