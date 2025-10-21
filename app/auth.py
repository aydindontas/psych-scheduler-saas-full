from datetime import datetime, timedelta, timezone
from jose import jwt
from passlib.hash import bcrypt

def hash_password(p:str)->str:
    return bcrypt.hash(p)

def verify_password(p:str, h:str)->bool:
    return bcrypt.verify(p, h)

def create_access_token(subject: str, secret: str, minutes: int) -> str:
    now = datetime.now(timezone.utc)
    payload = {'sub': subject, 'iat': int(now.timestamp()), 'exp': int((now+timedelta(minutes=minutes)).timestamp())}
    return jwt.encode(payload, secret, algorithm='HS256')
