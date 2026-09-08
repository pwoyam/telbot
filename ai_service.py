from config import AI_PROVIDER, AI_API_KEY, AI_BASE_URL, AI_MODEL
from database import save_message, get_conversation_history, reset_user_history, get_user_language, set_user_language
from duckduckgo_search import DDGS
import asyncio

SYSTEM_PROMPT_FA = "تو یک دستیار هوش مصنوعی مفید و مودب هستی که به فارسی پاسخ می‌دهی. همیشه پاسخ‌ها رو با فرمت Markdown بنویس (بولد، ایتالیک، کد، لیست)."
SYSTEM_PROMPT_EN = "You are a helpful and polite AI assistant that responds in English. Always format your responses in Markdown (bold, italic, code, lists)."

MAX_HISTORY_MESSAGES = 10

async def _get_language(user_id: int) -> str:
    return await get_user_language(user_id)

async def set_language(user_id: int, lang: str):
    await set_user_language(user_id, lang)

async def reset_history(user_id: int):
    await reset_user_history(user_id)

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
            formatted += f"🔗 بیشتر بخوانید\n\n"
        
        return formatted
    except Exception as e:
        return f"خطا در جستجو: {str(e)}"

async def get_ai_response(user_id: int, user_message: str) -> str:
    lang = await _get_language(user_id)
    system_prompt = SYSTEM_PROMPT_FA if lang == "fa" else SYSTEM_PROMPT_EN
    
    await save_message(user_id, "user", user_message)
    history = await get_conversation_history(user_id, limit=MAX_HISTORY_MESSAGES)
    
    if AI_PROVIDER == "anthropic":
        reply = await _call_anthropic(history, system_prompt)
    else:
        reply = await _call_openai_compatible(history, system_prompt)
    
    await save_message(user_id, "assistant", reply)
    return reply

async def _call_openai_compatible(history: list, system_prompt: str) -> str:
    from openai import AsyncOpenAI
    client = AsyncOpenAI(api_key=AI_API_KEY, base_url=AI_BASE_URL or None)
    messages = [{"role": "system", "content": system_prompt}] + history
    response = await client.chat.completions.create(
        model=AI_MODEL,
        messages=messages,
        max_tokens=4000,
    )
    return response.choices[0].message.content

async def _call_anthropic(history: list, system_prompt: str) -> str:
    from anthropic import AsyncAnthropic
    client = AsyncAnthropic(api_key=AI_API_KEY, base_url=AI_BASE_URL or None)
    response = await client.messages.create(
        model=AI_MODEL,
        max_tokens=4000,
        system=system_prompt,
        messages=history,
    )
    return response.content[0].text
