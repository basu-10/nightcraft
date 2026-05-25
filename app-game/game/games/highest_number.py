import random

GAME_TYPE = "highest_number"


def init_round():
    a = random.randint(10, 99)
    b = random.randint(10, 99)
    while b == a:
        b = random.randint(10, 99)
    values = [a, b]
    random.shuffle(values)
    return {
        "values": values,
        "correct_index": 0 if values[0] > values[1] else 1,
    }


def validate_move(move_data, round_state):
    idx = move_data.get("index")
    if idx not in (0, 1):
        return False, "Invalid choice."
    return True, None


def evaluate_round(moves, round_state):
    correct_index = round_state["correct_index"]
    results = {}
    for player_id, move_data in moves.items():
        chosen = move_data.get("index")
        results[player_id] = {
            "correct": chosen == correct_index,
            "chosen": chosen,
            "values": round_state["values"],
        }
    return results
