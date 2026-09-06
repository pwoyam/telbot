from config import AI_PROVIDER, AI_API_KEY, AI_BASE_URL, AI_MODEL
from database import save_message
from duckduckgo_search import DDGS
import asyncio

SYSTEM_PROMPT_FA = "تو یک دستیار هوش مصنوعی مفید و مودب هستی که به فارسی پاسخ می‌دهی. همیشه پاسخ‌ها رو با فرمت Markdown بنویس (بولد، ایتالیک، کد، لیست)."
SYSTEM_PROMPT_EN = "You are a helpful and polite AI assistant that responds in English. Always format your responses in Markdown (bold, italic, code, lists)."

_conversation_memory: dict[int, list[dict]] = {}
_user_language: dict[int, str] = {}
MAX_HISTORY_MESSAGES = 10


def _get_history(user_id: int) -> list[dict]:
    return _conversation_memory.setdefault(user_id, [])


def _get_language(user_id: int) -> str:
    return _user_language.get(user_id, "fa")


def set_language(user_id: int, lang: str):
    _user_language[user_id] = lang


def _append_history(user_id: int, role: str, content: str):
    history = _get_history(user_id)
    history.append({"role": role, "content": content})
    if len(history) > MAX_HISTORY_MESSAGES:
        del history[: len(history) - MAX_HISTORY_MESSAGES]


def reset_history(user_id: int):
    _conversation_memory[user_id] = []


def web_search(query: str, num_results: int = 5) -> str:
    """جستجوی وب با DuckDuckGo"""
    try:
        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=num_results))
        
        if not results:
            return "نتیجه‌ای پیدا نشد."
        
        formatted = f"🔍 نتایج جستجو برای: **{query}**\n\n"
        for i, result in enumerate(results, 1):
            formatted += f"{i}. **{result['title']}**\n"
            formatted += f"{result['body']}\n"
            formatted += f"🔗 [بیشتر بخوانید]({result['href']})\n\n"
        
        return formatted
    except Exception as e:
        return f"خطا در جستجو: {str(e)}"


async def get_ai_response(user_id: int, user_message: str) -> str:
    lang = _get_language(user_id)
    system_prompt = SYSTEM_PROMPT_FA if lang == "fa" else SYSTEM_PROMPT_EN
    
    _append_history(user_id, "user", user_message)
    save_message(user_id, "user", user_message)
    history = _get_history(user_id)
    
    if AI_PROVIDER == "anthropic":
        reply = await _call_anthropic(history, system_prompt)
    else:
        reply = await _call_openai_compatible(history, system_prompt)
    
    _append_history(user_id, "assistant", reply)
    save_message(user_id, "assistant", reply)
    return reply


async def _call_openai_compatible(history: list[dict], system_prompt: str) -> str:
    from openai import AsyncOpenAI
    client = AsyncOpenAI(api_key=AI_API_KEY, base_url=AI_BASE_URL or None)
    messages = [{"role": "system", "content": system_prompt}] + history
    response = await client.chat.completions.create(
        model=AI_MODEL,
        messages=messages,
        max_tokens=4000,
    )
    return response.choices[0].message.content


async def _call_anthropic(history: list[dict], system_prompt: str) -> str:
    from anthropic import AsyncAnthropic
    client = AsyncAnthropic(api_key=AI_API_KEY, base_url=AI_BASE_URL or None)
    response = await client.messages.create(
        model=AI_MODEL,
        max_tokens=4000,
        system=system_prompt,
        messages=history,
    )
    return response.content[0].text