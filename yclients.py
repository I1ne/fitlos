import os
import httpx
from typing import List, Dict, Any
from datetime import datetime
from database import Client

YCLIENTS_API_URL = os.getenv("YCLIENTS_API_URL", "https://api.yclients.com/api/v1")
PARTNER_TOKEN = os.getenv("YCLIENTS_PARTNER_TOKEN")
USER_TOKEN = os.getenv("YCLIENTS_USER_TOKEN")

async def get_clients_from_yclients(company_id: int) -> List[Dict[str, Any]]:
    headers = {
        "Authorization": f"Bearer {USER_TOKEN}",
        "X-Partner-Token": PARTNER_TOKEN,
        "Content-Type": "application/json"
    }
    if not USER_TOKEN or not PARTNER_TOKEN:
        print("Нет токенов Yclients, возвращаем пустой список")
        return []   # НЕ ВОЗВРАЩАЕМ МОКОВ
    url = f"{YCLIENTS_API_URL}/clients/{company_id}"
    async with httpx.AsyncClient() as client:
        resp = await client.get(url, headers=headers)
        if resp.status_code == 200:
            return resp.json().get("data", [])
        else:
            print(f"Ошибка Yclients: {resp.status_code} - {resp.text}")
    return []   # НЕ ВОЗВРАЩАЕМ МОКОВ

# ========== НОВАЯ ФУНКЦИЯ РАСЧЁТА РИСКА ==========
def calculate_churn_risk_from_data(last_visit_str, visits_count, total_spent):
    
     # Recency (давность)
    risk_recency = 0.0
    if last_visit_str:
        last_visit = datetime.strptime(last_visit_str, '%Y-%m-%d')
        days_since = (datetime.now() - last_visit).days
        if days_since <= 3:
            risk_recency = 0.1
        elif days_since <= 7:
            risk_recency = 0.3
        elif days_since <= 14:
            risk_recency = 0.6
        else:
            risk_recency = 0.9
    else:
        risk_recency = 0.9

         # Frequency (частота)
    risk_frequency = 0.9 if visits_count < 4 else (0.4 if visits_count < 8 else 0.1)
      # Monetary (траты)
    risk_monetary = 0.8 if total_spent < 5000 else (0.4 if total_spent < 10000 else 0.1)
    final_risk = (risk_recency * 0.5) + (risk_frequency * 0.3) + (risk_monetary * 0.2)
    return min(max(final_risk, 0.0), 1.0)


async def sync_clients_to_db(db, company_id: int):
    #Синхронизирует клиентов из Yclients и обновляет риск оттока
    yc_clients = await get_clients_from_yclients(company_id)
    for yc in yc_clients:
        client = db.query(Client).filter(Client.yclients_id == yc["id"]).first()
        if not client:
            client = Client(
                yclients_id=yc["id"],
                name=yc["name"],
                phone=yc.get("phone"),
                email=yc.get("email"),
                last_visit=datetime.fromisoformat(yc["last_visit"]) if yc.get("last_visit") else None,
                churn_risk=0.0
            )
            db.add(client)
        calculated_risk = calculate_churn_risk_from_data(
            yc.get("last_visit", ""),
            yc.get("visits_count", 0),
            yc.get("total_spent", 0.0)
        )
        client.churn_risk = calculated_risk
    db.commit()