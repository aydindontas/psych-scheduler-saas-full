from sqlmodel import SQLModel, Field, Relationship
from typing import Optional, List
from datetime import datetime

class Tenant(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    tenant_key: str
    created_at: datetime = Field(default_factory=datetime.utcnow)

    users: List['User'] = Relationship(back_populates='tenant')
    clients: List['Client'] = Relationship(back_populates='tenant')
    appointments: List['Appointment'] = Relationship(back_populates='tenant')

class User(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    tenant_id: int = Field(foreign_key='tenant.id')
    email: str
    password_hash: str
    role: str = Field(default='admin')
    created_at: datetime = Field(default_factory=datetime.utcnow)
    tenant: Optional[Tenant] = Relationship(back_populates='users')

class Client(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    tenant_id: int = Field(foreign_key='tenant.id')
    phone: str
    name: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    tenant: Optional[Tenant] = Relationship(back_populates='clients')
    appointments: List['Appointment'] = Relationship(back_populates='client')

class Appointment(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    tenant_id: int = Field(foreign_key='tenant.id')
    client_id: int = Field(foreign_key='client.id')
    start: datetime
    end: datetime
    status: str = Field(default='confirmed')
    source: str = Field(default='whatsapp')
    ms_event_id: Optional[str] = None
    tenant: Optional[Tenant] = Relationship(back_populates='appointments')
    client: Optional[Client] = Relationship(back_populates='appointments')
