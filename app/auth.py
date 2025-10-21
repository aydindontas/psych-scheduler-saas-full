from datetime import datetime, timedelta, timezone
from jose import jwt
from passlib.hash import pbkdf2_sha256, bcrypt, bcrypt_sha256  # bcrypt* sadece geriye dönük uyumluluk için

# Ana şifre şeması: PBKDF2-SHA256  (bcrypt'e bağımlılık yok, 72 byte sınırı yok)
def hash_password(p: str) -> str:
    # rounds = 29000 default; istersen 200k+ yapabilirsin
    return pbkdf2_sha256.hash(p)

def verify_password(p: str, h: str) -> bool:
    # 1) yeni şema
    try:
        return pbkdf2_sha256.verify(p, h)
    except Exception:
        pass
    # 2) eski olası hash'ler için geriye dönük uyumluluk
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

