import random

GAME_TYPE = "tic_tac_toe"

EMPTY = None

WIN_LINES = [
    [0, 1, 2],
    [3, 4, 5],
    [6, 7, 8],
    [0, 3, 6],
    [1, 4, 7],
    [2, 5, 8],
    [0, 4, 8],
    [2, 4, 6],
]


def init_round(first_player, second_player=None):
    return {
        "board": [EMPTY] * 9,
        "turn": first_player,
        "first_player": first_player,
        "second_player": second_player,
    }


def symbol_for(round_state, user_id):
    return "X" if round_state.get("first_player") == user_id else "O"


def opponent_of(round_state, user_id):
    if round_state.get("first_player") == user_id:
        return round_state.get("second_player")
    return round_state.get("first_player")


def validate_move(move_data, round_state, user_id):
    if round_state.get("turn") != user_id:
        return False, "Not your turn."

    cell = move_data.get("cell")
    if not isinstance(cell, int) or cell < 0 or cell > 8:
        return False, "Invalid cell index."

    if round_state["board"][cell] is not EMPTY:
        return False, "Cell already occupied."

    return True, None


def apply_move(round_state, user_id, cell):
    board = list(round_state["board"])
    symbol = symbol_for(round_state, user_id)
    board[cell] = symbol

    next_turn = opponent_of(round_state, user_id)

    return {
        "board": board,
        "turn": next_turn,
        "first_player": round_state.get("first_player"),
        "second_player": round_state.get("second_player"),
    }


def evaluate_round(round_state):
    board = round_state["board"]

    for line in WIN_LINES:
        a, b, c = line
        if board[a] is not EMPTY and board[a] == board[b] == board[c]:
            symbol = board[a]
            winner = (
                round_state["first_player"]
                if symbol == "X"
                else round_state.get("second_player")
            )
            return {"result": "win", "winner": winner, "line": line, "symbol": symbol}

    if all(cell is not EMPTY for cell in board):
        return {"result": "draw", "winner": None, "line": None, "symbol": None}

    return {"result": None, "winner": None, "line": None, "symbol": None}


def is_terminal(round_state):
    return evaluate_round(round_state)["result"] is not None


def available_cells(board):
    return [i for i, cell in enumerate(board) if cell is EMPTY]


def random_first_player(p1, p2):
    return random.choice([p1, p2])
