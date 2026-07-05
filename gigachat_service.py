from knowledge_base import retrieve_context
import os
import json
import re
import httpx
from dotenv import load_dotenv

load_dotenv()

AUTH_KEY = os.getenv("GIGACHAT_CREDENTIALS")
SCOPE = os.getenv("GIGACHAT_SCOPE", "GIGACHAT_API_PERS")
MODEL = os.getenv("GIGACHAT_MODEL", "GigaChat")
TOKEN_URL = "https://ngw.devices.sberbank.ru:9443/api/v2/oauth"
API_URL = "https://gigachat.devices.sberbank.ru/api/v1/chat/completions"

async def get_access_token() -> str:
    async with httpx.AsyncClient(verify=False) as client:
        response = await client.post(
            TOKEN_URL,
            headers={
                "Authorization": f"Basic {AUTH_KEY}",
                "Content-Type": "application/x-www-form-urlencoded",
                "Accept": "application/json",
                "RqUID": "123e4567-e89b-12d3-a456-426614174000"
            },
            data={"scope": SCOPE}
        )
        if response.status_code != 200:
            raise Exception(f"Ошибка получения токена: {response.status_code} - {response.text}")
        return response.json()["access_token"]

def analyze_chat(chat_history: str) -> dict:
    import asyncio
    return asyncio.run(analyze_chat_async(chat_history))

async def analyze_chat_async(chat_history: str) -> dict:
    try:
        token = await get_access_token()
    except Exception as e:
        print(f"Ошибка получения токена: {e}")
        return {
            "summary": "Не удалось подключиться к GigaChat.",
            "sentiment": "neutral",
            "churn_probability": 0.5,
            "draft_response": "Здравствуйте! Чем могу помочь?"
        }

    # ==================== RAG: поиск релевантного контекста ====================
    relevant_context = retrieve_context(chat_history, top_k=2)
    if relevant_context:
        context_section = f"""
Используй следующую информацию из базы знаний фитнес-клуба, если она относится к вопросу клиента:

{relevant_context}
"""
    else:
        context_section = ""

    prompt = f"""
Ты — профессиональный ассистент фитнес-клуба Los Island.
{context_section}
Проанализируй диалог с клиентом и дай рекомендации.
Верни ТОЛЬКО JSON (без комментариев) в формате:
{{
  "summary": "краткое содержание диалога (2-3 предложения)",
  "sentiment": "positive/neutral/negative",
  "churn_probability": число от 0 до 1,
  "draft_response": "готовый ответ администратора клиенту (вежливо, по существу)"
}}
Диалог:
{chat_history}
""".strip()

    async with httpx.AsyncClient(verify=False, timeout=30.0) as client:
        response = await client.post(
            API_URL,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
                "Accept": "application/json"
            },
            json={
                "model": MODEL,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.7,
                "max_tokens": 800  # увеличено, чтобы уместился контекст
            }
        )
        if response.status_code != 200:
            print(f"Ошибка GigaChat API: {response.status_code} - {response.text}")
            return {
                "summary": f"Ошибка API: {response.status_code}",
                "sentiment": "neutral",
                "churn_probability": 0.5,
                "draft_response": "Произошла ошибка при анализе. Попробуйте позже."
            }
        result = response.json()
        content = result["choices"][0]["message"]["content"].strip()
        match = re.search(r"\{[\s\S]*\}", content)
        if match:
            content = match.group(0)
        try:
            return json.loads(content)
        except:
            return {
                "summary": content[:300],
                "sentiment": "neutral",
                "churn_probability": 0.5,
                "draft_response": "Не удалось разобрать ответ. Проверьте диалог."
            }