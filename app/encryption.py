import os
import logging
from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy.types import TypeDecorator, Text

logger = logging.getLogger(__name__)

_key = os.getenv("ENCRYPTION_KEY")
if not _key:
    raise RuntimeError(
        "ENCRYPTION_KEY is not set. Generate one with:\n"
        '  python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"\n'
        "and add it to your environment (.env locally, Render's Environment tab in production)."
    )
_fernet = Fernet(_key.encode())


def encrypt_text(plaintext):
    """Encrypts a string for storage. None passes through unchanged."""
    if plaintext is None:
        return None
    return _fernet.encrypt(plaintext.encode()).decode()


def decrypt_text(value):
    """
    Decrypts a value produced by encrypt_text(). Falls back to returning
    the raw value unchanged if it isn't a valid Fernet token — this covers
    rows written before encryption was added (plain text), so old data
    doesn't crash the app; it just stays readable-as-is until it's next
    overwritten by a write that goes through encrypt_text().
    """
    if value is None:
        return None
    try:
        return _fernet.decrypt(value.encode()).decode()
    except (InvalidToken, ValueError, UnicodeDecodeError):
        return value


class EncryptedText(TypeDecorator):
    """
    A Text column that's encrypted at rest automatically. Every place that
    reads or writes this column through the ORM sees plain text as normal —
    only the raw database file (or a direct SQL query bypassing the app)
    ever sees ciphertext.
    """
    impl = Text
    cache_ok = True

    def process_bind_param(self, value, dialect):
        return encrypt_text(value)

    def process_result_value(self, value, dialect):
        return decrypt_text(value)