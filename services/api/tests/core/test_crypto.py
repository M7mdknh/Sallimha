from core.crypto import decrypt_text, encrypt_text, keyed_hash, new_code, new_token


def test_encrypt_roundtrip_and_ciphertext_hides_value():
    token = encrypt_text("+966501234567")
    assert "966501234567" not in token
    assert decrypt_text(token) == "+966501234567"


def test_keyed_hash_is_purpose_separated_and_stable():
    assert keyed_hash("+966501234567", "phone") == keyed_hash("+966501234567", "phone")
    assert keyed_hash("+966501234567", "phone") != keyed_hash("+966501234567", "token")


def test_new_token_is_high_entropy_and_unique():
    tokens = {new_token() for _ in range(200)}
    assert len(tokens) == 200
    assert all(len(t) >= 32 for t in tokens)


def test_new_code_is_six_digits():
    for _ in range(100):
        code = new_code()
        assert len(code) == 6 and code.isdigit()
