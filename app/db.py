# app/db.py
import os
from sqlmodel import SQLModel, create_engine, Session
from .settings import load_settings

_settings = load_settings()

# Render için güvenli SQLite yolu
if _settings.database_url.startswith("sqlite:////"):
    db_path = _settings.database_url.replace("sqlite:////", "/opt/render/project/src/")
    os.makedirs(os.path.dirname(db_path), exist_ok=True)

engine = create_engine(_settings.database_url.replace("/data", "/opt/render/project/src/data"), echo=False, future=True)

def init_db():
    if _settings.database_url.startswith("sqlite"):
        with engine.connect() as conn:
            conn.exec_driver_sql("PRAGMA foreign_keys=ON")

    from . import models
    SQLModel.metadata.create_all(engine)

def get_session():
    return Session(engine)
