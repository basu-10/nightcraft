# app-game

A small Flask game hub inspired by the project structure used in `app-radio`.

## Goal

Create a landing page that links to lightweight browser games such as:
- Highest Number
- Rock Paper Scissors

## Quick start

1. Create and activate a virtual environment.
2. Install dependencies:

```powershell
pip install -r requirements.txt
```

3. Run the app:

```powershell
python run.py
```

4. Open `http://127.0.0.1:5320/` in your browser.

## Structure

- `run.py` — local development entrypoint
- `wsgi.py` — production entrypoint
- `config.py` — configuration loader
- `game/` — app package with blueprint routes and templates
- `static/` — shared static assets

## Next steps

- Add more games as separate route modules or blueprints.
- Replace the placeholder pages with full game logic.
- Add tests under `tests/` when the app is ready.
