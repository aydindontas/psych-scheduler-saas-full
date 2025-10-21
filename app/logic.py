from datetime import datetime, timedelta, time as dtime, timezone
from dateutil import tz
from typing import List, Tuple
from sqlmodel import Session, select
from .models import Appointment, Client

def overlaps(a_start, a_end, b_start, b_end)->bool:
    return max(a_start,b_start) < min(a_end,b_end)

def working_slots(day: datetime, work_start: dtime, work_end: dtime, slot_minutes: int, tz_name: str):
    tzi = tz.gettz(tz_name)
    local = day.astimezone(tzi).replace(hour=work_start.hour, minute=work_start.minute, second=0, microsecond=0)
    end_local = day.astimezone(tzi).replace(hour=work_end.hour, minute=work_end.minute, second=0, microsecond=0)
    slots=[]
    cur=local
    while cur + timedelta(minutes=slot_minutes) <= end_local:
        nxt = cur + timedelta(minutes=slot_minutes)
        slots.append((cur.astimezone(timezone.utc), nxt.astimezone(timezone.utc)))
        cur = nxt
    return slots

def busy_from_db(session: Session, tenant_id: int, start: datetime, end: datetime):
    appts = session.exec(select(Appointment).where(Appointment.tenant_id==tenant_id).where(Appointment.start<end).where(Appointment.end>start).where(Appointment.status=='confirmed')).all()
    return [(a.start,a.end) for a in appts]

def ensure_client(session: Session, tenant_id: int, phone: str, name: str|None=None)->Client:
    c = session.exec(select(Client).where(Client.tenant_id==tenant_id).where(Client.phone==phone)).first()
    if c: return c
    c = Client(tenant_id=tenant_id, phone=phone, name=name or None)
    session.add(c); session.commit(); session.refresh(c)
    return c
