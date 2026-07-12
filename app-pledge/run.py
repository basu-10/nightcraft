import os
from pathlib import Path

from greenpledge import create_app

# Use runtime/shared for persisted data in direct-source deployments.
_SHARED_INSTANCE = Path(
    os.getenv("PLEDGE_SHARED_INSTANCE_DIR", "/runtime/shared/green-pledge-app/instance")
)
_SHARED_INSTANCE.mkdir(parents=True, exist_ok=True)

app = create_app(instance_path=str(_SHARED_INSTANCE))

if __name__ == "__main__":
    app.run(debug=True, port=5300)
