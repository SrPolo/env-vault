from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

# Argon2id with library defaults (OWASP-recommended parameters).
_hasher = PasswordHasher()

# Precomputed hash used only to equalize login timing when the email is unknown.
# Generated once with the same hasher so verify() always does real Argon2 work.
_DUMMY_HASH = _hasher.hash("timing-equalization-dummy-password")


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return _hasher.verify(password_hash, password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def verify_password_or_dummy(password: str, password_hash: str | None) -> bool:
    """
    Verify against the real hash, or against a dummy hash when the user/hash is
    missing. Prevents timing-based email enumeration on login.
    """
    if password_hash is None:
        verify_password(password, _DUMMY_HASH)
        return False
    return verify_password(password, password_hash)
