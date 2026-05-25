"""Local development server entry point."""
import os

from landing import create_app


if __name__ == "__main__":
    app = create_app()
    host = os.environ.get("FLASK_HOST", "127.0.0.1")
    port = int(os.environ.get("FLASK_PORT", "5400"))
    app.run(host=host, port=port, debug=True)
