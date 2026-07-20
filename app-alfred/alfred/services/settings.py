from ..models import AppSetting
from .crypto import EncryptionService


def get_setting(key, default=""):
    setting = AppSetting.query.filter_by(key=key).first()
    if not setting:
        return default
    if setting.encrypted:
        return EncryptionService.decrypt(setting.value)
    return setting.value


def upsert_setting(key, value, encrypted=False):
    setting = AppSetting.query.filter_by(key=key).first()
    payload = EncryptionService.encrypt(value) if encrypted else value
    if setting:
        setting.value = payload
        setting.encrypted = encrypted
    else:
        setting = AppSetting(key=key, value=payload, encrypted=encrypted)
    return setting


def get_setting_int(key, default):
    raw_value = get_setting(key, "")
    try:
        return int(raw_value)
    except (TypeError, ValueError):
        return default


def get_setting_float(key, default):
    raw_value = get_setting(key, "")
    try:
        return float(raw_value)
    except (TypeError, ValueError):
        return default
