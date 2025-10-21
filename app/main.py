import os, secrets
from fastapi import FastAPI, Request, Depends, HTTPException, Header, Query
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from sqlmodel import Session, select
from datetime import datetime, timedelta, timezone

from .db import init_db, get_session
from .models import Tenant, User, Client, Appointment
from .settings import load_settings
from .auth import hash_password, verify_password, create_access_token
from .logic import working_slots, busy_from_db, ensure_client
from .whatsapp import send_whatsapp_text
from .scheduler import start_scheduler, schedule_all

settings = load_settings()
app = FastAPI(title="Psych Scheduler SaaS")
init_db()

if os.path.isdir("static"):
from fastapi.responses import FileResponse

# Statik dosyaları /static altında sun
app.mount("/static", StaticFiles(directory="static"), name="static")

# Ana sayfa: static/index.html
@app.get("/", response_class=HTMLResponse)
def root():
    return FileResponse("static/index.html")


def tznow(): return datetime.now(timezone.utc)

scheduler = start_scheduler()
scheduler.start()

def reschedule_all(session: Session):
    schedule_all(session, scheduler, settings.reminder_24h, settings.reminder_1h, settings.zoom_join_url,
                 {"access_token": settings.whatsapp_access_token, "phone_number_id": settings.whatsapp_phone_number_id})

from jose import jwt, JWTError
def current_user(authorization: str = Header(None), session: Session = Depends(get_session)) -> User:
    if not authorization: raise HTTPException(401, "Auth gerekli")
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer": raise HTTPException(401, "Bearer bekleniyor")
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=["HS256"])
        uid = int(payload["sub"])
    except JWTError:
        raise HTTPException(401, "Token geçersiz")
    u = session.get(User, uid)
    if not u: raise HTTPException(401, "Kullanıcı yok")
    return u

@app.get("/health")
def health():
    return {"ok": True}

@app.get("/", response_class=HTMLResponse)
def home():
    return HTMLResponse("<h1>Psych Scheduler SaaS</h1><p>Static UI yüklüyse otomatik sunulur.</p>")

@app.post("/api/auth/signup")
async def signup(req: Request, session: Session = Depends(get_session)):
    data = await req.json()
    email = data["email"].strip().lower()
    password = data["password"]
    name = data.get("clinic","Klinik")
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
    u = session.exec(select(User).where(User.email==email)).first()
    if not u or not verify_password(password, u.password_hash):
        raise HTTPException(status_code=401, detail="Geçersiz bilgiler")
    token = create_access_token(subject=str(u.id), secret=settings.jwt_secret, minutes=settings.jwt_expire_minutes)
    reschedule_all(session)
    tenant = session.get(Tenant, u.tenant_id)
    return {"access_token": token, "tenant_key": tenant.tenant_key}

@app.get("/api/me")
def me(u: User = Depends(current_user), session: Session = Depends(get_session)):
    tenant = session.get(Tenant, u.tenant_id)
    return {"email": u.email, "tenant": {"name": tenant.name, "tenant_key": tenant.tenant_key}}

@app.get("/api/appointments")
def list_appointments(u: User = Depends(current_user), session: Session = Depends(get_session)):
    appts = session.exec(select(Appointment).where(Appointment.tenant_id==u.tenant_id).order_by(Appointment.start.desc())).all()
    out = []
    for a in appts:
        c = session.get(Client, a.client_id)
        out.append({"id": a.id, "phone": c.phone if c else "-", "start": a.start.isoformat(), "end": a.end.isoformat(), "status": a.status, "source": a.source})
    return out

@app.post("/api/appointments")
async def create_appointment(req: Request, u: User = Depends(current_user), session: Session = Depends(get_session)):
    data = await req.json()
    phone = data["phone"]
    start = datetime.fromisoformat(data["start"])
    end = datetime.fromisoformat(data["end"])
    client = ensure_client(session, u.tenant_id, phone)
    appt = Appointment(tenant_id=u.tenant_id, client_id=client.id, start=start, end=end, status="confirmed", source="manual")
    session.add(appt); session.commit(); session.refresh(appt)
    zoom_text = f"\nZoom: {settings.zoom_join_url}" if settings.zoom_join_url else ""
    send_whatsapp_text(settings.whatsapp_access_token, settings.whatsapp_phone_number_id, phone, f"Randevunuz onaylandı: {start.astimezone().strftime('%d.%m.%Y %H:%M')}{zoom_text}")
    reschedule_all(session)
    return {"id": appt.id}

@app.get("/whatsapp/webhook/{tenant_key}")
def wa_verify(tenant_key: str, mode: str = Query(None, alias="hub.mode"),
              challenge: str = Query(None, alias="hub.challenge"),
              token: str = Query(None, alias="hub.verify_token"), session: Session = Depends(get_session)):
    t = session.exec(select(Tenant).where(Tenant.tenant_key==tenant_key)).first()
    if not t: return PlainTextResponse("tenant not found", status_code=404)
    if mode == "subscribe" and token == settings.whatsapp_verify_token:
        return PlainTextResponse(challenge or "")
    return PlainTextResponse("forbidden", status_code=403)

@app.post("/whatsapp/webhook/{tenant_key}")
async def wa_webhook(tenant_key: str, req: Request, session: Session = Depends(get_session)):
    t = session.exec(select(Tenant).where(Tenant.tenant_key==tenant_key)).first()
    if not t: return JSONResponse({"status":"no tenant"}, status_code=404)
    body = await req.json()
    try:
        entry = body["entry"][0]["changes"][0]["value"]
        message = entry["messages"][0]
        from_phone = message["from"]
        text_body = message.get("text", {}).get("body", "").strip().lower()
    except Exception:
        return JSONResponse({"status":"ignored"})

    intent = "help"
    if any(k in text_body for k in ["randevu","rezerv","al"]): intent="book"
    elif any(k in text_body for k in ["iptal","cancel"]): intent="cancel"
    elif any(k in text_body for k in ["bugün","yarın","hafta","uygun","saat"]): intent="availability"

    day = tznow()
    db_busy = busy_from_db(session, t.id, day.replace(hour=0, minute=0), day.replace(hour=0, minute=0)+timedelta(days=1))
    avail = working_slots(day, settings.work_start, settings.work_end, settings.slot_minutes, settings.timezone)
    free = [(s,e) for (s,e) in avail if not any(max(s,b1)<min(e,b2) for (b1,b2) in db_busy)]

    if intent in ["book","availability"]:
        if not free:
            send_whatsapp_text(settings.whatsapp_access_token, settings.whatsapp_phone_number_id, from_phone, "Bugün için uygun saat yok. 'yarın' veya 'hafta' yazabilirsiniz.")
        else:
            formatted = "\n".join([f"- {s.astimezone().strftime('%H:%M')} - {e.astimezone().strftime('%H:%M')}" for s,e in free[:10]])
            send_whatsapp_text(settings.whatsapp_access_token, settings.whatsapp_phone_number_id, from_phone, f"Uygun saatler:\n{formatted}\n\nRezerv için 'YYYY-MM-DD HH:MM' yazın.")
    elif intent=="cancel":
        client = session.exec(select(Client).where(Client.tenant_id==t.id).where(Client.phone==from_phone)).first()
        if not client:
            send_whatsapp_text(settings.whatsapp_access_token, settings.whatsapp_phone_number_id, from_phone, "Kayıtlı randevunuz bulunamadı.")
        else:
            appt = session.exec(select(Appointment).where(Appointment.tenant_id==t.id).where(Appointment.client_id==client.id).where(Appointment.status=='confirmed').where(Appointment.start>tznow()).order_by(Appointment.start)).first()
            if not appt:
                send_whatsapp_text(settings.whatsapp_access_token, settings.whatsapp_phone_number_id, from_phone, "İptal edilecek randevu bulunamadı.")
            else:
                appt.status='cancelled'; session.add(appt); session.commit()
                send_whatsapp_text(settings.whatsapp_access_token, settings.whatsapp_phone_number_id, from_phone, "Randevunuz iptal edildi.")
                reschedule_all(session)
    else:
        send_whatsapp_text(settings.whatsapp_access_token, settings.whatsapp_phone_number_id, from_phone, "Merhaba! 'randevu al', 'bugün', 'yarın' veya 'iptal' yazabilirsiniz.")

    try:
        from dateutil import parser
        dt = parser.parse(text_body)
        start = dt.replace(second=0, microsecond=0).astimezone(timezone.utc)
        end = start + timedelta(minutes=settings.slot_minutes)
        clash = any(max(start,b1)<min(end,b2) for (b1,b2) in db_busy)
        if clash:
            send_whatsapp_text(settings.whatsapp_access_token, settings.whatsapp_phone_number_id, from_phone, "Seçtiğiniz saat dolu. Başka bir saat dener misiniz?")
        else:
            client = ensure_client(session, t.id, from_phone)
            appt = Appointment(tenant_id=t.id, client_id=client.id, start=start, end=end, status='confirmed', source='whatsapp')
            session.add(appt); session.commit()
            zoom_text = f"\nZoom: {settings.zoom_join_url}" if settings.zoom_join_url else ""
            send_whatsapp_text(settings.whatsapp_access_token, settings.whatsapp_phone_number_id, from_phone, f"Randevunuz onaylandı: {start.astimezone().strftime('%d.%m.%Y %H:%M')}{zoom_text}")
            reschedule_all(session)
    except Exception:
        pass

    return JSONResponse({"status":"ok"})
