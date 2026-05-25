# Dev Windows Script Hub

This folder is the script-first entrypoint for Windows development and local client/server runs.

## Folder Layout

- powershell/: executable scripts
- env/: environment templates for local overrides
- postgres/: local Postgres notes/scripts placeholders

## Quick Commands

Run from repo root or from this folder.

### 1) One-time setup

```powershell
.\platform-infra\dev-windows\powershell\setup-all.ps1
```

Curio only setup:

```powershell
.\platform-infra\dev-windows\powershell\setup-artsy.ps1
```

### 2) Seed auth + OAuth client

```powershell
.\platform-infra\dev-windows\powershell\seed-all.ps1 -RadioPort 5000
```

Include Curio OAuth client as well:

```powershell
.\platform-infra\dev-windows\powershell\seed-all.ps1 -RadioPort 5000 -IncludeArtsy -ArtsyPort 5600
```

When `-IncludeArtsy` is enabled, the same script also runs Curio's catalog seed so the artsy app starts with the shared test dataset.

### 3) Run auth server only (server mode)

```powershell
.\platform-infra\dev-windows\powershell\run-server.ps1
```

### 4) Run radio app only (client mode)

```powershell
.\platform-infra\dev-windows\powershell\run-client.ps1 -AuthMode sso -AuthServiceUrl http://127.0.0.1:5100
or
.\run-client.ps1 -AuthMode sso -AuthServiceUrl http://127.0.0.1:5100

```

Run Curio only:

```powershell
.\platform-infra\dev-windows\powershell\run-client.ps1 -App artsy -AuthMode sso -AuthServiceUrl http://127.0.0.1:5100
```

Equivalent Curio-focused shortcut:

```powershell
.\platform-infra\dev-windows\powershell\run-artsy.ps1 -AuthMode sso -AuthServiceUrl http://127.0.0.1:5100
```

### 5) Run both (dev mode)

```powershell
.\platform-infra\dev-windows\powershell\run-all.ps1
```

Run auth + radio + Curio:

```powershell
.\platform-infra\dev-windows\powershell\run-all.ps1 -IncludeArtsy
```

## Migrations

```powershell
.\platform-infra\dev-windows\powershell\migrate-all.ps1
```

This applies `service-auth` DB migrations and runs idempotent setup/schema sync for `app-radio` and `app-artsy`.

## Notes

- `run-all.ps1` starts service-auth and app-radio in separate PowerShell windows.
- Add `-IncludeArtsy` to also launch app-artsy.
- `seed-all.ps1` writes the callback redirect URI based on `-RadioPort`.
- Add `-IncludeArtsy` to also seed Curio's redirect URI based on `-ArtsyPort` and load Curio's seeded catalog.
- Both app startup scripts handle FLASK-prefixed env vars for SSO mode.
