# app/db.py
import os
from sqlmodel import SQLModel, create_engine, Session
from .settings import load_settings

_settings = load_settings()

# 🧱 /data klasörünü oluştur (Render'da yoksa hata verir)
if _settings.database_url.startswith("sqlite:////"):
    db_path = _settings.database_url.replace("sqlite:////", "/")
    os.makedirs(os.path.dirname(db_path), exist_ok=True)

engine = create_engine(_settings.database_url, echo=False, future=True)

def init_db():
    # SQLite için faydalı (opsiyonel)
    if _settings.database_url.startswith("sqlite"):
        with engine.connect() as conn:
            conn.exec_driver_sql("PRAGMA foreign_keys=ON")

    # MODELLERİN YÜKLÜ OLDUĞUNDAN EMİN OLUN
    from . import models  # <-- User, Tenant, Client, Appointment import edilmiş olacak

    SQLModel.metadata.create_all(engine)  # <-- tablo oluşturur

def get_session():
    return Session(engine)
