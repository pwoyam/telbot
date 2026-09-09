"""
AI service with singleton clients, async web search, caching, and proper error handling.
Supports: DeepSeek, OpenAI, Anthropic
"""
import asyncio
import logging
from typing import Optional

from config import (
    AI_PROVIDER, AI_API_KEY, AI_BASE_URL, AI_MODEL,
    AI_TIMEOUT, AI_MAX_RETRIES,
)
from database import (
    save_message, get_conversation_history, reset_user_history,
    get_user_language, set_user_language,
)
from cache import cache_get, cache_set

logger = logging.getLogger(__name__)

SYSTEM_PROMPT_FA = (
    "تو یک دستیار هوش مصنوعی مفید و مودب هستی که به فارسی پاسخ می‌دهی. "
    "همیشه پاسخ‌ها رو با فرمت Markdown بنویس (بولد، ایتالیک، کد، لیست)."
)
SYSTEM_PROMPT_EN = (
    "You are a helpful and polite AI assistant that responds in English. "
    "Always format your responses in Markdown (bold, italic, code, lists)."
)

MAX_HISTORY_MESSAGES = 20
MAX_HISTORY_TOKENS = 3000

# Token counting
try:
    import tiktoken
    _encoder = None
    
    def _get_encoder():
        global _encoder
        if _encoder is None:
            try:
                _encoder = tiktoken.get_encoding("cl100k_base")
            except Exception:
                _encoder = None
        return _encoder
    
    def count_tokens(text: str) -> int:
        enc = _get_encoder()
        if enc is None:
            return len(text) // 3
        return len(enc.encode(text))
    
    HAS_TIKTOKEN = True
except ImportError:
    HAS_TIKTOKEN = False
    def count_tokens(text: str) -> int:
        return len(text) // 3


class AIServiceError(Exception):
    pass

class AIServiceTimeoutError(AIServiceError):
    pass

class AIServiceRateLimitError(AIServiceError):
    pass

class AIServiceAuthError(AIServiceError):
    pass

class AIServiceUnavailableError(AIServiceError):
    pass


# Singleton AI Clients
_openai_client = None
_anthropic_client = None


def _get_openai_client():
    """Get OpenAI-compatible client (works with DeepSeek, OpenAI, etc.)"""
    global _openai_client
    if _openai_client is None:
        from openai import AsyncOpenAI
        
        # DeepSeek and other OpenAI-compatible providers
        if AI_PROVIDER == "deepseek":
            base_url = AI_BASE_URL or "https://api.deepseek.com/v1"
            logger.info("🤖 Initializing DeepSeek client")
        else:
            base_url = AI_BASE_URL or None
            logger.info("🤖 Initializing OpenAI-compatible client")
        
        _openai_client = AsyncOpenAI(
            api_key=AI_API_KEY,
            base_url=base_url,
            timeout=AI_TIMEOUT,
            max_retries=AI_MAX_RETRIES,
        )
    return _openai_client


def _get_anthropic_client():
    global _anthropic_client
    if _anthropic_client is None:
        from anthropic import AsyncAnthropic
        _anthropic_client = AsyncAnthropic(
            api_key=AI_API_KEY,
            base_url=AI_BASE_URL or None,
            timeout=AI_TIMEOUT,
            max_retries=AI_MAX_RETRIES,
        )
        logger.info("Anthropic client initialized")
    return _anthropic_client


async def _get_language(user_id: int) -> str:
    return await get_user_language(user_id)


async def set_language(user_id: int, lang: str):
    await set_user_language(user_id, lang)


async def reset_history(user_id: int):
    await reset_user_history(user_id)


def _sync_web_search(query: str, num_results: int = 5) -> str:
    try:
        from duckduckgo_search import DDGS
        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=num_results))
        
        if not results:
            return "نتیجه‌ای پیدا نشد."
        
        formatted = f"🔍 نتایج جستجو برای: **{query}**\n\n"
        for i, r in enumerate(results, 1):
            title = r.get("title", "بدون عنوان")
            body = r.get("body", "بدون توضیحات")
            href = r.get("href", "")
            formatted += f"{i}. **{title}**\n{body}\n"
            if href:
                formatted += f"🔗 [مطالعه بیشتر]({href})\n"
            formatted += "\n"
        return formatted
    except Exception:
        logger.exception("Web search failed")
        return "❌ جستجو در حال حاضر در دسترس نیست."


async def web_search(query: str, num_results: int = 5) -> str:
    cache_key = (query, num_results)
    cached = await cache_get("web_search", *cache_key)
    if cached:
        logger.info("🗂️ Cache hit for web search")
        return cached
    
    result = await asyncio.to_thread(_sync_web_search, query, num_results)
    
    if "خطا" not in result and "Error" not in result:
        await cache_set("web_search", query, num_results, value=result)
        logger.info("🗂️ Cached web search result")
    
    return result


async def get_ai_response(user_id: int, user_message: str) -> str:
    lang = await _get_language(user_id)
    system_prompt = SYSTEM_PROMPT_FA if lang == "fa" else SYSTEM_PROMPT_EN
    
    history = await get_conversation_history(
        user_id, limit=MAX_HISTORY_MESSAGES, max_tokens=MAX_HISTORY_TOKENS
    )
    
    use_cache = len(history) == 0
    
    if use_cache:
        cache_key = (user_message, lang, AI_MODEL, AI_PROVIDER)
        cached = await cache_get("ai_response", *cache_key)
        if cached:
            logger.info("🗂️ Cache hit for AI response")
            await save_message(user_id, "user", user_message)
            await save_message(user_id, "assistant", cached)
            return cached
    
    try:
        if AI_PROVIDER == "anthropic":
            reply = await _call_anthropic(history, system_prompt)
        else:
            reply = await _call_openai_compatible(history, system_prompt)
    except AIServiceError:
        raise
    
    await save_message(user_id, "user", user_message)
    await save_message(user_id, "assistant", reply)
    
    if use_cache:
        await cache_set("ai_response", user_message, lang, AI_MODEL, AI_PROVIDER, value=reply)
        logger.info("🗂️ Cached AI response")
    
    return reply


async def get_ai_response_inline(user_id: int, query: str) -> str:
    lang = await _get_language(user_id)
    system_prompt = SYSTEM_PROMPT_FA if lang == "fa" else SYSTEM_PROMPT_EN
    
    cache_key = (query, lang, AI_MODEL, AI_PROVIDER, "inline")
    cached = await cache_get("ai_response_inline", *cache_key)
    if cached:
        logger.info("🗂️ Cache hit for inline query")
        return cached
    
    history = [{"role": "user", "content": query}]
    
    try:
        if AI_PROVIDER == "anthropic":
            reply = await _call_anthropic(history, system_prompt)
        else:
            reply = await _call_openai_compatible(history, system_prompt)
    except AIServiceError:
        raise
    
    await cache_set("ai_response_inline", query, lang, AI_MODEL, AI_PROVIDER, "inline", value=reply)
    logger.info("🗂️ Cached inline response")
    
    return reply


def _classify_error(e: Exception) -> AIServiceError:
    msg = str(e).lower()
    if "timeout" in msg or "timed out" in msg:
        return AIServiceTimeoutError("درخواست زمان بیشتری نیاز دارد")
    if "429" in msg or "rate limit" in msg:
        return AIServiceRateLimitError("محدودیت درخواست‌ها")
    if "401" in msg or "403" in msg or "auth" in msg:
        return AIServiceAuthError("خطا در احراز هویت")
    if any(code in msg for code in ("500", "502", "503", "504")):
        return AIServiceUnavailableError("سرویس موقتاً در دسترس نیست")
    return AIServiceError(f"خطا در سرویس هوش مصنوعی: {e}")


async def _call_openai_compatible(history: list, system_prompt: str) -> str:
    client = _get_openai_client()
    messages = [{"role": "system", "content": system_prompt}] + history
    try:
        response = await client.chat.completions.create(
            model=AI_MODEL,
            messages=messages,
            max_tokens=4000,
        )
        return response.choices[0].message.content
    except AIServiceError:
        raise
    except Exception as e:
        raise _classify_error(e)


async def _call_anthropic(history: list, system_prompt: str) -> str:
    client = _get_anthropic_client()
    try:
        response = await client.messages.create(
            model=AI_MODEL,
            max_tokens=4000,
            system=system_prompt,
            messages=history,
        )
        return response.content[0].text
    except AIServiceError:
        raise
    except Exception as e:
        raise _classify_error(e)
