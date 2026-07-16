import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.core.security.kms.interface import KMSProviderProtocol


class CryptoService:
    """
    Handles envelope encryption logic for secrets.
    Uses the provided KMS (Key Management Service) to encrypt/decrypt Data Encryption Keys (DEKs),
    and uses those DEKs to encrypt/decrypt the actual secret values.
    """

    def __init__(self, kms_provider: KMSProviderProtocol):
        self.kms = kms_provider

    def create_wrapped_dek(self) -> bytes:
        """
        Generates a new secure Data Encryption Key (DEK) and returns it wrapped 
        (encrypted) by the Master Key using the KMS provider.
        
        Returns:
            bytes: The encrypted DEK (wrapped_dek).
        """
        plain_dek = self.kms.generate_dek()
        wrapped_dek = self.kms.encrypt_dek(plain_dek)
        return wrapped_dek

    def encrypt_secret(self, plain_value: str, wrapped_dek: bytes) -> tuple[bytes, bytes]:
        """
        Encrypts a plaintext secret value using the environment's wrapped DEK.
        
        Args:
            plain_value: The raw secret value string.
            wrapped_dek: The encrypted DEK retrieved from the database.
            
        Returns:
            tuple: A tuple containing (encrypted_value, iv) where both are bytes.
        """
        # 1. Decrypt the DEK in memory
        plain_dek = self.kms.decrypt_dek(wrapped_dek)
        
        # 2. Encrypt the secret using AES-256-GCM with the plaintext DEK
        aesgcm = AESGCM(plain_dek)
        iv = os.urandom(12) # Standard nonce size for AES-GCM is 12 bytes
        
        # Associated data could be used in the future to tie the ciphertext to a specific secret ID
        encrypted_value = aesgcm.encrypt(iv, plain_value.encode("utf-8"), associated_data=None)
        
        return encrypted_value, iv

    def decrypt_secret(self, encrypted_value: bytes, iv: bytes, wrapped_dek: bytes) -> str:
        """
        Decrypts a stored secret using the environment's wrapped DEK and its Initialization Vector (IV).
        
        Args:
            encrypted_value: The encrypted secret bytes from the database.
            iv: The Initialization Vector (nonce) used during encryption.
            wrapped_dek: The encrypted DEK retrieved from the database.
            
        Returns:
            str: The decrypted plaintext secret value.
        """
        # 1. Decrypt the DEK in memory
        plain_dek = self.kms.decrypt_dek(wrapped_dek)
        
        # 2. Decrypt the secret using AES-256-GCM
        aesgcm = AESGCM(plain_dek)
        plain_bytes = aesgcm.decrypt(iv, encrypted_value, associated_data=None)
        
        return plain_bytes.decode("utf-8")
