from flask import Blueprint, render_template

from .auth.current_user import get_current_user
from .models import Pledge

bp = Blueprint("landing", __name__)


@bp.route("/")
def home():
    app_user = get_current_user()
    pledges = (
        Pledge.query.filter_by(active=True)
        .order_by(Pledge.created_at.desc())
        .limit(12)
        .all()
    )
    return render_template("landing/index.html", pledges=pledges, app_user=app_user)


@bp.route("/about")
def about():
    return render_template("landing/about.html")
