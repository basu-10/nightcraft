from flask import render_template

from . import bp


@bp.route("/")
def landing():
    return render_template("landing.html")


@bp.route("/rock-paper-scissors")
def rock_paper_scissors():
    return render_template("rock_paper_scissors.html")


@bp.route("/tic-tac-toe")
def tic_tac_toe_ai():
    return render_template("tic_tac_toe_ai.html")
