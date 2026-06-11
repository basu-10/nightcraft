# SeekSage Backend

SeekSage backend is a Flask app with REST APIs, authentication, and a hybrid UI layer.

## UI modes

- Flask UI is the default root experience at `/`.
- Flask UI remains directly accessible at `/ui`.
- Implemented in Flask UI:
  - `/ui/login`
  - `/ui/dashboard`
  - `/ui/notes`
  - `/ui/notifications`
  - `/ui/account`
  - `/ui/global-settings`
  - `/ui/admin`
- The React Workspace SPA is built from `frontend/` during production deploy and served from the Flask frontend dist directory when `frontend/dist/index.html` exists.
- Behind the Nightcraft nginx proxy, the React Workspace SPA is available at `/seeksage/ui`.
- The production deploy builds the React Workspace SPA with `VITE_BASE_PATH=/seeksage/`; this keeps asset URLs, client-side routes, and API calls stable under the `/seeksage` path prefix.
- Flask UI templates expose `window.SEEK_API_BASE="/seeksage"` when served behind the Nightcraft proxy and `""` when served directly, so `/ui` API calls do not double-prefix under local/direct Flask routes.
- If the React build is skipped because `npm` is unavailable, `/ui` falls back to the Flask dashboard.

## Workspace UI behavior

- The Workspace nav link is first in the Flask UI navigation.
- Workspace settings are hidden until a workspace exists; the no-workspace fix shows a prompt to create a workspace first instead of rendering an empty settings form.
- Workspace settings preserve explicit `null` values returned by the API.
- Settings save failures are caught so a failed policy/profile update does not leave the UI in a broken pending state.
- Stale `activeWorkspaceId` values are cleared from `localStorage` when all workspaces are deleted.

## Agent response metadata

- Final answers include a `Usage Stats` section.
- Usage stats summarize searches, tool calls/results/cache hits/errors/timeouts, LLM calls/replies/retries/errors, run time, and model names.
- Usage stats are also stored in the assistant message metadata for replay/debugging.

## PDF report tool

- `create_pdf` converts research findings into a PDF report using WeasyPrint.
- Supported templates: `research_report`, `procurement_report`, `comparison_report`, and `financial_report`.
- Supported styles: `clean`, `dense`, and `executive`.
- If WeasyPrint cannot render the PDF, the tool saves an HTML fallback.
- Debian/Linux deployments need the WeasyPrint system packages listed in `requirements.txt`.

## Run locally

```powershell
cd app-researchAgent/seeksage/backend
python run.py
```

Open:

- Flask UI (default): `http://127.0.0.1:5000/`
- Flask UI direct path: `http://127.0.0.1:5000/ui`

To temporarily disable root redirect and use the React dist at `/` when available:

```powershell
$env:SEEKSAGE_UI_AT_ROOT = "0"
python run.py
```

To override the frontend dist directory:

```powershell
$env:SEEKSAGE_FRONTEND_DIST = "D:\dev_work\web_dev\personal site\ionos-server\app-researchAgent\seeksage\frontend\dist"
python run.py
```

To build the React Workspace SPA manually for local path-prefix testing:

```powershell
cd app-researchAgent/seeksage/frontend
npm ci
$env:VITE_BASE_PATH = "/seeksage/"
npm run build
```

The local Vite dev server proxies `/api`, `/auth`, and `/admin` to the Flask backend; production uses the Flask-served dist and the `SEEK_API_BASE` template value to keep API calls aligned with `/seeksage`.

## Testing note

The current test harness requires `TEST_DATABASE_URL` to be set (PostgreSQL DSN) before running pytest.

```powershell
$env:TEST_DATABASE_URL = "postgresql://USER:PASS@127.0.0.1:5432/DB"
pytest -q
```

