from app.core.security.passwords import (
    hash_password,
    verify_password,
    verify_password_or_dummy,
)
from app.core.security.tokens import (
    create_access_token,
    decode_access_token,
    generate_refresh_token,
    hash_refresh_token,
)


def test_hash_and_verify_password_roundtrip() -> None:
    hashed = hash_password("correct-horse-battery")
    assert hashed != "correct-horse-battery"
    assert verify_password("correct-horse-battery", hashed) is True
    assert verify_password("wrong-password", hashed) is False


def test_verify_password_or_dummy_unknown_user_returns_false() -> None:
    assert verify_password_or_dummy("anything", None) is False


def test_verify_password_or_dummy_with_real_hash() -> None:
    hashed = hash_password("s3cret")
    assert verify_password_or_dummy("s3cret", hashed) is True
    assert verify_password_or_dummy("nope", hashed) is False


def test_access_token_roundtrip() -> None:
    token = create_access_token("11111111-1111-1111-1111-111111111111")
    payload = decode_access_token(token)
    assert payload["sub"] == "11111111-1111-1111-1111-111111111111"
    assert payload["type"] == "access"


def test_refresh_token_hash_is_deterministic_and_not_raw() -> None:
    raw = generate_refresh_token()
    digest = hash_refresh_token(raw)
    assert digest == hash_refresh_token(raw)
    assert digest != raw
    assert len(digest) == 64
