
## DEPLOYMENT


Keep the wrapper script outside `/nightcraft-source-code` (for example `/usr/local/sbin/server-scripts/nightcraft-server-bootstrap.sh`) and run:

sudo /usr/local/sbin/server-scripts/nightcraft-server-bootstrap.sh --repo-url https://github.com/basu-10/nightcraft.git --branch main --target-dir /nightcraft-source-code --adopt-existing --force-sync

This replaces the manual sequence by checking host requirements, syncing repo via git, running install scripts, deploying apps, restarting services, and printing final status.

