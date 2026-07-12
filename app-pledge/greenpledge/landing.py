from flask import Blueprint, render_template

bp = Blueprint("landing", __name__)

# Placeholder community statistics. On day one these may be very small (or
# zero). The landing experience is designed to make that feel acceptable and
# to invite the visitor to imagine the future rather than fixate on the low
# numbers. Wire these to real aggregates once the product data layer lands.
COMMUNITY = {
    "people": 0,
    "co2_pledged": 0,
    "co2_completed": 0,
}


@bp.route("/")
def home():
    return render_template("landing/index.html", community=COMMUNITY)


@bp.route("/about")
def about():
    return render_template("landing/about.html")
