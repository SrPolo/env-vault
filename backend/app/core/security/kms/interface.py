from typing import Protocol


class KMSProviderProtocol(Protocol):
    """
    Interface for Key Management Service (KMS) providers.
    
    This abstracts the envelope encryption layer. The KMS is responsible
    for encrypting and decrypting the Data Encryption Keys (DEKs) using
    a Master Key.
    """

    def encrypt_dek(self, plain_dek: bytes) -> bytes:
        """
        Encrypts a plaintext Data Encryption Key (DEK) using the Master Key.
        
        Args:
            plain_dek: The raw bytes of the DEK.
            
        Returns:
            The encrypted DEK (wrapped DEK).
        """
        ...

    def decrypt_dek(self, wrapped_dek: bytes) -> bytes:
        """
        Decrypts a wrapped Data Encryption Key (DEK) using the Master Key.
        
        Args:
            wrapped_dek: The encrypted bytes of the DEK.
            
        Returns:
            The plaintext DEK.
        """
        ...

    def generate_dek(self) -> bytes:
        """
        Generates a new, cryptographically secure plaintext DEK.
        Typically 32 bytes for AES-256.
        
        Returns:
            The raw bytes of the newly generated DEK.
        """
        ...
