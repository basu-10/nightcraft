# app-landing todo

Build a small Flask-based landing app for my multi-app self-hosted platform.

Context:
I run multiple Flask apps on a Debian VPS behind Nginx using path routing:

/        -> landing-app
/auth    -> auth-service
/notes   -> notes-app
/game    -> game-app
/admin   -> admin-app

This landing app should be a lightweight product dashboard / portfolio hub.
It should be the default route and provide links to the other apps, as well as a unified login page that redirects to the auth service for SSO.
