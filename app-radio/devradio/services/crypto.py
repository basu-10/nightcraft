from __future__ import annotations

import base64
import hashlib

from cryptography.fernet import Fernet


class EncryptionService:
    _fernet = None

    @classmethod
    def configure(cls, app):
        key = app.config.get("APP_ENCRYPTION_KEY")
        if key:
            try:
                cls._fernet = Fernet(key.encode("utf-8"))
                return
            except Exception:
                derived = hashlib.sha256(key.encode("utf-8")).digest()
                raw_key = base64.urlsafe_b64encode(derived)
        else:
            derived = hashlib.sha256(app.config["SECRET_KEY"].encode("utf-8")).digest()
            raw_key = base64.urlsafe_b64encode(derived)
        cls._fernet = Fernet(raw_key)

    @classmethod
    def encrypt(cls, plaintext):
        if plaintext is None:
            return ""
        return cls._fernet.encrypt(plaintext.encode("utf-8")).decode("utf-8")

    @classmethod
    def decrypt(cls, ciphertext):
        if not ciphertext:
            return ""
        return cls._fernet.decrypt(ciphertext.encode("utf-8")).decode("utf-8")
