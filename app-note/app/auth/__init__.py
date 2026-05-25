from flask import Flask


def get_auth_blueprint(app: Flask):
	auth_mode = (app.config.get("AUTH_MODE", "local") or "local").strip().lower()
	if auth_mode == "sso":
		from .sso_auth import auth_bp

		return auth_bp

	from .routes import auth_bp

	return auth_bp
