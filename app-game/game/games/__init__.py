from .rock_paper_scissors import GAME_TYPE as RPS_TYPE
from .tic_tac_toe import GAME_TYPE as TTT_TYPE

_GAME_MODULES = {
    RPS_TYPE: __import__("game.games.rock_paper_scissors", fromlist=[""]),
    TTT_TYPE: __import__("game.games.tic_tac_toe", fromlist=[""]),
}

VALID_GAME_TYPES = set(_GAME_MODULES.keys())

LEADERBOARD_GAMES = {RPS_TYPE, TTT_TYPE}


def get_game_module(game_type: str):
    mod = _GAME_MODULES.get(game_type)
    if mod is None:
        raise ValueError(f"Unknown game type: {game_type}")
    return mod
