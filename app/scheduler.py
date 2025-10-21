from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.date import DateTrigger
from datetime import datetime, timedelta, timezone
from sqlmodel import Session, select
from .models import Appointment, Client
from .whatsapp import send_whatsapp_text

def start_scheduler():
    return BackgroundScheduler(timezone=timezone.utc)

def schedule_all(session: Session, scheduler: BackgroundScheduler, reminder_24m: int, reminder_1h: int, zoom_url: str | None, send_args: dict):
    for job in scheduler.get_jobs():
        job.remove()
    now = datetime.now(timezone.utc)
    appts = session.exec(select(Appointment).where(Appointment.status=='confirmed').where(Appointment.start>now)).all()
    for a in appts:
        _schedule(a, session, scheduler, reminder_24m, reminder_1h, zoom_url, send_args)

def _schedule(a: Appointment, session: Session, scheduler: BackgroundScheduler, reminder_24m: int, reminder_1h: int, zoom_url: str | None, send_args: dict):
    client = session.get(Client, a.client_id)
    if not client: return
    now = datetime.now(timezone.utc)
    def msg(prefix:str):
        z = f"\nZoom: {zoom_url}" if zoom_url else ""
        return f"{prefix}: {a.start.astimezone().strftime('%d.%m %H:%M')} seansınız var.{z}"
    t1 = a.start - timedelta(minutes=reminder_24m)
    if t1 > now:
        scheduler.add_job(send_whatsapp_text, trigger=DateTrigger(run_date=t1),
                          args=[send_args.get('access_token',''), send_args.get('phone_number_id',''), client.phone, msg('Hatırlatma (24s)')],
                          id=f"a-{a.id}-24", replace_existing=True)
    t2 = a.start - timedelta(minutes=reminder_1h)
    if t2 > now:
        scheduler.add_job(send_whatsapp_text, trigger=DateTrigger(run_date=t2),
                          args=[send_args.get('access_token',''), send_args.get('phone_number_id',''), client.phone, msg('Hatırlatma (1s)')],
                          id=f"a-{a.id}-1", replace_existing=True)
