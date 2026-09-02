import hashlib
import secrets

def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode("utf-8")).hexdigest()

def check_password(password: str, stored_hash: str) -> bool:
    return secrets.compare_digest(hash_password(password), stored_hash)
