from datetime import datetime, timezone

from flask import current_app, has_app_context
from zoneinfo import ZoneInfo


DEFAULT_APP_TIMEZONE = "Asia/Kolkata"


def now_utc():
    return datetime.now(timezone.utc)


def app_timezone_name():
    if has_app_context():
        return current_app.config.get("DEFAULT_TIMEZONE", DEFAULT_APP_TIMEZONE)
    return DEFAULT_APP_TIMEZONE


def safe_zoneinfo(tz_name):
    try:
        return ZoneInfo(tz_name)
    except Exception:
        return timezone.utc


def app_timezone():
    return safe_zoneinfo(app_timezone_name())


def now_app_timezone():
    return now_utc().astimezone(app_timezone())


def _parse_datetime(value, assume_tz=timezone.utc):
    if value is None:
        return None
    if isinstance(value, datetime):
        dt_value = value
    elif isinstance(value, str):
        candidate = value.strip()
        if not candidate:
            return None
        if candidate.endswith("Z"):
            candidate = candidate[:-1] + "+00:00"
        try:
            dt_value = datetime.fromisoformat(candidate)
        except ValueError:
            return None
    else:
        return None

    if dt_value.tzinfo is None:
        dt_value = dt_value.replace(tzinfo=assume_tz)
    return dt_value


def format_in_app_timezone(value, fmt="%Y-%m-%d %H:%M:%S %Z"):
    dt_value = _parse_datetime(value)
    if dt_value is None:
        return ""
    localized = dt_value.astimezone(app_timezone())
    return localized.strftime(fmt)
