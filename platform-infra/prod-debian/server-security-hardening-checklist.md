# Nightcraft Production Server Security Hardening Checklist

Related architecture notes: `platform-infra/prod-debian/overview_of__production_server.md`.

Login used for production work:

```bash
ssh ionos-dev
```

The production bootstrap script `server-scripts/nightcraft-server-bootstrap.sh` is deliberately kept outside the repo on the VPS and should remain git-untracked locally.

## Checklist Status Legend

Use these markers when reviewing the server:

- `[ ]` not done
- `[~]` partially done or needs verification
- `[x]` done
- `[n/a]` not applicable

Priority:

- **P0**: immediate security risk
- **P1**: strong hardening item
- **P2**: operational maturity / defense-in-depth

## Current Baseline Strengths

- [x] Apps run as non-root user `dev:dev`, not as `root`.
- [x] Gunicorn services bind to `127.0.0.1:<port>` and are exposed through nginx.
- [x] nginx has a catch-all server block returning `444` for unknown hostnames.
- [x] Default Debian nginx site is removed.
- [x] App secrets live under `/etc/nightcraft`, outside the source checkout.
- [x] PostgreSQL is intended to be local-only on `127.0.0.1:5432`.
- [x] Deployment is script-driven through `serverctl` and `nightcraft-server-bootstrap.sh`.

## P0: Immediate Security Fixes

### 1. SSH Access

| Status | Check | Why | Verification |
| --- | --- | --- | --- |
| [ ] | Disable root SSH login. | Prevents direct root compromise. | `grep -E '^(PermitRootLogin|PasswordAuthentication|PubkeyAuthentication)' /etc/ssh/sshd_config` should show `PermitRootLogin no`, `PasswordAuthentication no`, `PubkeyAuthentication yes`. |
| [ ] | Disable password authentication. | Stops brute-force password attacks. | `sudo sshd -T \| grep passwordauthentication`. |
| [ ] | Ensure only trusted SSH keys are in `/home/dev/.ssh/authorized_keys`. | Limits who can log in. | `sudo cat /home/dev/.ssh/authorized_keys`. |
| [ ] | Prefer a separate admin user with sudo instead of using the app user for human login. | Separates deployment/runtime access from human admin access. | `getent passwd dev`; `groups dev`; `sudo -l -U dev`. |
| [ ] | If admin IP is fixed, restrict SSH to that IP. | Reduces SSH attack surface. | `sudo ufw status verbose` should show SSH allowed only from trusted IP. |

Example commands after backup:

```bash
sudo cp -a /etc/ssh/sshd_config /root/sshd_config.before-hardening.$(date +%Y%m%d_%H%M%S)
sudo nano /etc/ssh/sshd_config
sudo sshd -t
sudo systemctl reload ssh
```

Recommended SSH settings:

```sshconfig
PermitRootLogin no
PasswordAuthentication no
PubkeyAuthentication yes
KbdInteractiveAuthentication no
ChallengeResponseAuthentication no
UsePAM yes
```

### 2. Firewall

| Status | Check | Why | Verification |
| --- | --- | --- | --- |
| [ ] | Enable a host firewall. | Only intended ports should be reachable. | `sudo ufw status verbose`. |
| [ ] | Allow SSH and HTTP/HTTPS only from the internet. | Public server should not expose app/DB ports. | `sudo ufw status numbered`. |
| [ ] | Deny direct access to Gunicorn ports `5100,5333,5400,5500,5600,5800,5900`. | nginx should be the only public entrypoint. | `sudo ss -lntup`. |
| [ ] | Keep PostgreSQL bound to localhost only. | Database must not be internet-facing. | `sudo ss -lntup \| grep 5432`. |

Example baseline firewall:

```bash
sudo ufw default deny incoming
sudo ufw default allow outgoing
sudo ufw allow OpenSSH
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw enable
sudo ufw status verbose
```

If PostgreSQL is only local:

```bash
sudo ufw deny 5432/tcp
```

### 3. Secrets and Environment Files

| Status | Check | Why | Verification |
| --- | --- | --- | --- |
| [ ] | Confirm no production secrets are committed to git. | Repo secrets are high-impact leaks. | `git grep -iE 'SECRET|PASSWORD|TOKEN|DATABASE_URL|AUTHLIB_CLIENT_SECRET'` from each repo. |
| [ ] | Restrict `/etc/nightcraft` permissions. | Env files contain DB passwords, OAuth secrets, and signing keys. | `sudo find /etc/nightcraft -maxdepth 1 -type f -name '*.env' -printf '%m %u:%g %p\n'`. |
| [ ] | Rotate default/seed secrets if they were ever public. | Seed values are not acceptable for production. | Check GitHub, deploy logs, shell history, and old backups. |
| [ ] | Store bootstrap script outside repo. | Keeps deploy control plane separate from source code. | `ls -l /usr/local/sbin/server-scripts/nightcraft-server-bootstrap.sh`; `git -C /nightcraft-source-code status --short`. |

Recommended permissions:

```bash
sudo chown root:dev /etc/nightcraft
sudo chmod 0750 /etc/nightcraft
sudo chown root:dev /etc/nightcraft/*.env
sudo chmod 0640 /etc/nightcraft/*.env
```

### 4. TLS / Public HTTP

| Status | Check | Why | Verification |
| --- | --- | --- | --- |
| [ ] | Move production traffic from HTTP to HTTPS. | HTTP exposes cookies, OAuth codes, and session data. | Browser shows HTTPS; `curl -I http://31.70.85.89/` redirects to HTTPS. |
| [ ] | Add a real domain and obtain a trusted TLS certificate. | Standard Let's Encrypt certificates are normally issued for domain names, not bare IPs. | DNS A record points to `31.70.85.89`; `openssl s_client -connect 31.70.85.89:443 -servername your-domain.example`. |
| [ ] | Redirect all HTTP to HTTPS after TLS works. | Prevents accidental insecure usage. | `nginx -t && sudo systemctl reload nginx`. |
| [ ] | Enable secure cookie flags after HTTPS is live. | Cookies must not leak over HTTP. | App cookie settings use `Secure`, `HttpOnly`, and appropriate `SameSite`. |

If staying on a bare IP, treat the public HTTP admin/auth surfaces as temporary and consider SSH tunneling, VPN, or IP allowlisting for admin-only paths.

## P1: Server Hardening

### 5. OS Updates and Automatic Security Patches

| Status | Check | Why | Verification |
| --- | --- | --- | --- |
| [ ] | Install current Debian security updates. | Closes known OS vulnerabilities. | `sudo apt update && sudo apt full-upgrade -y`. |
| [ ] | Enable `unattended-upgrades`. | Applies security fixes automatically. | `sudo dpkg -l unattended-upgrades`; check `/etc/apt/apt.periodic/unattended-upgrades`. |
| [ ] | Reboot after kernel/security package updates. | Kernel fixes require reboot. | `sudo needrestart -r a` or `sudo reboot`. |
| [ ] | Remove unused packages. | Smaller attack surface. | `sudo deborphan` or manual package review. |

### 6. Intrusion Prevention and Logging

| Status | Check | Why | Verification |
| --- | --- | --- | --- |
| [ ] | Install and configure `fail2ban` for SSH and nginx. | Blocks repeated failed login/probe attempts. | `sudo fail2ban-client status sshd`. |
| [ ] | Enable persistent journald logs. | Logs survive reboot. | `grep -E '^Storage=' /etc/systemd/journald.conf`. |
| [ ] | Add log rotation and retention. | Keeps logs available without filling disk. | `sudo journalctl --disk-usage`; `/etc/logrotate.d/` entries. |
| [ ] | Install `auditd` for sensitive file access. | Provides tamper-evident file activity. | `sudo systemctl status auditd`. |
| [ ] | Monitor disk usage. | Full disks break services and logging. | `df -h`; alert when `/`, `/var`, `/runtime` exceed 80%. |

Example:

```bash
sudo apt install -y fail2ban auditd
sudo systemctl enable --now auditd
sudo systemctl enable --now fail2ban
sudo journalctl --vacuum-time=30d
```

### 7. Filesystem and Directory Permissions

| Status | Check | Why | Verification |
| --- | --- | --- | --- |
| [ ] | Keep source checkout under `/nightcraft-source-code` separate from runtime data. | Prevents runtime writes into code paths. | `find /nightcraft-source-code -maxdepth 2 -type d`. |
| [ ] | Keep runtime state under `/runtime/shared` and `/runtime/venvs`. | Matches current deployment design. | `ls -ld /runtime /runtime/shared /runtime/venvs`. |
| [ ] | Ensure `www-data` cannot write to app source or env files. | nginx should proxy only, not mutate files. | `namei -l /nightcraft-source-code/service-auth`; `namei -l /etc/nightcraft`. |
| [ ] | Restrict backup directory permissions. | Backups contain secrets and user data. | `sudo find /var/backups/nightcraft -maxdepth 1 -type d -printf '%m %u:%g %p\n'`. |

Recommended ownership model:

```bash
sudo chown -R dev:dev /nightcraft-source-code
sudo chown -R dev:dev /runtime/venvs
sudo chown -R dev:dev /runtime/shared
sudo chown -R root:root /var/backups/nightcraft
sudo chmod 0750 /var/backups/nightcraft
```

### 8. Systemd Service Hardening

| Status | Check | Why | Verification |
| --- | --- | --- | --- |
| [ ] | Keep `User=dev` and `Group=dev` on all app services. | Prevents root-owned app execution. | `systemctl cat nightcraft-auth.service`. |
| [ ] | Add `NoNewPrivileges=yes` to each service. | Blocks privilege escalation through setuid. | `systemctl cat nightcraft-*.service`. |
| [ ] | Add `PrivateTmp=yes`. | Isolates temporary files per service. | `systemctl cat nightcraft-*.service`. |
| [ ] | Add `ProtectSystem=full` and `ProtectHome=yes`. | Makes most filesystem read-only. | `systemctl cat nightcraft-*.service`. |
| [ ] | Add `ReadWritePaths=` for each app's runtime directory. | Allows needed writes only. | `systemctl cat nightcraft-*.service`. |
| [ ] | Test stricter sandboxing in batches. | Python apps can break under sandbox restrictions. | `sudo systemctl restart nightcraft-<service>` and smoke test URL. |

Example service additions:

```ini
NoNewPrivileges=yes
PrivateTmp=yes
ProtectSystem=full
ProtectHome=yes
ReadWritePaths=/runtime/shared/service-auth
ReadWritePaths=/runtime/shared/dev-podcast-app
ReadWritePaths=/runtime/shared/app-artsy
ReadWritePaths=/runtime/shared/app-note
RestrictSUIDSGID=yes
LockPersonality=yes
```

Add only the `ReadWritePaths` entries needed by each service.

## P1: nginx Hardening

### 9. Reverse Proxy Security

| Status | Check | Why | Verification |
| --- | --- | --- | --- |
| [ ] | Keep all upstreams bound to `127.0.0.1`. | Prevents direct app access. | `grep -R 'server 127.0.0.1' /etc/nginx/sites-enabled/nightcraft.conf`. |
| [ ] | Keep catch-all `server_name _` returning `444`. | Blocks unknown host routing. | `sudo nginx -T \| grep -A5 'server_name _'`. |
| [ ] | Add request rate limiting. | Reduces brute-force and scraping impact. | `sudo nginx -T \| grep limit_req`. |
| [ ] | Add security headers. | Hardens browser behavior. | `curl -I https://your-domain.example`. |
| [ ] | Keep `client_max_body_size` as small as practical. | Limits upload abuse. | Current `20m` may be acceptable only if uploads require it. |

Example nginx snippets:

```nginx
limit_req_zone $binary_remote_addr zone=nightcraft_req:10m rate=10r/s;
limit_conn_zone $binary_remote_addr zone=nightcraft_conn:10m;

server {
    listen 443 ssl http2;
    server_name your-domain.example;

    limit_req zone=nightcraft_req burst=30 nodelay;
    limit_conn nightcraft_conn 20;

    add_header X-Content-Type-Options nosniff always;
    add_header Referrer-Policy "strict-origin-when-cross-origin" always;
    add_header X-Frame-Options SAMEORIGIN always;
    add_header Content-Security-Policy "default-src 'self'; frame-ancestors 'self'; base-uri 'self'; object-src 'none'" always;
}
```

After HTTPS is stable:

```nginx
add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;
```

### 10. Admin and Auth Exposure

| Status | Check | Why | Verification |
| --- | --- | --- | --- |
| [ ] | Restrict `/admin/` to trusted users or trusted IP ranges if possible. | Admin paths should not be broadly exposed. | nginx `allow`/`deny` rules for `/admin/`. |
| [ ] | Ensure login, register, password reset, and OAuth endpoints have rate limits. | Protects central auth service. | Check auth service config and nginx rate limits. |
| [ ] | Confirm no open redirects are accepted. | Prevents phishing and OAuth redirect abuse. | Review auth redirect validation. |
| [ ] | Ensure CSRF protection is enabled for state-changing forms. | Prevents cross-site request forgery. | Manual login/logout/password reset tests. |

## P1: PostgreSQL Hardening

### 11. Database Access

| Status | Check | Why | Verification |
| --- | --- | --- | --- |
| [ ] | Confirm PostgreSQL listens only on localhost. | DB must not be public. | `sudo -u postgres psql -c "SHOW listen_addresses;"`. |
| [ ] | Confirm `pg_hba.conf` does not allow public `host` entries. | Prevents network DB access. | `sudo grep -vE '^#|^$' /etc/postgresql/*/main/pg_hba.conf`. |
| [ ] | Use `scram-sha-256` password auth. | Stronger PostgreSQL authentication. | `sudo -u postgres psql -c "SHOW password_encryption;"`. |
| [ ] | Rotate DB passwords periodically and after any suspected exposure. | Limits blast radius. | Use `reset-neera-password.sh` and similar rotation for auth/radio roles. |
| [ ] | Grant each role access only to its own database. | Least privilege. | Review `platform-infra/prod-debian/postgres/users-and-permissions.sql`. |

Example PostgreSQL checks:

```bash
sudo -u postgres psql -c "SHOW listen_addresses;"
sudo -u postgres psql -c "SHOW password_encryption;"
sudo grep -vE '^#|^$' /etc/postgresql/*/main/pg_hba.conf
sudo ss -lntup | grep 5432
```

### 12. Backups and Restore

| Status | Check | Why | Verification |
| --- | --- | --- | --- |
| [ ] | Run `serverctl backup` before major changes. | Captures DB, env files, and shared data. | `sudo platform-infra/prod-debian/scripts/serverctl backup`. |
| [ ] | Store backups outside the VPS. | VPS loss should not delete all backups. | Confirm backup copy in separate storage. |
| [ ] | Encrypt backups containing env files and DB dumps. | Backups contain secrets and user data. | Backup archive permissions and encryption status. |
| [ ] | Test restore on a separate machine or disposable VM. | Untested backups are not reliable. | Restore DB dump and app data; run smoke tests. |
| [ ] | Set backup retention. | Prevents indefinite secret retention. | Keep recent daily/weekly/monthly backups according to need. |

Existing backup entrypoint:

```bash
sudo platform-infra/prod-debian/scripts/serverctl backup
```

## P1: Auth, OAuth, and Application Secrets

### 13. Central Auth Service

| Status | Check | Why | Verification |
| --- | --- | --- | --- |
| [ ] | Replace all seed users with real production users. | Seed accounts are public knowledge from docs. | `seeduser`, `seedadmin`, and `devuser` should not be used as real admin accounts. |
| [ ] | Rotate `SECRET_KEY`, OIDC keys, and OAuth client secrets. | Secret rotation reduces exposure window. | Review `/etc/nightcraft/service-auth.env` and app env files. |
| [ ] | Use long random values for signing/session secrets. | Weak secrets allow forgery. | Generate with `openssl rand -hex 32` or stronger. |
| [ ] | Revoke existing sessions after secret rotation. | Old sessions may remain valid. | Test logout/login across `/auth`, `/neera`, `/game`, `/notestack`. |
| [ ] | Review password reset rate limits. | Prevents abuse. | Manual reset attempts and auth service logs. |
| [ ] | Confirm session cookies use `HttpOnly`, `Secure` after HTTPS, and `SameSite=Lax` or `Strict`. | Reduces session theft. | Browser devtools cookie inspection. |

### 14. OAuth Clients

| Status | Check | Why | Verification |
| --- | --- | --- | --- |
| [ ] | Audit OAuth clients for radio, NEERA, and game. | Unused clients expand attack surface. | Auth service admin/database client table. |
| [ ] | Restrict redirect URIs to exact approved URLs. | Prevents code/token theft. | Auth service OAuth client config. |
| [ ] | Rotate client secrets after any GitHub/deploy exposure. | Client secrets can impersonate apps. | App env files and auth DB. |
| [ ] | Remove unused OAuth clients. | Least privilege. | Compare seeded clients to deployed apps. |

## P1: Deployment Pipeline Security

### 15. GitHub Actions and SSH Deployment

| Status | Check | Why | Verification |
| --- | --- | --- | --- |
| [ ] | Keep deploy SSH key restricted to the VPS and required user. | Limits key abuse. | GitHub Actions secrets and VPS `authorized_keys`. |
| [ ] | Use GitHub environment protection for production. | Requires review/approval before deploy. | Repository settings: Environments. |
| [ ] | Restrict who can push to `main`. | Prevents unreviewed production deploys. | GitHub branch protection. |
| [ ] | Keep action versions pinned. | Prevents supply-chain drift. | `.github/workflows/deploy.yml` already pins `appleboy/ssh-action@v1.2.5`. |
| [ ] | Validate bootstrap script accepts only expected repo URL and branch. | Prevents CI from deploying malicious repo/branch. | Review `/usr/local/sbin/server-scripts/nightcraft-server-bootstrap.sh`. |
| [ ] | Keep bootstrap script outside `/nightcraft-source-code`. | Source checkout should not control its own deploy mechanism. | `ls -ld /usr/local/sbin/server-scripts /nightcraft-source-code`. |

### 16. Deployment Safety

| Status | Check | Why | Verification |
| --- | --- | --- | --- |
| [ ] | Run backup before destructive or env-overwriting deploys. | Protects data and secrets. | `/runtime/deploy-history.csv`; `/var/backups/nightcraft`. |
| [ ] | Avoid `install-env.sh --overwrite` unless secrets are intentionally refreshed. | Prevents accidental secret replacement. | Review deploy logs in `/var/log/nightcraft-deploy/`. |
| [ ] | Keep deploy logs readable only by admins. | Logs may contain paths, secrets, or stack traces. | `sudo find /var/log/nightcraft-deploy -maxdepth 1 -printf '%m %u:%g %p\n'`. |
| [ ] | Review failed deploys before retrying. | Repeated deploys can hide partial failures. | `sudo tail -n 200 /var/log/nightcraft-deploy/*.log`. |

## P2: Monitoring, Incident Response, and Maintenance

### 17. Health Checks and Alerts

| Status | Check | Why | Verification |
| --- | --- | --- | --- |
| [ ] | Monitor service health. | Detects outages quickly. | `platform-infra/prod-debian/scripts/serverctl status`. |
| [ ] | Monitor nginx access/error logs. | Finds attacks and broken routes. | `/var/log/nginx/access.log`, `/var/log/nginx/error.log`. |
| [ ] | Monitor app logs by service. | Captures auth failures and app errors. | `sudo journalctl -u nightcraft-auth -n 100 --no-pager`. |
| [ ] | Add uptime monitoring for public URLs. | External visibility into availability. | Test `/`, `/auth/`, `/admin/`, `/neera/`, `/notestack/`. |
| [ ] | Alert on disk, memory, failed logins, and service restarts. | Prevents silent degradation. | Monitoring provider or cron-based checks. |

Useful commands:

```bash
platform-infra/prod-debian/scripts/serverctl status
sudo systemctl list-units --type=service --state=failed
sudo journalctl -u nginx -n 100 --no-pager
sudo journalctl -u nightcraft-auth -n 100 --no-pager
sudo df -h
sudo free -h
sudo ss -lntup
```

### 18. Incident Response Runbook

| Status | Check | Why | Verification |
| --- | --- | --- | --- |
| [ ] | Keep an offline list of critical secrets and where they are stored. | Speeds rotation. | SSH keys, GitHub secrets, DB passwords, OAuth secrets, auth `SECRET_KEY`, OIDC keys. |
| [ ] | Define containment steps. | Limits damage during compromise. | Disable affected user, block IP, stop service if needed. |
| [ ] | Define rotation steps. | Restores trust after exposure. | Rotate SSH keys, GitHub deploy key, env secrets, DB passwords, OAuth client secrets, OIDC keys. |
| [ ] | Define restore steps. | Recovers from destructive attacks. | Restore DB and shared data from tested backup. |
| [ ] | Review auth and deploy logs after incidents. | Determines blast radius. | `/var/log/nightcraft-deploy/`, `journalctl`, auth DB session tables. |

Minimum rotation order after suspected compromise:

1. Revoke exposed SSH keys and replace VPS `authorized_keys`.
2. Rotate GitHub Actions deploy secrets.
3. Rotate `/etc/nightcraft/*.env` secrets.
4. Rotate PostgreSQL role passwords.
5. Rotate OAuth client secrets.
6. Rotate auth service signing/session secrets and revoke sessions.
7. Redeploy with updated secrets.
8. Review logs for unauthorized sessions or deploys.

## Recommended Hardening Order

1. Run `serverctl backup`.
2. Harden SSH and firewall.
3. Add TLS with a real domain.
4. Restrict `/etc/nightcraft` and backup permissions.
5. Rotate seed/default secrets.
6. Add fail2ban, auditd, persistent logs, and monitoring.
7. Add systemd sandboxing in small batches.
8. Add nginx rate limits and security headers.
9. Harden PostgreSQL auth and backups.
10. Add GitHub environment protection and branch protection.

## Post-Change Verification

After any hardening change:

```bash
sudo nginx -t
sudo systemctl reload nginx
platform-infra/prod-debian/scripts/serverctl status
sudo systemctl list-units --type=service --state=failed
sudo ss -lntup
```

Smoke-test:

```text
/
/auth/
/admin/
/devradio/
/neera/
/notestack/
```

For HTTPS deployments, verify cookies and redirects:

```bash
curl -I http://31.70.85.89/
curl -I https://your-domain.example/
```
