import hashlib
import secrets


def hash_password(password: str, salt: str | None = None) -> str:
    actual_salt = salt or secrets.token_hex(16)
    digest = hashlib.scrypt(
        password.encode("utf-8"),
        salt=actual_salt.encode("utf-8"),
        n=16384,
        r=8,
        p=1,
    )
    return f"{actual_salt}${digest.hex()}"


def verify_password(password: str, encoded: str) -> bool:
    salt, _ = encoded.split("$", 1)
    return hash_password(password, salt=salt) == encoded


def generate_access_token() -> str:
    return f"la_{secrets.token_urlsafe(32)}"


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()
