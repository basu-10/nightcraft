from .highest_number import GAME_TYPE as HN_TYPE
from .rock_paper_scissors import GAME_TYPE as RPS_TYPE

_GAME_MODULES = {
    HN_TYPE: __import__("game.games.highest_number", fromlist=[""]),
    RPS_TYPE: __import__("game.games.rock_paper_scissors", fromlist=[""]),
}

VALID_GAME_TYPES = set(_GAME_MODULES.keys())


def get_game_module(game_type: str):
    mod = _GAME_MODULES.get(game_type)
    if mod is None:
        raise ValueError(f"Unknown game type: {game_type}")
    return mod
