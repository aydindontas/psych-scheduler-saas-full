import os
from dataclasses import dataclass
from datetime import time

@dataclass
class Settings:
    app_base_url: str
    jwt_secret: str
    jwt_expire_minutes: int
    whatsapp_verify_token: str
    whatsapp_access_token: str
    whatsapp_phone_number_id: str
    work_start: time
    work_end: time
    slot_minutes: int
    timezone: str
    reminder_24h: int
    reminder_1h: int
    zoom_join_url: str | None
    database_url: str  # 🆕 EKLENDİ — veritabanı bağlantısı için gerekli

def _pt(s: str) -> time:
    h, m = s.split(':')
    return time(int(h), int(m))

def load_settings() -> Settings:
    return Settings(
        app_base_url=os.getenv('APP_BASE_URL', 'http://localhost:8000'),
        jwt_secret=os.getenv('JWT_SECRET', 'change-me'),
        jwt_expire_minutes=int(os.getenv('JWT_EXPIRE_MINUTES', '43200')),
        whatsapp_verify_token=os.getenv('WHATSAPP_VERIFY_TOKEN', 'verify-123'),
        whatsapp_access_token=os.getenv('WHATSAPP_ACCESS_TOKEN', ''),
        whatsapp_phone_number_id=os.getenv('WHATSAPP_PHONE_NUMBER_ID', ''),
        work_start=_pt(os.getenv('WORK_START', '09:00')),
        work_end=_pt(os.getenv('WORK_END', '18:00')),
        slot_minutes=int(os.getenv('SLOT_MINUTES', '60')),
        timezone=os.getenv('TIMEZONE', 'Europe/Istanbul'),
        reminder_24h=int(os.getenv('REMINDER_24H', '1440')),
        reminder_1h=int(os.getenv('REMINDER_1H', '60')),
        zoom_join_url=(os.getenv('ZOOM_JOIN_URL') or '').strip() or None,
        database_url=os.getenv('DATABASE_URL', 'sqlite:////data.db'),  # 🧱 varsayılan veritabanı yolu
    )
