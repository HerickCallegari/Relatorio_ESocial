from itsdangerous import BadSignature, URLSafeSerializer
from passlib.context import CryptContext

from app.settings import settings


pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
serializer = URLSafeSerializer(settings.app_secret_key, salt="auth-session")


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    return pwd_context.verify(password, password_hash)


def sign_session(user_id: int) -> str:
    return serializer.dumps({"user_id": user_id})


def read_session(value: str | None) -> int | None:
    if not value:
        return None
    try:
        payload = serializer.loads(value)
    except BadSignature:
        return None
    user_id = payload.get("user_id")
    return int(user_id) if user_id else None

