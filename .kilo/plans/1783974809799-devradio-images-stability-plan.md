# DevRadio: Fix missing images + stop server freeze

## Diagnosis

**1. Images never appear (text still shows)**
- `devradio/utils.py::sanitize_article_html` uses a strict allow-list (`_ARTICLE_ALLOWED_TAGS`) that does **not** include `img`, and `img` is not in `_ARTICLE_REMOVE_TAGS` either. Every `<img>` therefore hits `tag.unwrap()` → the tag is deleted, only children remain. The fetched article body HTML loses all inline images while keeping text — exactly matching "text shows, images never do."
- The lead `image_url` (og:image / RSS) is already rendered in templates (`article_detail.html`, `channel_page.html`, `player.html`, `bookmarks.html` via `<img src="{{ article.image_url }}" ...>`), but:
  - `source_fetch.py::fetch()` returns `image_url` **only** on `status=="ok"`; on `too_short`/`too_long` it returns early with `image_url=None`, discarding the already-extracted lead image.
  - The automated path (`automation.py`) sets `image_url=fetched.image_url` only on a fully successful fetch and ignores the RSS entry's own image.
- Body `<img>` that are relative URLs would also resolve against our host when hotlinked, so they must be absolutized at extraction time.

**2. Server freezes / whole site slow (the "breaking the server" bug)**
- VM: 1.8 GB RAM, **0 swap**, already at 1.6 GB used → `kswapd0` at 37% CPU, load avg ~5–11 = swap/page-cache thrash. This is global (affects all apps on the box).
- `nightcraft-radio.service` runs **`--workers 3`** (~100 MB RSS each ≈ 300 MB for devradio alone).
- `radio.env.example` sets `FLASK_AUTOMATED_BACKGROUND_ENABLED=true`, so **each of the 3 gunicorn worker processes also spawns the automated-ingestion background thread** (`_start_automated_worker` in `create_app`). Only one acquires the cross-process `flock`, but all 3 allocate a `requests.Session` + parser memory, and on startup the loop runs `run_automated_ingestion()` **immediately** (no initial delay) — up to 48 full-page fetches + robots.txt fetches + `BeautifulSoup` parsing (240 s budget). Restarting to recover re-triggers this exact memory spike → global thrash → "freeze."
- `listener.py::article_detail` loads the **entire channel's article list** (`Article.query.filter_by(channel_id=...).order_by(...).all()`) just to find prev/next, amplifying memory pulls on every article view.

**Decisions confirmed with user**
- Stability: reduce workers + add swap **and** move ingestion into its own systemd timer (out of gunicorn workers).
- Images: keep hotlinking (render original URLs, no storage, no extra scraping); fix the sanitizer to allow `<img>` with safe attrs + `referrerpolicy="no-referrer"`, and reliably capture the lead image URL.

---

## Part 1 — Make images render (hotlinked, not stored)

### 1.1 Allow `<img>` through the sanitizer (`app-radio/devradio/utils.py`)
- Add `"img"` to `_ARTICLE_ALLOWED_TAGS`.
- Add `_ARTICLE_ALLOWED_ATTRS["img"] = {"src", "alt", "title", "loading", "referrerpolicy", "width", "height"}`.
- In the tag loop, for `img`:
  - Keep `src` only if it is an absolute `http(s)` URL (new helper `_is_safe_image_src`, mirroring `_is_safe_link` but rejecting relative/anchor/data URIs). If unsafe, drop the `src` (or remove the tag).
  - Force `tag["referrerpolicy"] = "no-referrer"` and `tag["loading"] = "lazy"` (reduces origin hotlink-blocking risk — directly supports the "don't get blocked" goal).
  - All other non-allowed attrs (e.g. `srcset`, `data-*`) are already stripped by the existing attr loop.

### 1.2 Keep images at fetch time (`app-radio/devradio/services/source_fetch.py`)
- In `_extract_main_html`: change `.decompose()` on `["picture","figure"]` to `.unwrap()` so any contained `<img>` survives into the stored body.
- Absolutize body image URLs: when building the body HTML, rewrite each `<img src>` (and `srcset`) to absolute via `urljoin(source_url, src)`. Pass `source_url` into `_extract_main_html` from `fetch()`.
- In `fetch()`: extract `image_url` as today, but **also return it on `too_short`/`too_long`** results (`FetchResult(text=None, status="too_short", image_url=image_url)`), so the lead image is captured even when the article text is below `min_chars`.

### 1.3 Reliably populate `image_url` (`app-radio/devradio/services/automation.py`)
- Compute `feed_image = _extract_feed_entry_image(entry)` (import the existing helper from `ingestion.py` into a shared location or `automation.py`) and set `image_url = feed_image or fetched.image_url` when creating the automated article (currently only `fetched.image_url`).
- `ingest_articles` already uses `feed_image or page_image`; with 1.2's fix `page_image` is now populated even on `too_short`, so no further change needed there.

### 1.4 (Optional) Widen column
- `models.py`: `image_url = db.Column(db.String(1000), ...)` → `String(2000)` (some og:image URLs exceed 1000 chars). Schema-migration guard in `__init__.py` already runs `ALTER TABLE` for `image_url`; update both.

---

## Part 2 — Stop the freeze / restore stability

### 2.1 Reduce gunicorn workers (`platform-infra/prod-debian/systemd/nightcraft-radio.service`)
- `--workers 3` → `--workers 1` (low-traffic personal site; saves ~200 MB and removes the 3× background-thread multiplication). Bump to 2 only if concurrency is needed.

### 2.2 Move ingestion out of gunicorn (separate systemd timer)
- New shared module `app-radio/devradio/services/process_lock.py` containing `_acquire_process_lock` / `_release_process_lock` (moved out of `devradio/__init__.py` to avoid a circular import; update `__init__.py` to import them).
- `automation.py::run_automated_ingestion`: additionally acquire the cross-process `flock` (same lock-file path as the old worker) around the run, so the **timer runner and the manual `/admin/automated/run-now` trigger can never overlap**. If the lock is held, return the existing `skipped_concurrent` style result.
- `radio.env.example`: set `FLASK_AUTOMATED_BACKGROUND_ENABLED=false` so `create_app()` no longer spawns the in-process worker thread under gunicorn. (The standalone runner calls `run_automated_ingestion()` directly and ignores this flag.)
- New `platform-infra/prod-debian/systemd/nightcraft-radio-ingest.service` (`Type=oneshot`):
  - `EnvironmentFile=/etc/nightcraft/app-radio.env`
  - `ExecStart=/runtime/venvs/dev-podcast-app/bin/python -m flask --app devradio automated-run`
  - (Reuses the existing `flask automated-run` CLI command; `create_app()` runs without starting a background thread because the flag is off.)
- New `platform-infra/prod-debian/systemd/nightcraft-radio-ingest.timer`:
  - `OnCalendar=*-*-* *:00:00` (hourly — "a few times a day"; tunable) with `RandomizedDelaySec=600` so runs are spread and never fire instantly after a reboot/restart.
  - `Persistent=false`.
- `deploy-radio.sh`: after restarting `nightcraft-radio.service`, also `systemctl enable --now nightcraft-radio-ingest.timer`.

### 2.3 Lower per-run cost (env) to shrink memory/network spikes
- In `radio.env.example` set lighter caps (all already configurable, defaults in `__init__.py`):
  - `FLASK_AUTOMATED_MAX_TOTAL_FETCHES=24` (was 48)
  - `FLASK_AUTOMATED_RUN_TIME_BUDGET_SECONDS=150` (was 240)
  - `FLASK_AUTOMATED_FEED_FETCH_LIMIT=5` (was 8)
- These reduce concurrent buffering of full HTML pages during a run.

### 2.4 Add swap (buffer against OOM thrash)
- New `platform-infra/prod-debian/scripts/ensure-swap.sh`: create a 2 GB `/swapfile` (`fallocate`/`dd`, `chmod 600`, `mkswap`, `swapon`), and add an `/etc/fstab` entry if missing. Idempotent. Run once on the VPS. With swap, a transient memory spike pages instead of freezing the whole box.

### 2.5 Stop loading the whole channel per article view (`app-radio/devradio/listener.py::article_detail`)
- Replace the full-channel `.all()` + index search with two bounded neighbor queries:
  ```python
  created = article.created_at
  prev_article = (Article.query.filter_by(channel_id=article.channel_id)
                  .filter(Article.created_at < created)
                  .order_by(Article.created_at.desc()).first())
  next_article = (Article.query.filter_by(channel_id=article.channel_id)
                  .filter(Article.created_at > created)
                  .order_by(Article.created_at.asc()).first())
  ```
  (Tie-break by `id` if `created_at` is not unique.) Loads at most 2 rows instead of the entire channel.

---

## Validation
1. On the VPS: `free -h` shows swap available and healthy free memory after deploy.
2. `sudo systemctl status nightcraft-radio.service nightcraft-radio-ingest.timer` — radio on 1 worker, timer enabled.
3. `sudo journalctl -u nightcraft-radio-ingest.service -n 50` after a scheduled/forced run: run completes, `new_articles` > 0, no OOM.
4. Manually trigger: `cd /nightcraft-source-code/app-radio && /runtime/venvs/dev-podcast-app/bin/python -m flask --app devradio automated-run` then inspect the DB / admin automated log; confirm `image_url` is populated on newly ingested articles.
5. `curl -s http://127.0.0.1:5333/devradio/article/<id> | grep -o '<img[^>]*>'` — confirm `<img>` tags are present in the article body and the hero image, with `src` pointing to the **origin** host (not 31.70.85.89) and `referrerpolicy="no-referrer"`.
6. Load a channel page and an article page in a browser; images render; visiting the pages does **not** freeze the server (`uptime` load average stays low, `kswapd0` near 0%).
7. Confirm manual `/admin/automated/run-now` while a timer run is in progress returns the "skipped_concurrent" result rather than running twice.

## Risks / open questions
- 1 worker lowers request concurrency; acceptable for this traffic, raise to 2 if needed.
- Some origins employ hotlink protection and will 403 the `<img>`; the template `onerror` already hides those. This is expected and does not load our server.
- `SOURCE_FETCH_RESPECT_ROBOTS=True` (default) may still limit coverage on strict sites; tune only if image/text yield is too low.
- Timer cadence (hourly) is a default — adjust `OnCalendar` if "a few times a day" should mean less often.
