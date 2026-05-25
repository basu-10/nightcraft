import base64
import hashlib
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa


def _b64url_uint(value):
    raw = value.to_bytes((value.bit_length() + 7) // 8, "big")
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _derive_kid(public_pem_bytes):
    digest = hashlib.sha256(public_pem_bytes).hexdigest()
    return f"rsa-{digest[:16]}"


def load_or_create_signing_keypair(keys_dir):
    keys_path = Path(keys_dir)
    keys_path.mkdir(parents=True, exist_ok=True)

    private_key_path = keys_path / "oidc_private_key.pem"
    public_key_path = keys_path / "oidc_public_key.pem"

    if private_key_path.exists() and public_key_path.exists():
        private_pem = private_key_path.read_bytes()
        public_pem = public_key_path.read_bytes()
    else:
        private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        public_key = private_key.public_key()

        private_pem = private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
        public_pem = public_key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        private_key_path.write_bytes(private_pem)
        public_key_path.write_bytes(public_pem)

    private_key = serialization.load_pem_private_key(private_pem, password=None)
    public_key = serialization.load_pem_public_key(public_pem)
    kid = _derive_kid(public_pem)

    public_numbers = public_key.public_numbers()
    jwk = {
        "kty": "RSA",
        "use": "sig",
        "kid": kid,
        "alg": "RS256",
        "n": _b64url_uint(public_numbers.n),
        "e": _b64url_uint(public_numbers.e),
    }

    return {
        "kid": kid,
        "private_key": private_key,
        "public_key": public_key,
        "private_pem": private_pem.decode("utf-8"),
        "public_pem": public_pem.decode("utf-8"),
        "jwk": jwk,
    }
