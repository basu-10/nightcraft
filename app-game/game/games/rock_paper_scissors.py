import random

GAME_TYPE = "rock_paper_scissors"

_CHOICES = ["rock", "paper", "scissors"]

_BEAT = {
    "rock": "scissors",
    "paper": "rock",
    "scissors": "paper",
}


def init_round():
    return {}


def validate_move(move_data, round_state):
    choice = move_data.get("choice")
    if choice not in _CHOICES:
        return False, f"Invalid choice: must be one of {_CHOICES}."
    return True, None


def evaluate_round(moves, round_state):
    player_ids = list(moves.keys())
    if len(player_ids) != 2:
        return {}

    p1 = player_ids[0]
    p2 = player_ids[1]
    c1 = moves[p1].get("choice")
    c2 = moves[p2].get("choice")

    if c1 == c2:
        return {
            p1: {"result": "tie", "opponent_choice": c2, "choice": c1},
            p2: {"result": "tie", "opponent_choice": c1, "choice": c2},
        }

    p1_wins = _BEAT[c1] == c2
    return {
        p1: {"result": "win" if p1_wins else "lose", "opponent_choice": c2, "choice": c1},
        p2: {"result": "lose" if p1_wins else "win", "opponent_choice": c1, "choice": c2},
    }
