from sqlalchemy import text
from app.database import SessionLocal, engine
from app.models import Conversation
from app.encryption import encrypt_text, decrypt_text


def test_encrypt_decrypt_round_trip():
    plaintext = "This is a private message about work stress."
    ciphertext = encrypt_text(plaintext)
    assert ciphertext != plaintext
    assert decrypt_text(ciphertext) == plaintext


def test_decrypt_handles_legacy_plaintext_gracefully():
    # Rows written before encryption was added are plain text, not a valid
    # Fernet token — decrypting them must not crash the app.
    assert decrypt_text("just some old plain text") == "just some old plain text"


def test_encrypt_decrypt_handles_none():
    assert encrypt_text(None) is None
    assert decrypt_text(None) is None


def test_conversation_content_is_actually_encrypted_in_the_database():
    db = SessionLocal()
    db.query(Conversation).filter(Conversation.user_id == "encryption_test_user").delete()
    db.commit()

    secret_message = "unique-marker-should-never-appear-in-raw-sql-output"
    db.add(Conversation(
        user_id="encryption_test_user",
        session_id="s1",
        role="user",
        content=secret_message
    ))
    db.commit()
    db.close()

    # Bypass the ORM entirely and read the raw column value directly —
    # this is what someone with only database access (no app, no key)
    # would actually see.
    with engine.connect() as conn:
        raw = conn.execute(
            text("SELECT content FROM conversations WHERE user_id = :uid"),
            {"uid": "encryption_test_user"}
        ).scalar()
    assert secret_message not in raw

    # Reading it back through the ORM decrypts it transparently — no
    # application code needs to know encryption is happening.
    db = SessionLocal()
    row = db.query(Conversation).filter(Conversation.user_id == "encryption_test_user").first()
    db.close()
    assert row.content == secret_message