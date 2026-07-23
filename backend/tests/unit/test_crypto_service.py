from cryptography.exceptions import InvalidTag
import pytest

from app.core.security.kms.local import LocalKMSProvider
from app.services.crypto import CryptoService


@pytest.fixture
def crypto() -> CryptoService:
    return CryptoService(LocalKMSProvider(master_key_str="crypto-service-test-key"))


class TestCryptoService:
    def test_create_wrapped_dek_is_opaque(self, crypto: CryptoService) -> None:
        wrapped = crypto.create_wrapped_dek()
        assert isinstance(wrapped, bytes)
        assert len(wrapped) >= 28

    def test_encrypt_decrypt_roundtrip(self, crypto: CryptoService) -> None:
        wrapped_dek = crypto.create_wrapped_dek()
        ciphertext, iv = crypto.encrypt_secret("super-secret-value", wrapped_dek)

        assert ciphertext != b"super-secret-value"
        assert len(iv) == 12
        assert crypto.decrypt_secret(ciphertext, iv, wrapped_dek) == "super-secret-value"

    def test_encrypt_produces_unique_ciphertext(self, crypto: CryptoService) -> None:
        wrapped_dek = crypto.create_wrapped_dek()
        first, iv1 = crypto.encrypt_secret("same-value", wrapped_dek)
        second, iv2 = crypto.encrypt_secret("same-value", wrapped_dek)

        assert first != second
        assert iv1 != iv2

    def test_decrypt_rejects_tampered_ciphertext(self, crypto: CryptoService) -> None:
        wrapped_dek = crypto.create_wrapped_dek()
        ciphertext, iv = crypto.encrypt_secret("secret", wrapped_dek)
        tampered = ciphertext[:-1] + bytes([ciphertext[-1] ^ 0x01])

        with pytest.raises(InvalidTag):
            crypto.decrypt_secret(tampered, iv, wrapped_dek)

    def test_decrypt_rejects_wrong_iv(self, crypto: CryptoService) -> None:
        wrapped_dek = crypto.create_wrapped_dek()
        ciphertext, _iv = crypto.encrypt_secret("secret", wrapped_dek)
        wrong_iv = b"\x00" * 12

        with pytest.raises(InvalidTag):
            crypto.decrypt_secret(ciphertext, wrong_iv, wrapped_dek)

    def test_decrypt_rejects_wrong_dek(self, crypto: CryptoService) -> None:
        wrapped_a = crypto.create_wrapped_dek()
        wrapped_b = crypto.create_wrapped_dek()
        ciphertext, iv = crypto.encrypt_secret("secret", wrapped_a)

        with pytest.raises(InvalidTag):
            crypto.decrypt_secret(ciphertext, iv, wrapped_b)

    def test_supports_unicode_and_empty_values(self, crypto: CryptoService) -> None:
        wrapped_dek = crypto.create_wrapped_dek()
        for value in ("", "áéíóú", "🔐 vault", "line1\nline2"):
            ciphertext, iv = crypto.encrypt_secret(value, wrapped_dek)
            assert crypto.decrypt_secret(ciphertext, iv, wrapped_dek) == value
