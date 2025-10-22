import os, secrets
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from fastapi import FastAPI, Request, Depends, HTTPException, Header, Query
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from sqlmodel import Session, select

from .db import init_db, get_session
from .models import Tenant, User, Client, Appointment
from .settings import load_settings
from .auth import hash_password, verify_password, create_access_token
from .logic import working_slots, busy_from_db, ensure_client
from .whatsapp import send_whatsapp_text
from .scheduler import start_scheduler, schedule_all

# ----------------- App & Settings -----------------
settings = load_settings()
app = FastAPI(title="Psych Scheduler SaaS")
init_db()

# Statik dosyalar
app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/", response_class=HTMLResponse)
def root():
    if os.path.exists("static/index.html"):
        return FileResponse("static/index.html")
    return HTMLResponse("<h1>Psych Scheduler SaaS</h1><p>UI için static/index.html ekleyin.</p>")

# Kısa yollar
@app.get("/dashboard", response_class=HTMLResponse)
def _dash():
    path = "static/dashboard.html"
    if os.path.exists(path):
        return FileResponse(path)
    raise HTTPException(404, "dashboard.html yok")

@app.get("/schedule", response_class=HTMLResponse)
def _schedule():
    path = "static/schedule.html"
    if os.path.exists(path):
        return FileResponse(path)
    raise HTTPException(404, "schedule.html yok")

def tznow():
    return datetime.now(timezone.utc)

# ----------------- Scheduler -----------------
scheduler = start_scheduler()
scheduler.start()

def reschedule_all(session: Session):
    schedule_all(
        session,
        scheduler,
        settings.reminder_24h,
        settings.reminder_1h,
        settings.zoom_join_url,
        {"access_token": settings.whatsapp_access_token, "phone_number_id": settings.whatsapp_phone_number_id},
    )

# ----------------- Auth helper -----------------
from jose import jwt, JWTError

def current_user(authorization: str = Header(None), session: Session = Depends(get_session)) -> User:
    if not authorization:
        raise HTTPException(401, "Auth gerekli")
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer":
        raise HTTPException(401, "Bearer bekleniyor")
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=["HS256"])
        uid = int(payload["sub"])
    except JWTError:
        raise HTTPException(401, "Token geçersiz")
    u = session.get(User, uid)
    if not u:
        raise HTTPException(401, "Kullanıcı yok")
    return u

# ----------------- Health -----------------
@app.get("/health")
def health():
    return {"ok": True}

# ----------------- Auth APIs -----------------
@app.post("/api/auth/signup")
async def signup(req: Request, session: Session = Depends(get_session)):
    data = await req.json()
    email = data["email"].strip().lower()
    password = data["password"]
    name = data.get("clinic", "Klinik")

    if len(password) < 6:
        raise HTTPException(status_code=400, detail="Şifre en az 6 karakter olmalı")

    tenant = Tenant(name=name, tenant_key=secrets.token_urlsafe(6))
    session.add(tenant); session.commit(); session.refresh(tenant)

    u = User(tenant_id=tenant.id, email=email, password_hash=hash_password(password), role="admin")
    session.add(u); session.commit(); session.refresh(u)

    token = create_access_token(subject=str(u.id), secret=settings.jwt_secret, minutes=settings.jwt_expire_minutes)
    reschedule_all(session)
    return {"access_token": token, "tenant_key": tenant.tenant_key}

@app.post("/api/auth/login")
async def login(req: Request, session: Session = Depends(get_session)):
    data = await req.json()
    email = data["email"].strip().lower()
    password = data["password"]
    u = session.exec(select(User).where(User.email == email)).first()
    if not u or not verify_password(password, u.password_hash):
        raise HTTPException(401, "Geçersiz bilgiler")
    token = create_access_token(subject=str(u.id), secret=settings.jwt_secret, minutes=settings.jwt_expire_minutes)
    reschedule_all(session)
    tenant = session.get(Tenant, u.tenant_id)
    return {"access_token": token, "tenant_key": tenant.tenant_key}

@app.get("/api/me")
def me(u: User = Depends(current_user), session: Session = Depends(get_session)):
    tenant = session.get(Tenant, u.tenant_id)
    return {"email": u.email, "tenant": {"name": tenant.name, "tenant_key": tenant.tenant_key}}

# --------------- Helpers ----------------
def _parse_start_end_from_payload(payload: dict) -> tuple[datetime, datetime]:
    """
    Esnek tarih/saat parse:
      - start (ISO) + end (ISO)
      - starts_at (ISO) + duration (dk)
      - date (YYYY-MM-DD) + time (HH:MM) + duration (dk)
    Return: (start_utc, end_utc)
    """
    tz = ZoneInfo(getattr(settings, "timezone", "Europe/Istanbul"))

    # 1) start + end (ISO)
    if "start" in payload and "end" in payload:
        start = datetime.fromisoformat(payload["start"])
        end = datetime.fromisoformat(payload["end"])
        return start.astimezone(timezone.utc), end.astimezone(timezone.utc)

    # 2) starts_at (ISO) + duration
    if "starts_at" in payload:
        start = datetime.fromisoformat(payload["starts_at"])
        duration = int(payload.get("duration", getattr(settings, "slot_minutes", 60)))
        end = start + timedelta(minutes=duration)
        return start.astimezone(timezone.utc), end.astimezone(timezone.utc)

    # 3) date + time + duration (yerel timezone'a göre)
    if "date" in payload and "time" in payload:
        duration = int(payload.get("duration", getattr(settings, "slot_minutes", 60)))
        # yerel tz aware -> sonra UTC
        local_dt = datetime.fromisoformat(f"{payload['date']}T{payload['time']}:00").replace(tzinfo=tz)
        start = local_dt.astimezone(timezone.utc)
        end = start + timedelta(minutes=duration)
        return start, end

    raise HTTPException(400, "Tarih/saat formatı eksik veya hatalı")

def _send_whatsapp_safe(phone: str, text: str):
    if getattr(settings, "whatsapp_access_token", None) and getattr(settings, "whatsapp_phone_number_id", None):
        try:
            send_whatsapp_text(settings.whatsapp_access_token, settings.whatsapp_phone_number_id, phone, text)
        except Exception:
            # Sessiz geç
            pass

# ----------------- Appointments -----------------
@app.get("/api/appointments")
def list_appointments(u: User = Depends(current_user), session: Session = Depends(get_session)):
    appts = session.exec(
        select(Appointment).where(Appointment.tenant_id == u.tenant_id).order_by(Appointment.start.desc())
    ).all()
    out = []
    for a in appts:
        c = session.get(Client, a.client_id)
        out.append({
            "id": a.id,
            "phone": c.phone if c else "-",
            "start": a.start.isoformat(),
            "end": a.end.isoformat(),
            "status": a.status,
            "source": a.source,
        })
    return out

@app.get("/api/appointments/upcoming")
def list_upcoming_appointments(limit: int = 20, u: User = Depends(current_user), session: Session = Depends(get_session)):
    now = tznow()
    rows = session.exec(
        select(Appointment)
        .where(Appointment.tenant_id == u.tenant_id, Appointment.start >= now)
        .order_by(Appointment.start)
        .limit(limit)
    ).all()
    out = []
    for a in rows:
        c = session.get(Client, a.client_id)
        out.append({
            "id": a.id,
            "phone": c.phone if c else "-",
            "start": a.start.isoformat(),
            "end": a.end.isoformat(),
            "status": a.status,
            "source": a.source,
        })
    return out

# app/main.py (yalnızca /api/appointments içinde değişiklik)
from zoneinfo import ZoneInfo

@app.post("/api/appointments")
async def create_appointment(req: Request, u: User = Depends(current_user), session: Session = Depends(get_session)):
    data = await req.json()
    phone = data["phone"]

    # İstemciden gelen 'start' naive olabilir -> timezone ekle
    local_tz = ZoneInfo(settings.timezone)  # örn. Europe/Istanbul

    raw_start = datetime.fromisoformat(data["start"])  # '2025-10-24T13:00'
    if raw_start.tzinfo is None:
        start = raw_start.replace(tzinfo=local_tz).astimezone(timezone.utc)
    else:
        start = raw_start.astimezone(timezone.utc)

    # end'i ya istemciden al ya da slot süresine göre hesapla
    if "end" in data and data["end"]:
        raw_end = datetime.fromisoformat(data["end"])
        if raw_end.tzinfo is None:
            end = raw_end.replace(tzinfo=local_tz).astimezone(timezone.utc)
        else:
            end = raw_end.astimezone(timezone.utc)
    else:
        end = start + timedelta(minutes=settings.slot_minutes)

    client = ensure_client(session, u.tenant_id, phone)
    appt = Appointment(
        tenant_id=u.tenant_id, client_id=client.id,
        start=start, end=end, status="confirmed", source="manual"
    )
    session.add(appt); session.commit(); session.refresh(appt)

    # Onay mesajı (Zoom linki dahil)
    zoom_text = f"\nZoom: {settings.zoom_join_url}" if settings.zoom_join_url else ""
    # Kullanıcıya okunur olması için yerel saate çevirerek gönderelim
    start_local = start.astimezone(local_tz).strftime('%d.%m.%Y %H:%M')
    send_whatsapp_text(
        settings.whatsapp_access_token, settings.whatsapp_phone_number_id, phone,
        f"Randevunuz onaylandı: {start_local}{zoom_text}"
    )

    reschedule_all(session)
    return {"id": appt.id}

# ----------------- WhatsApp Webhook -----------------
@app.get("/whatsapp/webhook/{tenant_key}")
def wa_verify(
    tenant_key: str,
    mode: str = Query(None, alias="hub.mode"),
    challenge: str = Query(None, alias="hub.challenge"),
    token: str = Query(None, alias="hub.verify_token"),
    session: Session = Depends(get_session),
):
    t = session.exec(select(Tenant).where(Tenant.tenant_key == tenant_key)).first()
    if not t:
        return PlainTextResponse("tenant not found", status_code=404)
    if mode == "subscribe" and token == settings.whatsapp_verify_token:
        return PlainTextResponse(challenge or "")
    return PlainTextResponse("forbidden", status_code=403)

@app.post("/whatsapp/webhook/{tenant_key}")
async def wa_webhook(tenant_key: str, req: Request, session: Session = Depends(get_session)):
    t = session.exec(select(Tenant).where(Tenant.tenant_key == tenant_key)).first()
    if not t:
        return JSONResponse({"status": "no tenant"}, status_code=404)

    body = await req.json()
    try:
        entry = body["entry"][0]["changes"][0]["value"]
        message = entry["messages"][0]
        from_phone = message["from"]
        text_body = message.get("text", {}).get("body", "").strip().lower()
    except Exception:
        return JSONResponse({"status": "ignored"})

    # intent belirleme
    intent = "help"
    if any(k in text_body for k in ["randevu", "rezerv", "al"]):
        intent = "book"
    elif any(k in text_body for k in ["iptal", "cancel"]):
        intent = "cancel"
    elif any(k in text_body for k in ["bugün", "yarın", "hafta", "uygun", "saat"]):
        intent = "availability"

    # bugün için uygun saatleri çıkar
    day = tznow()
    db_busy = busy_from_db(session, t.id, day.replace(hour=0, minute=0), day.replace(hour=0, minute=0) + timedelta(days=1))
    avail = working_slots(day, settings.work_start, settings.work_end, settings.slot_minutes, settings.timezone)
    free = [(s, e) for (s, e) in avail if not any(max(s, b1) < min(e, b2) for (b1, b2) in db_busy)]

    if intent in ["book", "availability"]:
        if not free:
            _send_whatsapp_safe(from_phone, "Bugün için uygun saat yok. 'yarın' veya 'hafta' yazabilirsiniz.")
        else:
            formatted = "\n".join([f"- {s.astimezone().strftime('%H:%M')} - {e.astimezone().strftime('%H:%M')}" for s, e in free[:10]])
            _send_whatsapp_safe(from_phone, f"Uygun saatler:\n{formatted}\n\nRezerv için 'YYYY-MM-DD HH:MM' yazın.")
    elif intent == "cancel":
        client = session.exec(select(Client).where(Client.tenant_id == t.id).where(Client.phone == from_phone)).first()
        if not client:
            _send_whatsapp_safe(from_phone, "Kayıtlı randevunuz bulunamadı.")
        else:
            appt = session.exec(
                select(Appointment)
                .where(Appointment.tenant_id == t.id)
                .where(Appointment.client_id == client.id)
                .where(Appointment.status == 'confirmed')
                .where(Appointment.start > tznow())
                .order_by(Appointment.start)
            ).first()
            if not appt:
                _send_whatsapp_safe(from_phone, "İptal edilecek randevu bulunamadı.")
            else:
                appt.status = 'cancelled'
                session.add(appt); session.commit()
                _send_whatsapp_safe(from_phone, "Randevunuz iptal edildi.")
                reschedule_all(session)
    else:
        _send_whatsapp_safe(from_phone, "Merhaba! 'randevu al', 'bugün', 'yarın' veya 'iptal' yazabilirsiniz.")

    # Eğer mesaj açıkça bir tarih-saat ise rezerv yap
    try:
        from dateutil import parser
        dt = parser.parse(text_body)
        start = dt.replace(second=0, microsecond=0).astimezone(timezone.utc)
        end = start + timedelta(minutes=settings.slot_minutes)
        clash = any(max(start, b1) < min(end, b2) for (b1, b2) in db_busy)
        if clash:
            _send_whatsapp_safe(from_phone, "Seçtiğiniz saat dolu. Başka bir saat dener misiniz?")
        else:
            client = ensure_client(session, t.id, from_phone)
            appt = Appointment(tenant_id=t.id, client_id=client.id, start=start, end=end, status='confirmed', source='whatsapp')
            session.add(appt); session.commit()
            zoom_text = f"\nZoom: {settings.zoom_join_url}" if settings.zoom_join_url else ""
            _send_whatsapp_safe(from_phone, f"Randevunuz onaylandı: {start.astimezone().strftime('%d.%m.%Y %H:%M')}{zoom_text}")
            reschedule_all(session)
    except Exception:
        pass

    return JSONResponse({"status": "ok"})
