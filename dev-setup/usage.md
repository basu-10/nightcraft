# dev environment setup management commands:

Command	What it does
bash dev-setup/nightcraft-dev-setup.sh	Full install + start (or --skip-* flags for partial)
bash dev-setup/status.sh	Show running/stopped status per service with PIDs, ports, Docker container health, disk usage
bash dev-setup/shutdown.sh	Graceful shutdown — stops app services first, then Docker containers
The status.sh checks:

PID files + kill -0 for accurate running/stopped detection
Port-in-use fallback if PID files are stale
Docker container states via docker inspect
The shutdown.sh runs stop-all.sh + stop-infra.sh sequentially, so app processes terminate before PostgreSQL/Redis go down, preventing connection errors.