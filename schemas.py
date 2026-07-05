from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime

class Token(BaseModel):
    access_token: str
    token_type: str

class LoginRequest(BaseModel):
    username: str
    password: str

class UserCreate(BaseModel):
    username: str
    password: str

class ClientOut(BaseModel):
    id: int
    name: str
    phone: Optional[str]
    email: Optional[str]
    churn_risk: float
    last_visit: Optional[datetime]

class ChatLogOut(BaseModel):
    id: int
    client_id: int
    source: str
    message: str
    is_from_client: bool
    timestamp: datetime
    ai_summary: Optional[str]