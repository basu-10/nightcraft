from functools import wraps

from flask import abort
from flask_login import current_user, login_required


def admin_required(f):
    @login_required
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_admin:
            abort(403)
        return f(*args, **kwargs)
    return decorated
