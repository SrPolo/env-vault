import hashlib
import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.core.config import settings
from .interface import KMSProviderProtocol


class LocalKMSProvider(KMSProviderProtocol):
    """
    Local implementation of the KMS provider for development and testing.
    
    Uses AES-256-GCM to encrypt/decrypt DEKs locally using a Master Key
    provided via environment variables.
    """

    def __init__(self, master_key_str: str | None = None) -> None:
        """
        Initializes the LocalKMSProvider.
        
        Args:
            master_key_str: Optional master key. If not provided, it falls
                            back to the ENCRYPTION_MASTER_KEY from settings.
        """
        key_str = master_key_str or settings.ENCRYPTION_MASTER_KEY
        
        # Derive a strict 32-byte (256-bit) key for AES-GCM using SHA-256.
        # This ensures we always have a valid key size regardless of the input string length.
        self._master_key: bytes = hashlib.sha256(key_str.encode("utf-8")).digest()
        
        self._aesgcm = AESGCM(self._master_key)

    def generate_dek(self) -> bytes:
        """
        Generates a 32-byte (256-bit) cryptographically secure random key
        to be used as a DEK (suitable for AES-256).
        """
        return os.urandom(32)

    def encrypt_dek(self, plain_dek: bytes) -> bytes:
        """
        Encrypts the plaintext DEK using AES-256-GCM with the Master Key.
        
        The resulting wrapped DEK has the following format:
        [12-byte nonce] + [ciphertext] + [16-byte auth tag (handled by AESGCM)]
        """
        # AES-GCM standard nonce size is 12 bytes
        nonce = os.urandom(12)
        
        # AESGCM.encrypt appends the 16-byte authentication tag to the ciphertext automatically
        ciphertext = self._aesgcm.encrypt(nonce, plain_dek, associated_data=None)
        
        # Prepend the nonce so we can extract it during decryption
        return nonce + ciphertext

    def decrypt_dek(self, wrapped_dek: bytes) -> bytes:
        """
        Decrypts the wrapped DEK using AES-256-GCM with the Master Key.
        
        Expects the wrapped DEK in the format:
        [12-byte nonce] + [ciphertext + 16-byte auth tag]
        """
        if len(wrapped_dek) < 28:
            # 12 bytes (nonce) + at least 1 byte (ciphertext) + 16 bytes (tag) is not strictly enforced length,
            # but empty plaintext means 12 + 0 + 16 = 28 bytes.
            raise ValueError("Wrapped DEK is too short to be valid")

        nonce = wrapped_dek[:12]
        ciphertext = wrapped_dek[12:]
        
        # AESGCM.decrypt validates the auth tag automatically
        return self._aesgcm.decrypt(nonce, ciphertext, associated_data=None)
