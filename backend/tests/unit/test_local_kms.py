from cryptography.exceptions import InvalidTag
import pytest

from app.core.security.kms.local import LocalKMSProvider


@pytest.fixture
def kms() -> LocalKMSProvider:
    return LocalKMSProvider(master_key_str="unit-test-master-key")


class TestLocalKMSProvider:
    def test_generate_dek_is_32_bytes(self, kms: LocalKMSProvider) -> None:
        dek = kms.generate_dek()
        assert len(dek) == 32

    def test_generate_dek_is_unique(self, kms: LocalKMSProvider) -> None:
        assert kms.generate_dek() != kms.generate_dek()

    def test_wrap_and_unwrap_roundtrip(self, kms: LocalKMSProvider) -> None:
        plain_dek = kms.generate_dek()
        wrapped = kms.encrypt_dek(plain_dek)

        assert wrapped != plain_dek
        assert len(wrapped) >= 28  # 12 nonce + ciphertext + 16 tag
        assert kms.decrypt_dek(wrapped) == plain_dek

    def test_wrapped_dek_includes_random_nonce(self, kms: LocalKMSProvider) -> None:
        plain_dek = kms.generate_dek()
        first = kms.encrypt_dek(plain_dek)
        second = kms.encrypt_dek(plain_dek)
        assert first != second
        assert kms.decrypt_dek(first) == plain_dek
        assert kms.decrypt_dek(second) == plain_dek

    def test_decrypt_rejects_truncated_payload(self, kms: LocalKMSProvider) -> None:
        wrapped = kms.encrypt_dek(kms.generate_dek())
        tampered = wrapped[:-1] + bytes([wrapped[-1] ^ 0xFF])

        with pytest.raises(InvalidTag):
            kms.decrypt_dek(tampered)

    def test_decrypt_rejects_too_short_payload(self, kms: LocalKMSProvider) -> None:
        with pytest.raises(ValueError, match="too short"):
            kms.decrypt_dek(b"short")

    def test_different_master_keys_cannot_decrypt(self, kms: LocalKMSProvider) -> None:
        wrapped = kms.encrypt_dek(kms.generate_dek())
        other = LocalKMSProvider(master_key_str="a-completely-different-master-key")

        with pytest.raises(InvalidTag):
            other.decrypt_dek(wrapped)
