from datetime import datetime, timedelta, timezone
from jose import jwt
from passlib.hash import bcrypt, bcrypt_sha256

# Şifreleme: bcrypt_sha256 (72 bayt sınırını aşmak için)
def hash_password(p: str) -> str:
    return bcrypt_sha256.hash(p)

def verify_password(p: str, h: str) -> bool:
    # Eski hash'ler için geriye dönük uyumluluk: önce bcrypt_sha256 dene, olmazsa bcrypt dene
    try:
        return bcrypt_sha256.verify(p, h)
    except Exception:
        try:
            return bcrypt.verify(p, h)
        except Exception:
            return False

def create_access_token(subject: str, secret: str, minutes: int) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": subject,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=minutes)).timestamp()),
    }
    return jwt.encode(payload, secret, algorithm="HS256")
