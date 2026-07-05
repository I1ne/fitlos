from datetime import datetime
from pydantic import BaseModel
from fastapi import FastAPI, Depends, HTTPException, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session
from datetime import timedelta
from typing import List
import random

from database import SessionLocal, User, Client, ChatLog
from auth import get_current_user, authenticate_user, create_access_token, get_password_hash, oauth2_scheme
from schemas import LoginRequest, Token, UserCreate, ClientOut, ChatLogOut
from yclients import sync_clients_to_db
from gigachat_service import analyze_chat

app = FastAPI(title="ФИТЛОСЬ Analytics")
templates = Jinja2Templates(directory="templates")
app.mount("/static", StaticFiles(directory="static"), name="static")

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ------------------- Домашняя страница (редирект на логин) ------------------
@app.get("/", response_class=HTMLResponse)
def root():
    return RedirectResponse(url="/login")

# ------------------- Логин и регистрация ------------------------------------
@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})

@app.post("/api/login")
async def login(login: LoginRequest, db: Session = Depends(get_db)):
    user = authenticate_user(db, login.username, login.password)
    if not user:
        raise HTTPException(status_code=401, detail="Неверный логин или пароль")
    token = create_access_token(data={"sub": user.username}, expires_delta=timedelta(minutes=30))
    return {"access_token": token, "token_type": "bearer"}

@app.post("/api/register")
def register(user: UserCreate, db: Session = Depends(get_db)):
    existing = db.query(User).filter(User.username == user.username).first()
    if existing:
        raise HTTPException(status_code=400, detail="Пользователь уже существует")
    hashed = get_password_hash(user.password)
    new_user = User(username=user.username, hashed_password=hashed)
    db.add(new_user)
    db.commit()
    return {"msg": "ok"}

# ------------------- Дашборд (основная страница) ---------------------------
@app.get("/dashboard", response_class=HTMLResponse)
def dashboard(request: Request):
    return templates.TemplateResponse("dashboard.html", {"request": request})

# ------------------- API для клиентов (из БД + синхронизация с Yclients) ---
@app.get("/api/clients", response_model=List[ClientOut])
def get_clients(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    clients = db.query(Client).order_by(Client.id).all()   # добавили order_by
    return clients

@app.post("/api/sync_clients")
def sync_clients(company_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    import asyncio
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(sync_clients_to_db(db, company_id))
        loop.close()
        return {"status": "sync completed"}
    except Exception as e:
        print(f"Ошибка синхронизации: {e}")
       

# ------------------- API для чатов MAX ---------------------------------------
@app.get("/api/chats", response_model=List[ChatLogOut])
def get_chats(limit: int = 20, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    chats = db.query(ChatLog).order_by(ChatLog.timestamp.desc()).limit(limit).all()
    return chats

# Пример загрузки тестовых чатов (MAX)
@app.post("/api/load_sample_chats")
def load_sample_chats(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    # Удалим старые для чистоты
    db.query(ChatLog).delete()
    sample = [
        {"client_id": 1, "source": "MAX", "message": "Клиент: Здравствуйте, хочу записаться на массаж.", "is_from_client": True, "timestamp": "2026-05-15T10:00:00"},
        {"client_id": 1, "source": "MAX", "message": "Система: Здравствуйте! Свободные слоты завтра в 15:00 и 16:00.", "is_from_client": False, "timestamp": "2026-05-15T10:00:30"},
        {"client_id": 2, "source": "MAX", "message": "Клиент: У меня болит спина, можно ли перенести тренировку?", "is_from_client": True, "timestamp": "2026-05-14T09:20:00"},
    ]
    for s in sample:
        from datetime import datetime
        chat = ChatLog(
            client_id=s["client_id"],
            source=s["source"],
            message=s["message"],
            is_from_client=s["is_from_client"],
            timestamp=datetime.fromisoformat(s["timestamp"])
        )
        db.add(chat)
    db.commit()
    return {"msg": "sample chats loaded"}

# ------------------- Анализ конкретного чата через GigaChat ---------------
@app.post("/api/analyze_chat/{chat_id}")
def analyze_chat_endpoint(chat_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    # Получаем все сообщения этого чата (по client_id, source='MAX')
    chat = db.query(ChatLog).filter(ChatLog.id == chat_id).first()
    if not chat:
        raise HTTPException(404, "Чат не найден")
    # Собираем историю этого клиента (все сообщения)
    history = db.query(ChatLog).filter(ChatLog.client_id == chat.client_id, ChatLog.source == "MAX").order_by(ChatLog.timestamp).all()
    full_text = "\n".join([f"{'Клиент' if m.is_from_client else 'Система'}: {m.message}" for m in history])
    result = analyze_chat(full_text)
    # Сохраняем саммари в БД (первое сообщение)
    chat.ai_summary = result.get("summary", "")
    db.commit()
    return result

    # ------------------- Аналитические метрики для дашборда -------------------
@app.get("/api/analytics/metrics")
def get_metrics(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    from collections import defaultdict
    from datetime import timedelta
    
    # 1. Все диалоги
    all_chats = db.query(ChatLog).order_by(ChatLog.timestamp).all()
    total_dialogs = len(set(c.client_id for c in all_chats))
    
    # 2. Среднее время ответа (секунды)
    response_times = []
    client_msgs = defaultdict(list)
    for msg in all_chats:
        client_msgs[msg.client_id].append(msg)
    for msgs in client_msgs.values():
        msgs.sort(key=lambda x: x.timestamp)
        last_client_time = None
        for msg in msgs:
            if msg.is_from_client:
                last_client_time = msg.timestamp
            else:
                if last_client_time is not None:
                    delta = (msg.timestamp - last_client_time).total_seconds()
                    if 0 < delta < 3600:
                        response_times.append(delta)
                    last_client_time = None
    avg_response_sec = sum(response_times) / len(response_times) if response_times else 0
    avg_response_min = round(avg_response_sec / 60, 1)
    
    # 3. Конверсия в запись
    conversion_keywords = ['записать', 'запишите', 'подтверждаю', 'запишись', 'записи', 'ок', 'давайте']
    converted_chats = set()
    for msg in all_chats:
        if msg.is_from_client:
            text = msg.message.lower()
            if any(kw in text for kw in conversion_keywords):
                converted_chats.add(msg.client_id)
    conversion_rate = (len(converted_chats) / total_dialogs) * 100 if total_dialogs else 0
    
    # 4. Клиенты с высоким риском оттока (>0.6) – персонализированные действия
    high_risk_clients = db.query(Client).filter(Client.churn_risk > 0.6).all()
    action_map = {
        "Шахгельдян": "Предложить записаться на RSL Sculptor Beautylizer со скидкой 10%",
        "Валиуллина": "Предложить клубную карту со скидкой 15%",
        "Кутузова-Зарубинская": "Предложить клубную карту со скидкой 10%",
        "Авакян": "Предложить записаться на Общий массаж или абонемент со скидкой",
        "Преснецова": "Предложить абонемент на персональные тренировки со скидкой",
        "Папуша": "Написать, что давно не было в фитнес-клубе",
        "Ланцева": "Предложить записаться на RSL Sculptor Beautylizer",
        "Бадмаев": "Предложить клубную карту на 6 месяцев",
        "Щербаченко": "Предложить Общий массаж или абонемент с персональными тренировками",
        "Мазин": "Предложить клубную карту с тренажёрным залом",
    }
    high_risk_list = []
    for c in high_risk_clients:
        action = "📱 Связаться и предложить персональную скидку"
        for key, val in action_map.items():
            if key in c.name:
                action = val
                break
        high_risk_list.append({"id": c.id, "name": c.name, "risk": c.churn_risk, "action": action})
    
    return {
        "total_dialogs": total_dialogs,
        "avg_response_min": avg_response_min,
        "conversion_rate": round(conversion_rate, 1),
        "high_risk_clients": high_risk_list,
        "proactive_message": "Внимание! Есть клиенты с высоким риском оттока. Рекомендуем связаться." if high_risk_clients else None
    }

    # ------------------- Восстановление пароля ---------------------------------------

class ResetPasswordRequest(BaseModel):
    username: str
    new_password: str

@app.post("/api/reset-password")
def reset_password(req: ResetPasswordRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == req.username).first()
    if not user:
        raise HTTPException(status_code=404, detail="Пользователь не найден")
    user.hashed_password = get_password_hash(req.new_password)
    db.commit()
    return {"msg": "ok"}


    # ------------------- Сегментация клиентов -------------------
@app.get("/api/segments")
def get_segments(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    from datetime import datetime, timedelta
    
    clients = db.query(Client).all()
    
    # 1. Сегментация по риску оттока (на основе churn_risk)
    risk_segments = {
        "low": 0,   # < 0.3
        "medium": 0,# 0.3 - 0.6
        "high": 0   # > 0.6
    }
    # 2. Сегментация по активности (давность последнего визита)
    active_threshold = 7       # последние 7 дней
    sleeping_threshold = 30    # более 30 дней
    activity_segments = {
        "active": 0,      # визит в последние 7 дней
        "sleeping": 0,    # от 8 до 30 дней
        "lost": 0         # более 30 дней или нет визитов
    }
    
    today = datetime.now().date()
    for c in clients:
        # сегментация по риску
        if c.churn_risk < 0.3:
            risk_segments["low"] += 1
        elif c.churn_risk <= 0.6:
            risk_segments["medium"] += 1
        else:
            risk_segments["high"] += 1
        
        # сегментация по активности
        if c.last_visit:
            days_since = (today - c.last_visit.date()).days
            if days_since <= active_threshold:
                activity_segments["active"] += 1
            elif days_since <= sleeping_threshold:
                activity_segments["sleeping"] += 1
            else:
                activity_segments["lost"] += 1
        else:
            activity_segments["lost"] += 1
    
    return {
        "risk": risk_segments,
        "activity": activity_segments,
        "total": len(clients)
    }