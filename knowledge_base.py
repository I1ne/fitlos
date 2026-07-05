# knowledge_base.py
import re
from typing import List, Tuple

# Глобальная переменная для хранения базы знаний
_KB_CHUNKS = []  # список кортежей (заголовок, текст)

def load_knowledge_base(file_path: str = "kb.txt") -> None:
    """Загружает файл с базой знаний и разбивает на блоки по заголовкам."""
    global _KB_CHUNKS
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Разбиваем по строкам, начинающимся с заглавных букв или цифр (маркеры)
    # Простой способ: разделяем по двойным переводам строк, потом выделяем заголовки
    blocks = re.split(r'\n\s*\n', content)  # разделяем по пустым строкам
    for block in blocks:
        lines = block.strip().split('\n')
        if not lines:
            continue
        # Первая строка блока – заголовок
        header = lines[0].strip()
        text = '\n'.join(lines[1:]).strip() if len(lines) > 1 else ''
        if header and text:
            _KB_CHUNKS.append((header.lower(), text))
        elif header:
            _KB_CHUNKS.append((header.lower(), ''))
    print(f"База знаний загружена: {len(_KB_CHUNKS)} блоков.")

def retrieve_context(query: str, top_k: int = 3) -> str:
    """
    Ищет в базе знаний top_k блоков, наиболее релевантных запросу.
    Для простоты используем поиск по вхождению ключевых слов.
    """
    if not _KB_CHUNKS:
        return ""
    query_words = set(re.findall(r'\b\w+\b', query.lower()))
    if not query_words:
        return ""
    
    # Подсчитываем количество совпадающих слов в каждом блоке
    scored = []
    for header, text in _KB_CHUNKS:
        content = header + ' ' + text
        content_lower = content.lower()
        score = sum(1 for word in query_words if word in content_lower)
        if score > 0:
            scored.append((score, header, text))
    
    # Сортируем по убыванию релевантности
    scored.sort(reverse=True, key=lambda x: x[0])
    top = scored[:top_k]
    
    # Формируем контекст
    context_parts = []
    for score, header, text in top:
        context_parts.append(f"### {header.capitalize()}\n{text[:500]}")  # ограничим длину
    return "\n\n".join(context_parts)

# Загружаем базу знаний при импорте модуля
load_knowledge_base("kb.txt")